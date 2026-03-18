import argparse
import base64
import json
import uuid
from typing import Any, Dict, Set

import aiohttp
import uvicorn
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from funasr import AutoModel
from itn.chinese.inverse_normalizer import InverseNormalizer
from loguru import logger

app = FastAPI()
router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = None


def args_parser():
    """Parse command line arguments for ASR server configuration."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="127.0.0.1", help="host ip")
    parser.add_argument("--port", type=int, default=9009, help="grpc server port")
    parser.add_argument(
        "--diarization-url",
        type=str,
        default="http://127.0.0.1:8009/v1/speaker/diarize",
        help="Speaker diarization service URL",
    )
    parser.add_argument(
        "--asr-model",
        type=str,
        default="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    )
    parser.add_argument(
        "--asr-model-revision",
        type=str,
        default="v2.0.4",
    )
    parser.add_argument(
        "--asr-model-online",
        type=str,
        default="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    )
    parser.add_argument("--asr-model-online-revision", type=str, default="v2.0.4")
    parser.add_argument(
        "--vad-model", type=str, default="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    )
    parser.add_argument("--vad-model-revision", type=str, default="v2.0.4")
    parser.add_argument(
        "--punc-model",
        type=str,
        default="iic/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727",
    )
    parser.add_argument("--punc-model-revision", type=str, default="v2.0.4")
    parser.add_argument(
        "--lm-model",
        type=str,
        default="iic/speech_ngram_lm_zh-cn-ai-wesp-fst",
    )
    parser.add_argument(
        "--itn-model",
        type=str,
        # default="thuduj12/fst_itn_zh",
        default="/usr/local/lib/python3.10/dist-packages/itn",
    )
    parser.add_argument("--ncpu", type=int, default=4, help="cpu cores")
    parser.add_argument("--ngpu", type=int, default=0, help="0 for cpu, 1 for gpu")
    parser.add_argument("--device", type=str, default="cpu", help="cuda, cpu")
    parser.add_argument(
        "--ssl-cert",
        type=str,
        default="../../web/cert.pem",
        required=False,
        help="certfile for ssl",
    )
    parser.add_argument(
        "--ssl-key",
        type=str,
        default="../../web/key.pem",
        required=False,
        help="keyfile for ssl",
    )
    args = parser.parse_args()
    return args


args = args_parser()


def load_models():
    """Load all ASR and related models into memory."""
    global model_asr, model_asr_streaming, model_vad, model_punc, model_itn, manager

    model_asr = AutoModel(
        model=args.asr_model,
        ngpu=args.ngpu,
        ncpu=args.ncpu,
        device=args.device,
        disable_pbar=True,
        disable_log=True,
        disable_update=True,
    )

    model_asr_streaming = AutoModel(
        model=args.asr_model_online,
        ngpu=args.ngpu,
        ncpu=args.ncpu,
        device=args.device,
        disable_pbar=True,
        disable_log=True,
        disable_update=True,
    )

    model_vad = AutoModel(
        model=args.vad_model,
        ngpu=args.ngpu,
        ncpu=args.ncpu,
        device=args.device,
        disable_pbar=True,
        disable_log=True,
        disable_update=True,
    )

    model_punc = AutoModel(
        model=args.punc_model,
        ngpu=args.ngpu,
        ncpu=args.ncpu,
        device=args.device,
        disable_pbar=True,
        disable_log=True,
        disable_update=True,
    )

    model_itn = InverseNormalizer(cache_dir=args.itn_model)

    manager = ConnectionManager()

    logger.info("ASR models loaded successfully")
    return model_asr, model_asr_streaming, model_vad, model_punc, model_itn


model_asr, model_asr_streaming, model_vad, model_punc, model_itn = (
    None,
    None,
    None,
    None,
    None,
)


class ConnectionManager:
    """Manages WebSocket connections and their associated data."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_data: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection and initialize session data."""
        await websocket.accept(subprotocol="binary")
        self.active_connections.add(websocket)

        session_id = str(uuid.uuid4())
        logger.info(f"Session {session_id} opened.")

        self.connection_data[websocket] = {
            "session_id": session_id,
            "status_dict_asr": {},
            "status_dict_asr_online": {"cache": {}, "is_final": False},
            "status_dict_vad": {"cache": {}, "is_final": False},
            "status_dict_punc": {"cache": {}},
            "chunk_interval": 10,
            "vad_pre_idx": 0,
            "wav_name": "microphone",
            "mode": "2pass",
            "is_speaking": False,
            "frames": [],
            "frames_asr": [],
            "frames_asr_online": [],
            "speech_start": False,
            "speech_end_i": -1,
            "start_time": -1,
            "end_time": -1,
            "speaker_id": "-1",
        }

        logger.info(
            f"New user connected. Total connections: {len(self.active_connections)}",
            flush=True,
        )

    def disconnect(self, websocket: WebSocket):
        """Clean up resources when WebSocket disconnects."""
        session_id = self.connection_data[websocket]["session_id"]
        logger.info(f"Session {session_id} closed.")
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_data:
            del self.connection_data[websocket]
        logger.info(
            f"User disconnected. Total connections: {len(self.active_connections)}",
            flush=True,
        )

    def connect_reset(self, websocket: WebSocket):
        """Reset connection state while keeping the connection alive."""
        data = self.connection_data[websocket]
        data["status_dict_asr_online"]["cache"] = {}
        data["status_dict_asr_online"]["is_final"] = True
        data["status_dict_vad"]["cache"] = {}
        data["status_dict_vad"]["is_final"] = True
        data["status_dict_punc"]["cache"] = {}


