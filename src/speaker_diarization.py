import argparse
import asyncio
import os
import uuid
import wave

import uvicorn
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from loguru import logger
from nemo.collections.asr.models import SortformerEncLabelModel
from pydantic import BaseModel

router = APIRouter()

os.environ["CUDA_VISIBLE_DEVICES"] = "0"


def args_parser():
    parser = argparse.ArgumentParser(description="SD + ASR")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=9010)
    parser.add_argument(
        "--model-path",
        type=str,
        default="/home/workspace/models/modelscope/hub/iic/SenseVoiceSmall/",
    )
    parser.add_argument(
        "--sd-model-path",
        type=str,
        default="/root/.cache/modelscope/hub/models/diar_streaming_sortformer_4spk-v2/diar_streaming_sortformer_4spk-v2.nemo",
    )
    parser.add_argument("--ssl-cert", type=str, default="../web/cert.pem")
    parser.add_argument("--ssl-key", type=str, default="../web/key.pem")
    parser.add_argument("--language", type=str, default="zh")
    parser.add_argument("--max-gap", type=float, default=1)
    parser.add_argument("--batch-size", type=float, default=128)

    args = parser.parse_args()
    return args


args = args_parser()


class TranscriptionEvent(BaseModel):
    type: str = "TranscriptionEvent"
    session_id: str | None = None
    is_final: bool
    start_at: float
    end_at: float | None
    spk_id: str
    text: str


def create_transcriber():
    try:
        sensevoice_model = AutoModel(
            model=args.model_path,
            trust_remote_code=True,
            remote_code="./model.py",
            vad_kwargs={"max_single_segment_time": 30000},
        )
        diar_model = SortformerEncLabelModel.restore_from(
            restore_path=args.sd_model_path,
        )
        diar_model.eval()
        return sensevoice_model, diar_model
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return None, None


def merge_speaker_segments(segments, max_gap=0.5):
    if not segments:
        return []

    processed = [[float(seg[0]), float(seg[1]), seg[2]] for seg in segments]

    merged = [processed[0]]

    for current in processed[1:]:
        last = merged[-1]
        current_start, current_end, current_spk = current
        last_start, last_end, last_spk = last

        if current_spk == last_spk and (current_start - last_end) <= max_gap:
            merged[-1] = [last_start, current_end, last_spk]
        else:
            merged.append(current)

    return merged


def extract_wav_segment(input_path, output_path, start_time, end_time):
    with wave.open(input_path, "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()
        compname = wf.getcompname()

        start_frame = int(start_time * framerate)
        end_frame = int(end_time * framerate)

        total_duration = nframes / framerate
        if start_time < 0 or start_time >= end_time:
            raise ValueError(f"Error: total duration {total_duration:.3f} s")

        wf.setpos(start_frame)

        segment_frames = end_frame - start_frame
        audio_data = wf.readframes(segment_frames)

    with wave.open(output_path, "wb") as wf_out:
        wf_out.setnchannels(nchannels)
        wf_out.setsampwidth(sampwidth)
        wf_out.setframerate(framerate)
        wf_out.setnframes(segment_frames)
        wf_out.setcomptype(comptype, compname)
        wf_out.writeframes(audio_data)


sensevoice_model, diar_model = create_transcriber()


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "speaker_diarization"}


@router.websocket("/v1/audio/speaker_diarization")
async def websocket_endpoint(
    websocket: WebSocket,
):
    await websocket.accept()

    session_id = str(uuid.uuid4())
    logger.info(f"Session {session_id} opened")

    base_dir = os.path.abspath("./data")
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    temp_audio_path = os.path.join(base_dir, f"tmp-{session_id}.wav")

    with open(temp_audio_path, "wb") as f:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                logger.info("Client disconnected")
                break

            if "text" in message:
                if message["text"] == "EOF":
                    logger.info("Received EOF, closing file.")
                    break
                else:
                    continue

            if "bytes" in message:
                f.write(message["bytes"])
                logger.info(f"Receive auido data: {len(message['bytes'])} bytes")

    count = 0
    is_final = False
    try:
        predicted_segments = diar_model.diarize(audio=temp_audio_path, batch_size=3)
        aduio_output = [seg.split(" ") for seg in predicted_segments[0]]
        # logger.info(aduio_output)
        if aduio_output == []:
            response = TranscriptionEvent(
                type="Done",
                session_id=session_id,
                is_final=True,
                start_at=0.0,
                end_at=0.0,
                spk_id="",
                text="",
            )
            await websocket.send_json(response.model_dump())
            await websocket.close(code=1008)
        else:
            sorted_output = sorted(aduio_output, key=lambda x: float(x[0]))
            # logger.info(sorted_output)

            merged_segments = merge_speaker_segments(
                sorted_output, max_gap=args.max_gap
            )
            # logger.info(merged_segments)

            batch_audio_file = []
            for i, (start_s, end_s, speaker) in enumerate(merged_segments):
                output_wav = os.path.join(base_dir, f"tmp-{session_id}-{i}.wav")
                extract_wav_segment(temp_audio_path, output_wav, start_s, end_s)
                batch_audio_file.append((start_s, end_s, speaker, output_wav))

            batch_size = args.batch_size
            grouped_batches = [
                batch_audio_file[i : i + batch_size]
                for i in range(0, len(batch_audio_file), batch_size)
            ]

            for group in grouped_batches:
                audio_list = [item[3] for item in group]

                batch_results = await asyncio.to_thread(
                    sensevoice_model.generate,
                    input=audio_list,
                    cache={},
                    language=args.language,  # "zn", "en", "yue", "ja", "ko", "nospeech"
                    use_itn=True,
                    batch_size_s=256,
                    merge_vad=True,
                    merge_length_s=15,
                )

                for i, (start_s, end_s, speaker, _) in enumerate(group):
                    count += 1
                    is_final = count == len(merged_segments)
                    res = batch_results[i]
                    text = rich_transcription_postprocess(res["text"])
                    logger.info(f"{speaker}: {text}")

                    response = TranscriptionEvent(
                        session_id=session_id,
                        is_final=is_final,
                        start_at=start_s,
                        end_at=end_s,
                        spk_id=speaker,
                        text=text,
                    )
                    await websocket.send_json(response.model_dump())

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected ({session_id})")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
    finally:
        for filename in os.listdir(base_dir):
            if filename.startswith("tmp") and filename.endswith(".wav"):
                try:
                    os.remove(os.path.join(base_dir, filename))
                except Exception as e:
                    logger.warning(f"Not Found: {filename} ({e})")

        if is_final:
            await websocket.close(code=1008)

        logger.info(f"Session {session_id} closed")


if __name__ == "__main__":
    uvicorn.run(
        "speaker_diarization:router",
        host=args.host,
        port=args.port,
        timeout_keep_alive=120,
        workers=1,
        reload=False,
        ssl_certfile=args.ssl_cert,
        ssl_keyfile=args.ssl_key,
    )
