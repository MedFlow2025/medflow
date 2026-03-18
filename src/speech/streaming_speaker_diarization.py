import argparse
import base64
from collections import Counter, deque
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.amp
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from nemo.collections.asr.models import SortformerEncLabelModel
from pydantic import BaseModel


def args_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1", help="host to bind")
    parser.add_argument("--port", type=int, default=8009, help="port to bind")
    parser.add_argument(
        "--diar-model",
        type=str,
        default="/root/.cache/modelscope/hub/models/diar_streaming_sortformer_4spk-v2/diar_streaming_sortformer_4spk-v2.nemo",
        help="Path to diarization model",
    )
    args, _ = parser.parse_known_args()
    return args


args = args_parser()

model_diar = None
autocast = None
diarization_manager = None


class AudioRequest(BaseModel):
    audio_data: str
    session_id: str
    asr_text: Optional[str] = ""
    punc_text: Optional[str] = ""
    timestamps: Optional[List[List[int]]] = []


class SpeakerSegment(BaseModel):
    text: str
    start_time: str
    end_time: str
    speaker_id: str


class DiarizationResponse(BaseModel):
    segments: List[SpeakerSegment]
    session_id: str
    status: str


app = FastAPI(title="Speaker Diarization Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TimestampedAudioBuffer:
    def __init__(self, max_duration=300, sample_rate=16000):
        """Buffer aligned with timestamps"""
        self.sample_rate = sample_rate
        self.max_samples = int(max_duration * sample_rate)
        self.buffer = deque(maxlen=self.max_samples)
        self.start_time = 0.0
        self.end_time = 0.0

    def append(self, audio_chunk, chunk_start_time):
        """Add audio chunk and record timestamp"""
        chunk_duration = len(audio_chunk) / self.sample_rate

        if len(self.buffer) == 0:
            self.start_time = chunk_start_time

        self.buffer.extend(audio_chunk)
        self.end_time = chunk_start_time + chunk_duration

        if len(self.buffer) >= self.max_samples:
            removed_samples = len(self.buffer) - self.max_samples
            self.start_time += removed_samples / self.sample_rate

    def extract_segment(self, global_start_time, global_end_time):
        """Extract audio segment for specified global time range"""
        start_index = int((global_start_time - self.start_time) * self.sample_rate)
        end_index = int((global_end_time - self.start_time) * self.sample_rate)

        start_index = max(0, min(start_index, len(self.buffer)))
        end_index = max(0, min(end_index, len(self.buffer)))

        if start_index >= end_index:
            return np.array([])

        buffer_array = np.array(self.buffer)
        return buffer_array[start_index:end_index]

    def get_current_duration(self):
        """Get current duration of the buffer"""
        return len(self.buffer) / self.sample_rate


class StreamingSpeakerDiarization:
    """Streaming Speaker Diarization - Real-time speaker identification and tracking"""

    def __init__(self, model_diar):
        self.model_diar = model_diar
        self.sample_rate = 16000

        # Configure model's streaming parameters
        dm = model_diar.sortformer_modules
        dm.chunk_len = 6
        dm.spkcache_len = 188
        dm.chunk_right_context = 7
        dm.fifo_len = 188
        dm.spkcache_update_period = 144
        dm.log = False
        # dm._check_streaming_parameters()

        self.sessions: Dict[str, dict] = {}

    def get_or_create_session(self, session_id: str):
        """Get existing session state or create new one if it doesn't exist"""
        if session_id not in self.sessions:
            self.sessions[session_id] = self._init_session_state()
        return self.sessions[session_id]

    def _init_session_state(self):
        """Initialize state for a new streaming session"""
        batch_size = 1
        return {
            "batch_size": batch_size,
            "audio_buffer": np.array([], dtype=np.float32),
            "processed_signal_offset": torch.zeros(
                (batch_size,), dtype=torch.long, device=self.model_diar.device
            ),
            "streaming_state": self.model_diar.sortformer_modules.init_streaming_state(
                batch_size=batch_size,
                async_streaming=True,
                device=self.model_diar.device,
            ),
            "total_preds": torch.zeros(
                (batch_size, 0, self.model_diar.sortformer_modules.n_spk),
                device=self.model_diar.device,
            ),
            "frame_duration": (
                self.model_diar.preprocessor._cfg.window_stride
                * self.model_diar.sortformer_modules.subsampling_factor
            ),
            "audio_buffer_manager": TimestampedAudioBuffer(
                max_duration=300, sample_rate=self.sample_rate
            ),
            "current_stream_time": 0.0,
            "last_speaker_intervals": {},
            "all_speaker_intervals": {},
            "global_audio_start_time": 0.0,
            "total_audio_duration": 0.0,
            "processed_frames_count": 0,
        }

    async def process_audio_chunk(
        self,
        session_id: str,
        audio_data: bytes,
        asr_text: str = "",
        punc_text: str = "",
        timestamps: List[List[int]] = None,
    ):
        """Process audio chunk and return speaker diarization results"""
        session = self.get_or_create_session(session_id)

        chunk_start_time = session["total_audio_duration"]
        chunk_duration = len(audio_data) / self.sample_rate / 2  # bytes to seconds

        session["total_audio_duration"] += chunk_duration
        session["global_audio_start_time"] = chunk_start_time

        signal = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        session["audio_buffer_manager"].append(signal, session["current_stream_time"])
        session["current_stream_time"] += chunk_duration
        session["audio_buffer"] = np.concatenate((session["audio_buffer"], signal))

        # Process audio buffer when it has enough data
        if len(session["audio_buffer"]) > 0:
            chunk = session["audio_buffer"]
            session["audio_buffer"] = np.array([], dtype=np.float32)

            audio_signal = torch.tensor(chunk, device=self.model_diar.device).unsqueeze(
                0
            )
            audio_signal_length = torch.tensor(
                [audio_signal.shape[1]], device=self.model_diar.device
            )

            processed_signal, processed_signal_length = self.model_diar.process_signal(
                audio_signal=audio_signal, audio_signal_length=audio_signal_length
            )
            processed_signal = processed_signal[:, :, : processed_signal_length.max()]

            streaming_loader = self.model_diar.sortformer_modules.streaming_feat_loader(
                feat_seq=processed_signal,
                feat_seq_length=processed_signal_length,
                feat_seq_offset=session["processed_signal_offset"],
            )

            for (
                _,
                chunk_feat_seq_t,
                feat_lengths,
                left_offset,
                right_offset,
            ) in streaming_loader:
                with (
                    torch.inference_mode(),
                    autocast,
                ):
                    session["streaming_state"], session["total_preds"] = (
                        self.model_diar.forward_streaming_step(
                            processed_signal=chunk_feat_seq_t,
                            processed_signal_length=feat_lengths,
                            streaming_state=session["streaming_state"],
                            total_preds=session["total_preds"],
                            left_offset=left_offset,
                            right_offset=right_offset,
                        )
                    )

            end_frame = session["total_preds"][0].shape[0]

            # Process speaker predictions into time intervals
            time_intervals = self._handle_total_preds(
                session["total_preds"][0],
                session["frame_duration"],
                start_frame=session["processed_frames_count"],
                end_frame=end_frame,
            )
            # logger.info(f"Total intervals: {time_intervals}")

            session["processed_frames_count"] = end_frame

            # Identify new intervals since last processing
            new_intervals = self._update_intervals(session, time_intervals)
            # logger.info(f"New intervals: {new_intervals}")

            self.last_speaker_intervals = time_intervals

            del processed_signal, processed_signal_length

        # Align speaker segments with ASR text
        aligned_segments = self._align_asr_with_speaker(
            session, asr_text, punc_text, timestamps, new_intervals
        )

        return aligned_segments

    def _handle_total_preds(
        self, total_preds, frame_duration, start_frame, end_frame, threshold=0.55
    ):
        """
        Convert frame-level speaker predictions to time intervals

        Args:
            total_preds: Frame-level predictions from model, shape [num_frames, num_speakers]
            frame_duration: Duration of each frame in seconds
            start_frame: Starting frame index for processing
            end_frame: Ending frame index for processing
            threshold: Threshold for determining speaker activity

        Returns:
            time_intervals: Dictionary of time intervals in format
                          {speaker_id: [(start1, end1), (start2, end2), ...]}
        """
        time_intervals = {}

        num_frames, num_speakers = total_preds.shape

        # Process each speaker separately
        for speaker_idx in range(num_speakers):
            speaker_preds = total_preds[:, speaker_idx]
            intervals = []

            current_frame = None

            # Process frames in the specified range
            for frame_idx in range(start_frame, end_frame):
                current_active = speaker_preds[frame_idx] > threshold

                if current_active and current_frame is None:
                    current_frame = frame_idx
                elif not current_active and current_frame is not None:
                    start_time = current_frame * frame_duration
                    end_time = frame_idx * frame_duration
                    intervals.append((start_time, end_time))
                    current_frame = None

            # Handle case where segment continues to the end
            if current_frame is not None:
                start_time = current_frame * frame_duration
                end_time = num_frames * frame_duration
                intervals.append((start_time, end_time))

            # Merge adjacent intervals for the same speaker
            intervals = self._merge_intervals(intervals)

            time_intervals[f"speaker_{speaker_idx}"] = intervals

        return time_intervals

    def _merge_intervals(self, intervals, merge_gap=0.6):
        """
        Merge adjacent intervals that are close together

        Args:
            intervals: List of time intervals [(start1, end1), (start2, end2), ...]
            merge_gap: Maximum gap (in seconds) between intervals to merge them

        Returns:
            merged_intervals: List of merged time intervals
        """
        if not intervals:
            return []

        intervals.sort(key=lambda x: x[0])
        merged = []

        current_start, current_end = intervals[0]

        # Merge overlapping or close intervals
        for start, end in intervals[1:]:
            if start <= current_end + merge_gap:
                current_end = max(current_end, end)
            else:
                merged.append((current_start, current_end))
                current_start, current_end = start, end

        # Add the last interval
        merged.append((current_start, current_end))

        return merged

    def _update_intervals(self, session, current_intervals):
        """
        Update interval records and identify new intervals since last processing

        Args:
            session: Current session state dictionary
            current_intervals: Speaker intervals from current processing chunk

        Returns:
            new_intervals: New intervals that weren't present in the previous chunk
        """
        new_intervals = {}

        # Compare each speaker's current intervals with previous ones
        for speaker_id, current_interval_list in current_intervals.items():
            if speaker_id not in session["last_speaker_intervals"]:
                new_intervals[speaker_id] = current_interval_list.copy()
            else:
                last_interval_list = session["last_speaker_intervals"][speaker_id]
                new_interval_list = []

                for interval in current_interval_list:
                    is_new = True
                    for last_interval in last_interval_list:
                        if (
                            abs(interval[0] - last_interval[0]) < 0.1
                            and abs(interval[1] - last_interval[1]) < 0.1
                        ):
                            is_new = False
                            break

                    if is_new:
                        new_interval_list.append(interval)

                if new_interval_list:
                    new_intervals[speaker_id] = new_interval_list

        session["last_speaker_intervals"] = current_intervals.copy()

        for speaker_id, intervals in current_intervals.items():
            if speaker_id not in session["all_speaker_intervals"]:
                session["all_speaker_intervals"][speaker_id] = []

            for interval in intervals:
                if not self._interval_exists(
                    session["all_speaker_intervals"][speaker_id], interval
                ):
                    session["all_speaker_intervals"][speaker_id].append(interval)

        return new_intervals

    def _interval_exists(self, interval_list, interval, tolerance=0.1):
        """
        Check if a time interval already exists in the list

        Args:
            interval_list: List of existing intervals
            interval: Interval to check
            tolerance: Time tolerance in seconds for considering intervals equal

        Returns:
            bool: True if interval exists, False otherwise
        """
        for existing_interval in interval_list:
            if (
                abs(existing_interval[0] - interval[0]) < tolerance
                and abs(existing_interval[1] - interval[1]) < tolerance
            ):
                return True
        return False

    def _align_asr_with_speaker(
        self, session, asr_text, punc_text, asr_timestamps, new_intervals
    ):
        """
        Align ASR (Automatic Speech Recognition) results with speaker diarization information.

        Args:
            session: Session information containing global audio start time
            asr_text: Raw ASR text output (without punctuation, may contain spaces)
            punc_text: Punctuated text for better sentence segmentation
            asr_timestamps: List of (start_ms, end_ms) for each character in asr_text
            new_intervals: Speaker diarization intervals by speaker ID

        Returns:
            List of speaker turns with formatted text, speaker IDs, and timestamps
        """

        results = []

        asr_text = "".join(asr_text.split(" "))
        # logger.info(f"{asr_text=}")
        # logger.info(f"{punc_text=}")
        # logger.info(f"{asr_timestamps=}")
        # logger.info(f"{new_intervals=}")
        # logger.info(f"{session["global_audio_start_time"]=}")

        # Flatten speaker intervals
        speaker_segments = []
        for speaker, intervals in new_intervals.items():
            for start, end in intervals:
                speaker_segments.append(
                    {"speaker": speaker, "start": start, "end": end}
                )

        speaker_segments.sort(key=lambda x: x["start"])

        asr_text = self._merge_english_words(asr_text)
        punc_text = self._merge_english_words(punc_text)

        # Character-level time alignment
        for char, (start_ms, end_ms) in zip(asr_text, asr_timestamps):
            start_time = session["global_audio_start_time"] + start_ms / 1000
            end_time = session["global_audio_start_time"] + end_ms / 1000
            mid_time = (start_time + end_time) / 2

            assigned_speaker = "unknown"

            for seg in speaker_segments:
                if seg["start"] - 0.1 <= mid_time <= seg["end"] + 0.1:
                    assigned_speaker = seg["speaker"]
                    break

            results.append(
                {
                    "char": char,
                    "start": round(start_time, 2),
                    "end": round(end_time, 2),
                    "speaker": assigned_speaker,
                }
            )

        # Unknown speaker repair
        for i, item in enumerate(results):
            if item["speaker"] == "unknown":
                if i > 0:
                    item["speaker"] = results[i - 1]["speaker"]
                else:
                    for j in range(i + 1, len(results)):
                        if results[j]["speaker"] != "unknown":
                            item["speaker"] = results[j]["speaker"]
                            break

        # Abnormal character duration repair
        for i, item in enumerate(results):
            duration = item["end"] - item["start"]

            if duration > 1.0:
                if i > 0:
                    item["speaker"] = results[i - 1]["speaker"]

                item["start"] = round(results[i - 1]["end"], 2)

        # Speaker jitter correction
        for i in range(1, len(results) - 1):
            prev_spk = results[i - 1]["speaker"]
            curr_spk = results[i]["speaker"]
            next_spk = results[i + 1]["speaker"]

            if prev_spk == next_spk and curr_spk != prev_spk:
                results[i]["speaker"] = prev_spk

        # Sentence-level speaker voting correction
        results = self._sentence_refine_by_punctuation(asr_text, punc_text, results)

        # Format final output
        final_results = self._build_speaker_turns(results, punc_text)

        return final_results

    def _merge_english_words(self, asr_text):
        """
        Merge consecutive English letters and digits in ASR text.

        Args:
            asr_text: Input text from Automatic Speech Recognition

        Returns:
            List of tokens where English words are merged into single elements
        """

        merged = []
        buffer = []

        def flush_buffer():
            """Flush the buffer contents to the result list as a single token."""
            if not buffer:
                return

            word = "".join(x for x in buffer)
            merged.append(word)
            buffer.clear()

        for char in asr_text:
            if char.isascii() and (char.isalpha() or char.isdigit()):
                buffer.append(char)
            else:
                flush_buffer()
                merged.append(char)

        flush_buffer()

        return merged

    def _sentence_refine_by_punctuation(self, asr_text, punc_text, results):
        """
        Refine speaker segmentation using punctuation as sentence boundaries.

        Args:
            asr_text: Original ASR text without punctuation
            punc_text: Punctuated text (contains punctuation marks)
            results: List of dictionaries containing character-level results with speaker tags

        Returns:
            List of refined results with consistent speaker assignment within sentences
        """

        aligned = []
        i = 0

        # Align punctuated text with original ASR text
        for ch in punc_text:
            if i < len(asr_text) and ch == asr_text[i]:
                aligned.append({"char": ch, "punct_after": False})
                i += 1
            else:
                if aligned:
                    aligned[-1]["punct_after"] = True

        if len(aligned) != len(results):
            raise ValueError("Length mismatch: asr_text and results cannot be aligned")

        # Sentence segmentation by punctuation
        sentences = []
        current_sentence = []

        for idx, item in enumerate(results):
            current_sentence.append(item)

            if aligned[idx]["punct_after"]:
                sentences.append(current_sentence)
                current_sentence = []

        if current_sentence:
            sentences.append(current_sentence)

        # Sentence-level speaker voting correction
        final_results = []

        for sentence in sentences:
            speakers = [x["speaker"] for x in sentence]
            main_speaker = Counter(speakers).most_common(1)[0][0]

            for x in sentence:
                x["speaker"] = main_speaker

            final_results.extend(sentence)

        return final_results

    def _build_speaker_turns(self, results, punc_text):
        """
        Build speaker turns from character-level results and punctuated text.

        Args:
            results: List of character-level results with speaker, timing, and text info
            punc_text: Punctuated text for proper text reconstruction

        Returns:
            List of speaker turn dictionaries, each containing:
                - speaker_id: Speaker identifier
                - start_time: Formatted start time (HH:MM:SS.ss)
                - end_time: Formatted end time (HH:MM:SS.ss)
                - text: Complete text for this speaker turn (with punctuation)
        """

        turns = []
        current_turn = {
            "speaker_id": None,
            "start_time": None,
            "end_time": None,
            "text": "",
        }

        i = 0
        prev_end = ""

        for item in results:
            item["start"] = (
                f"{int(item['start'] // 3600):02d}:{int((item['start'] % 3600) // 60):02d}:{(item['start'] % 60):05.2f}"
            )
            item["end"] = (
                f"{int(item['end'] // 3600):02d}:{int((item['end'] % 3600) // 60):02d}:{(item['end'] % 60):05.2f}"
            )
            char = item["char"]

            if current_turn["speaker_id"] is None:
                current_turn["speaker_id"] = item["speaker"]
                current_turn["start_time"] = item["start"]

            if item["speaker"] != current_turn["speaker_id"]:
                current_turn["end_time"] = prev_end
                turns.append(current_turn)

                current_turn = {
                    "speaker_id": item["speaker"],
                    "start_time": item["start"],
                    "end_time": None,
                    "text": "",
                }

            while i < len(punc_text) and punc_text[i] != char:
                current_turn["text"] += punc_text[i]
                i += 1

            current_turn["text"] += char
            i += 1

            prev_end = item["end"]

        if current_turn["speaker_id"] is not None:
            current_turn["end_time"] = prev_end
            turns.append(current_turn)

        return turns


def load_model(model_path: str):
    """Load speaker diarization model"""
    global model_diar, autocast, diarization_manager

    logger.info(f"Loading diarization model from {model_path}")

    model_diar = SortformerEncLabelModel.restore_from(
        restore_path=model_path,
        map_location="cuda" if torch.cuda.is_available() else "cpu",
        strict=False,
    )
    model_diar.eval()

    if torch.cuda.is_available():
        model_diar.to(torch.device("cuda"))

    autocast = torch.amp.autocast(model_diar.device.type, enabled=True)

    diarization_manager = StreamingSpeakerDiarization(model_diar)

    logger.info("Diarization model loaded successfully")
    return model_diar


@app.on_event("startup")
async def startup_event():
    """Load model when application starts"""
    load_model(args.diar_model)


@app.get("/health")
async def health_check():
    """Health check endpoint for service monitoring"""
    return {
        "status": "healthy",
        "service": "speaker-diarization-service",
        "model_loaded": model_diar is not None,
    }


@app.get("/info")
async def server_info():
    """Get server configuration information"""
    return {
        "host": args.host,
        "port": args.port,
        "diar_model": args.diar_model,
    }


@app.post("/v1/speaker/diarize", response_model=DiarizationResponse)
async def diarize_audio(request: AudioRequest):
    """Speaker diarization endpoint - identifies different speakers in audio"""
    if diarization_manager is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        # Decode base64 audio data
        audio_bytes = base64.b64decode(request.audio_data)

        # Process audio through diarization manager
        segments = await diarization_manager.process_audio_chunk(
            session_id=request.session_id,
            audio_data=audio_bytes,
            asr_text=request.asr_text,
            punc_text=request.punc_text,
            timestamps=request.timestamps,
        )
        return DiarizationResponse(
            segments=segments, session_id=request.session_id, status="success"
        )
    except Exception as e:
        logger.error(f"Error in diarization: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


if __name__ == "__main__":
    # Start the web server
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