async def call_diarization_service(
    session_id: str,
    audio_data: bytes,
    asr_text: str = "",
    punc_text: str = "",
    timestamps: list = None,
):
    """Call external speaker diarization service to identify different speakers."""
    try:
        payload = {
            "audio_data": base64.b64encode(audio_data).decode("utf-8"),
            "session_id": session_id,
            "asr_text": asr_text,
            "punc_text": punc_text,
            "timestamps": timestamps if timestamps else [],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                args.diarization_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("segments", [])
                else:
                    logger.error(f"Diarization service error: {response.status}")
                    return []
    except Exception as e:
        logger.error(f"Error calling diarization service: {str(e)}")
        return []


async def async_vad(websocket: WebSocket, audio_in: bytes):
    """Perform voice activity detection on audio chunk in streaming mode."""
    data = manager.connection_data[websocket]
    segments_result = model_vad.generate(input=audio_in, **data["status_dict_vad"])[0][
        "value"
    ]

    speech_start, speech_end = -1, -1

    if len(segments_result) == 0 or len(segments_result) > 1:
        return speech_start, speech_end

    if segments_result[0][0] != -1:
        speech_start = segments_result[0][0]
        start_time = speech_start / 1000.0
        data["start_time"] = (
            f"{int(start_time // 3600):02d}:{int((start_time % 3600) // 60):02d}:{(start_time % 60):05.2f}"
        )
        logger.info(f"vad start time: {start_time}")

    if segments_result[0][1] != -1:
        speech_end = segments_result[0][1]
        end_time = speech_end / 1000.0
        data["end_time"] = (
            f"{int(end_time // 3600):02d}:{int((end_time % 3600) // 60):02d}:{(end_time % 60):05.2f}"
        )
        logger.info(f"vad end time: {end_time}")

    # logger.info(f"vad frame: {speech_start} - {speech_end}")
    return speech_start, speech_end


async def async_asr(websocket: WebSocket, audio_in: bytes):
    """Perform offline ASR with full audio context."""
    data = manager.connection_data[websocket]

    asr_result, punc_result, itn_result = "", "", ""
    if len(audio_in) > 0:
        asr_result = model_asr.generate(
            input=audio_in,
            **data["status_dict_asr"],
        )
        # logger.info(f"asr results: {asr_result}")

        if model_punc is not None and len(asr_result[0]["text"]) > 0:
            punc_result = model_punc.generate(
                input=asr_result[0]["text"], **data["status_dict_punc"]
            )
            # logger.info(f"punc results: {punc_result}")

        speaker_segments = await call_diarization_service(
            session_id=data["session_id"],
            audio_data=audio_in,
            asr_text=asr_result[0]["text"] if asr_result else "",
            punc_text=punc_result[0]["text"] if punc_result else "",
            timestamps=asr_result[0].get("timestamp", []) if asr_result else [],
        )
        # logger.info(f"sd results: {speaker_segments}")

        for segment in speaker_segments:
            if model_itn is not None and len(segment["text"]) > 0:
                itn_result = model_itn.normalize(segment["text"])
                # logger.info(f"itn results: {itn_result}")

            if len(itn_result) > 0:
                mode = "2pass-offline" if "2pass" in data["mode"] else data["mode"]
                message = json.dumps(
                    {
                        "mode": mode,
                        "text": itn_result,
                        "wav_name": data["wav_name"],
                        "is_final": data["is_speaking"],
                        "start_time": segment["start_time"],
                        "end_time": segment["end_time"],
                        "speaker_id": segment["speaker_id"],
                    },
                    ensure_ascii=False,
                )

                logger.info(f"ASR offline send: {message}")
                await websocket.send_text(message)

                data["start_time"] = -1

    else:
        mode = "2pass-offline" if "2pass" in data["mode"] else data["mode"]
        message = json.dumps(
            {
                "mode": mode,
                "text": "",
                "wav_name": data["wav_name"],
                "is_final": data["is_speaking"],
                "start_time": data["start_time"],
                "end_time": data["end_time"],
                "speaker_id": data["speaker_id"],
            },
            ensure_ascii=False,
        )

        logger.info(f"Empty ASR result: {message}")
        await websocket.send_text(message)

        data["start_time"] = -1


async def async_asr_online(websocket: WebSocket, audio_in: bytes):
    """Perform streaming ASR on audio chunk."""
    data = manager.connection_data[websocket]

    if len(audio_in) > 0:
        rec_result = model_asr_streaming.generate(
            input=audio_in, **data["status_dict_asr_online"]
        )[0]

        if data["mode"] == "2pass" and data["status_dict_asr_online"].get(
            "is_final", False
        ):
            return

        if len(rec_result["text"]):
            mode = "2pass-online" if "2pass" in data["mode"] else data["mode"]
            message = json.dumps(
                {
                    "mode": mode,
                    "text": rec_result["text"],
                    "wav_name": data["wav_name"],
                    "is_final": data["is_speaking"],
                    "start_time": data["start_time"],
                    "end_time": data["end_time"],
                    "speaker_id": "-1",
                },
                ensure_ascii=False,
            )

            logger.info(f"ASR online send: {message}")
            await websocket.send_text(message)

            data["start_time"] = -1
            data["end_time"] = -1


async def streaming_asr(data: Dict, audio_data: bytes, websocket: WebSocket):
    """Main streaming ASR processing pipeline for each audio chunk."""
    data["frames"].append(audio_data)
    duration_ms = len(audio_data) // 32
    data["vad_pre_idx"] += duration_ms

    data["frames_asr_online"].append(audio_data)
    data["status_dict_asr_online"]["is_final"] = data["speech_end_i"] != -1

    if (
        len(data["frames_asr_online"]) % data["chunk_interval"] == 0
        or data["status_dict_asr_online"]["is_final"]
    ):
        if data["mode"] == "2pass" or data["mode"] == "online":
            audio_in = b"".join(data["frames_asr_online"])
            try:
                await async_asr_online(websocket, audio_in)
            except Exception as e:
                logger.error(f"Error in ASR streaming: {e}")
        data["frames_asr_online"] = []

    if data["speech_start"]:
        data["frames_asr"].append(audio_data)

    try:
        speech_start_i, speech_end_i = await async_vad(
            websocket,
            audio_data,
        )
    except Exception as e:
        logger.error(f"Error in VAD: {e}")
        speech_start_i, speech_end_i = -1, -1

    data["speech_end_i"] = speech_end_i

    if speech_start_i != -1:
        data["speech_start"] = True
        beg_bias = (data["vad_pre_idx"] - speech_start_i) // duration_ms
        frames_pre = data["frames"][-beg_bias:] if beg_bias > 0 else []
        data["frames_asr"] = []
        data["frames_asr"].extend(frames_pre)

    if data["speech_end_i"] != -1 or not data["is_speaking"]:
        if data["mode"] == "2pass" or data["mode"] == "offline":
            audio_in = b"".join(data["frames_asr"])
            try:
                await async_asr(websocket, audio_in)
            except Exception as e:
                logger.error(f"Error in ASR offline: {e}")

        data["frames_asr"] = []
        data["speech_start"] = False
        data["frames_asr_online"] = []
        data["status_dict_asr_online"]["cache"] = {}

        if not data["is_speaking"]:
            data["vad_pre_idx"] = 0
            data["frames"] = []
            data["status_dict_vad"]["cache"] = {}
        else:
            data["frames"] = data["frames"][-20:]


@app.on_event("startup")
async def startup_event():
    """Load models when FastAPI application starts."""
    load_models()


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "asr-websocket-service",
        "model_loaded": model_asr is not None,
    }


