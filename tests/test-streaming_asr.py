import argparse
import asyncio
import json
import logging
import os
import ssl
import wave
from multiprocessing import Process

import websockets

logging.basicConfig(level=logging.ERROR)


def args_parser():
    """Parse command line arguments for the speech recognition client."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host", type=str, default="127.0.0.1", required=False, help="host ip"
    )
    parser.add_argument(
        "--port", type=int, default=9009, required=False, help="server port"
    )
    parser.add_argument(
        "--chunk_size",
        type=str,
        default="5, 10, 5",
    )
    parser.add_argument(
        "--chunk_interval",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--hotword",
        type=str,
        default="",
        help="hotword file path, one hotword perline (e.g.:测试 20)",
    )
    parser.add_argument("--audio_in", type=str, default="./data/speaker_diarization.wav")
    parser.add_argument(
        "--audio_fs",
        type=int,
        default=16000,
    )
    parser.add_argument(
        "--send_without_sleep",
        action="store_true",
        default=True,
        help="if audio_in is set, send_without_sleep",
    )
    parser.add_argument("--thread_num", type=int, default=1)
    parser.add_argument("--words_max_print", type=int, default=10000)
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--ssl", type=int, default=1, help="1 for ssl connect, 0 for no ssl"
    )
    parser.add_argument(
        "--use_itn", type=int, default=1, help="1 for using itn, 0 for not itn"
    )
    parser.add_argument(
        "--mode", type=str, default="2pass", help="offline, online, 2pass"
    )

    args = parser.parse_args()

    args.chunk_size = [int(x) for x in args.chunk_size.split(",")]
    return args


args = args_parser()
print(f"Configuration: {args}")

# Global flag to track completion of offline recognition
offline_msg_done = False


# Create output directory if specified
if args.output_dir is not None:
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)


def handle_hotword():
    """Load and parse hotwords from file."""
    fst_dict = {}
    hotword_msg = ""
    if args.hotword.strip() != "":
        f_scp = open(args.hotword)
        hot_lines = f_scp.readlines()
        for line in hot_lines:
            words = line.strip().split(" ")
            if len(words) < 2:
                print("Please checkout format of hotwords")
                continue
            try:
                # Join all words except last as hotword, last as boost score
                fst_dict[" ".join(words[:-1])] = int(words[-1])
            except ValueError:
                print("Please checkout format of hotwords")
        hotword_msg = json.dumps(fst_dict)
        print(hotword_msg)
    return hotword_msg


async def record_from_scp(chunk_begin, chunk_size):
    """Read audio files and send them to WebSocket server in chunks."""
    # Load audio file list
    if args.audio_in.endswith(".scp"):
        f_scp = open(args.audio_in)
        wavs = f_scp.readlines()
    else:
        wavs = [args.audio_in]

    # Load hotwords
    hotword_msg = handle_hotword()

    # Default audio parameters
    sample_rate = args.audio_fs
    wav_format = "pcm"
    use_itn = True if args.use_itn == 1 else False

    # Slice audio list based on chunk parameters
    if chunk_size > 0:
        wavs = wavs[chunk_begin : chunk_begin + chunk_size]

    # Process each audio file
    for wav in wavs:
        wav_splits = wav.strip().split()

        wav_name = wav_splits[0] if len(wav_splits) > 1 else "demo"
        wav_path = wav_splits[1] if len(wav_splits) > 1 else wav_splits[0]

        if not len(wav_path.strip()) > 0:
            continue

        # Read audio file based on format
        if wav_path.endswith(".pcm"):
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
        elif wav_path.endswith(".wav"):
            with wave.open(wav_path, "rb") as wav_file:
                params = wav_file.getparams()
                sample_rate = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())
                audio_bytes = bytes(frames)
        else:
            wav_format = "others"
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()

        # Calculate chunking parameters
        stride = int(
            60 * args.chunk_size[1] / args.chunk_interval / 1000 * sample_rate * 2
        )
        chunk_num = (len(audio_bytes) - 1) // stride + 1

        # Send initialization message
        message = json.dumps(
            {
                "mode": args.mode,
                "chunk_size": args.chunk_size,
                "chunk_interval": args.chunk_interval,
                "audio_fs": sample_rate,
                "wav_name": wav_name,
                "wav_format": wav_format,
                "is_speaking": True,
                "hotwords": hotword_msg,
                "itn": use_itn,
            }
        )

        await websocket.send(message)
        is_speaking = True

        # Send audio data in chunks
        for i in range(chunk_num):
            beg = i * stride
            data = audio_bytes[beg : beg + stride]
            message = data
            await websocket.send(message)

            # Send end-of-speech message for last chunk
            if i == chunk_num - 1:
                is_speaking = False
                message = json.dumps({"is_speaking": is_speaking})
                await websocket.send(message)

            # Calculate sleep duration based on mode
            sleep_duration = (
                0.001
                if args.mode == "offline"
                else 60 * args.chunk_size[1] / args.chunk_interval / 1000
            )

            await asyncio.sleep(sleep_duration)

    # Additional wait for online modes to ensure all results are received
    if not args.mode == "offline":
        await asyncio.sleep(2)

    # Wait for offline recognition to complete
    if args.mode == "offline":
        global offline_msg_done
        while not offline_msg_done:
            await asyncio.sleep(1)

    await websocket.close()


async def message(id):
    """Receive and process messages from WebSocket server."""
    global websocket, offline_msg_done
    text_print = ""
    text_print_2pass_online = ""
    text_print_2pass_offline = ""
    pre_start_time = ""
    punctuation_set = {
        "，", "。", "、", "；", "：", "！", "？", ",", ".", "!", "?", ";", ":", " ",
    }

    # Open output file if output directory specified
    if args.output_dir is not None:
        ibest_writer = open(
            os.path.join(args.output_dir, "text.{}".format(id)), "a", encoding="utf-8"
        )
    else:
        ibest_writer = None

    try:
        # Continuously receive messages
        while True:
            meg = await websocket.recv()
            meg = json.loads(meg)

            mode = meg.get("mode", "")
            text = meg["text"]
            wav_name = meg.get("wav_name", "")
            offline_msg_done = meg.get("is_final", False)
            start_time = meg["start_time"]
            end_time = meg["end_time"]
            speaker_id = meg.get("speaker_id", "")
            timestamp = ""

            if "timestamp" in meg:
                timestamp = meg["timestamp"]

            # Write results to file
            if ibest_writer is not None:
                if timestamp != "":
                    text_write_line = "{}\t{}\t{}\n".format(wav_name, text, timestamp)
                else:
                    text_write_line = "{}\t{}\n".format(wav_name, text)
                ibest_writer.write(text_write_line)

            if "mode" not in meg:
                continue

            # Handle different recognition modes
            if meg["mode"] == "online":
                text_print += "{}".format(text)
                text_print = text_print[-args.words_max_print :]
                os.system("clear")
                print("\rpid" + str(id) + ": " + text_print)

            elif meg["mode"] == "offline":
                if timestamp != "":
                    text_print += "{} timestamp: {}".format(text, timestamp)
                else:
                    text_print += "{}".format(text)

                print("\rpid" + str(id) + ": " + wav_name + ": " + text_print)
                offline_msg_done = True

            else:
                if mode == "2pass-online":
                    if start_time and start_time != -1:
                        pre_start_time = start_time
                        text_print_2pass_online += "【{} - 】: {}".format(
                            pre_start_time, text
                        )
                    else:
                        text_print_2pass_online += "{}".format(text)
                    text_print = (
                        text_print_2pass_offline + "\n" + text_print_2pass_online
                    )
                elif mode == "2pass-offline":
                    if start_time and start_time != -1:
                        pre_start_time = start_time

                    text_stripped = text.strip()
                    text_print_2pass_online = ""
                    if text_stripped and text_stripped[0] in punctuation_set:
                        text_print_2pass_offline += text_stripped[0]
                        text_print_2pass_offline += "\n【{} - {}】{}: {}".format(
                            pre_start_time, end_time, speaker_id, text_stripped[1:]
                        )
                    else:
                        text_print_2pass_offline += "\n【{} - {}】{}: {}".format(
                            pre_start_time, end_time, speaker_id, text
                        )
                    text_print = text_print_2pass_offline
                    pre_start_time = ""

                text_print = text_print[-args.words_max_print :]
                os.system("clear")
                print("\rpid" + str(id) + ": " + text_print)

    except Exception as e:
        print("Exception:", e)


async def ws_client(id, chunk_begin, chunk_size):
    """WebSocket client main function."""
    global websocket, offline_msg_done

    # Process each audio file assigned to this client
    for i in range(chunk_begin, chunk_begin + chunk_size):
        offline_msg_done = False

        # Configure SSL if enabled
        if args.ssl == 1:
            ssl_context = ssl.SSLContext()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = "wss://{}:{}/v1/audio/streaming_asr".format(args.host, args.port)
        else:
            uri = "ws://{}:{}/v1/audio/streaming_asr".format(args.host, args.port)
            ssl_context = None

        print("connect to", uri)

        # Establish WebSocket connection
        async with websockets.connect(
            uri, subprotocols=["binary"], ping_interval=None, ssl=ssl_context
        ) as websocket:
            # Create concurrent tasks for sending and receiving
            task = asyncio.create_task(record_from_scp(i, 1))
            task2 = asyncio.create_task(message(str(id) + "_" + str(i)))

            # Run both tasks concurrently
            await asyncio.gather(task, task2)

    exit(0)


def one_thread(id, chunk_begin, chunk_size):
    """Thread entry point for multiprocessing."""
    asyncio.get_event_loop().run_until_complete(ws_client(id, chunk_begin, chunk_size))
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    """Distributes audio files across multiple processes for parallel processing."""
    # Load audio file list
    if args.audio_in.endswith(".scp"):
        f_scp = open(args.audio_in)
        wavs = f_scp.readlines()
    else:
        wavs = [args.audio_in]

    total_len = len(wavs)

    # Calculate chunk size for each thread
    if total_len >= args.thread_num:
        chunk_size = int(total_len / args.thread_num)
        remain_wavs = total_len - chunk_size * args.thread_num
    else:
        chunk_size = 1
        remain_wavs = 0

    # Create and start processes
    process_list = []
    chunk_begin = 0

    for i in range(args.thread_num):
        now_chunk_size = chunk_size
        if remain_wavs > 0:
            now_chunk_size = chunk_size + 1
            remain_wavs = remain_wavs - 1

        p = Process(target=one_thread, args=(i, chunk_begin, now_chunk_size))
        chunk_begin = chunk_begin + now_chunk_size
        p.start()
        process_list.append(p)

    # Wait for all processes to complete
    for i in process_list:
        p.join()

    print("end")