@router.get("/info")
async def server_info():
    """Endpoint to get server configuration information."""
    return {
        "host": args.host,
        "port": args.port,
        "asr_model": args.asr_model,
        "asr_model_online": args.asr_model_online,
        "vad_model": args.vad_model,
        "punc_model": args.punc_model,
        "diarization_service": args.diarization_url,
        "device": args.device,
    }


@router.websocket("/v1/audio/streaming_asr")
async def websocket_endpoint(
    websocket: WebSocket,
):
    """Main WebSocket endpoint for streaming ASR."""
    await manager.connect(websocket)
    data = manager.connection_data[websocket]

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                manager.connect_reset(websocket)
                manager.disconnect(websocket)
                # logger.info("Client disconnected")
                break

            if "text" in message:
                message_text = message["text"]
                message_json = json.loads(message_text)

                logger.info(f"Received control message: {message_json}")

                if "is_speaking" in message_json:
                    data["is_speaking"] = message_json["is_speaking"]
                    data["status_dict_asr_online"]["is_final"] = not data["is_speaking"]
                if "chunk_interval" in message_json:
                    data["chunk_interval"] = message_json["chunk_interval"]
                if "wav_name" in message_json:
                    data["wav_name"] = message_json.get("wav_name")
                if "chunk_size" in message_json:
                    chunk_size = message_json["chunk_size"]
                    if isinstance(chunk_size, str):
                        chunk_size = chunk_size.split(",")
                    data["status_dict_asr_online"]["chunk_size"] = [
                        int(x) for x in chunk_size
                    ]
                if "encoder_chunk_look_back" in message_json:
                    data["status_dict_asr_online"]["encoder_chunk_look_back"] = (
                        message_json["encoder_chunk_look_back"]
                    )
                if "decoder_chunk_look_back" in message_json:
                    data["status_dict_asr_online"]["decoder_chunk_look_back"] = (
                        message_json["decoder_chunk_look_back"]
                    )
                if "hotword" in message_json:
                    data["status_dict_asr"]["hotword"] = message_json["hotwords"]
                if "mode" in message_json:
                    data["mode"] = message_json["mode"]

                if "chunk_size" in data["status_dict_asr_online"]:
                    data["status_dict_vad"]["chunk_size"] = int(
                        data["status_dict_asr_online"]["chunk_size"][1]
                        * 60
                        / data["chunk_interval"]
                    )

            elif "bytes" in message:
                audio_data = message["bytes"]
                # logger.info(f"receive bytes: {len(audio_data)}")
                await streaming_asr(data, audio_data, websocket)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")


app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(
        "streaming_asr_wss:app",
        host=args.host,
        port=args.port,
        timeout_keep_alive=120,
        workers=1,
        reload=False,
        ssl_certfile=args.ssl_cert if hasattr(args, "ssl_cert") else None,
        ssl_keyfile=args.ssl_key if hasattr(args, "ssl_key") else None,
        ws_ping_interval=None,
        ws="websockets",
        loop="asyncio",
    )
