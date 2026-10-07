"""Run the local capture or virtual-device helper."""

from __future__ import annotations

import argparse
import os
import queue
import socket
import sys
import threading
import time
from contextlib import closing, suppress
from io import BytesIO
from pathlib import Path

from .protocol import (
    AUDIO,
    AUDIO_BYTES,
    CAPTURE_PORT,
    FPS,
    HEIGHT,
    READY,
    RECEIVER_PORT,
    VIDEO,
    WIDTH,
    recv_frame,
    send_frame,
    valid,
)


def _setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _device(value: str) -> str | int | None:
    if not value:
        return None
    return int(value) if value.isdecimal() else value


def _loopback_server(port: int) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    return server


def _offer(q: queue.Queue, item: tuple[int, bytes]) -> None:
    try:
        q.put_nowait(item)
    except queue.Full:
        # A stale camera frame is less useful than the next one. Keep the
        # capture callback independent of network backpressure.
        pass


def _camera_capture(out: queue.Queue, stop: threading.Event, errors: queue.Queue) -> None:
    import cv2

    index = int(_setting("CAMERA_INDEX", "0"))
    backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    camera = cv2.VideoCapture(index, backend)
    if not camera.isOpened():
        errors.put(f"Cannot open camera {index}. Check camera permission and CAMERA_INDEX.")
        return
    try:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        quality = int(_setting("JPEG_QUALITY", "55"))
        while not stop.is_set():
            started = time.monotonic()
            ok, frame = camera.read()
            if not ok:
                errors.put("Camera stopped returning frames.")
                return
            frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ok:
                data = encoded.tobytes()
                if valid(VIDEO, data):
                    _offer(out, (VIDEO, data))
                else:
                    errors.put("Camera JPEG exceeds the media frame limit. Lower JPEG_QUALITY.")
                    return
            stop.wait(max(0, 1 / FPS - (time.monotonic() - started)))
    finally:
        camera.release()


def _capture_session(conn: socket.socket, no_audio: bool, no_video: bool) -> None:
    import sounddevice as sd

    frames: queue.Queue[tuple[int, bytes]] = queue.Queue(maxsize=12)
    errors: queue.Queue[str] = queue.Queue()
    stop = threading.Event()
    camera_thread = None
    stream = None
    if not no_video:
        camera_thread = threading.Thread(target=_camera_capture, args=(frames, stop, errors), daemon=True)
        camera_thread.start()
    try:
        if not no_audio:
            last_audio_warning = [0.0]

            def audio_callback(indata, frame_count, time_info, status):
                now = time.monotonic()
                if status and now - last_audio_warning[0] >= 5:
                    print(f"Microphone: {status}", flush=True)
                    last_audio_warning[0] = now
                if frame_count == AUDIO_BYTES // 2:
                    _offer(frames, (AUDIO, bytes(indata)))

            stream = sd.RawInputStream(
                samplerate=48_000,
                blocksize=AUDIO_BYTES // 2,
                channels=1,
                dtype="int16",
                device=_device(_setting("MIC_INPUT_DEVICE")),
                callback=audio_callback,
            )
            stream.start()
        conn.settimeout(2)
        while True:
            if not errors.empty():
                raise RuntimeError(errors.get_nowait())
            try:
                kind, data = frames.get(timeout=0.5)
            except queue.Empty:
                continue
            send_frame(conn, kind, data)
    finally:
        stop.set()
        if stream is not None:
            stream.stop()
            stream.close()
        if camera_thread is not None:
            camera_thread.join(timeout=2)


def capture(no_audio: bool, no_video: bool) -> None:
    if no_audio and no_video:
        raise ValueError("At least one capture source must be enabled")
    with closing(_loopback_server(CAPTURE_PORT)) as server:
        print(f"Capture helper waiting on 127.0.0.1:{CAPTURE_PORT}. Camera and mic are idle.", flush=True)
        while True:
            conn, _ = server.accept()
            print("Desktop session connected. Capturing enabled sources.", flush=True)
            with closing(conn):
                try:
                    conn.sendall(READY)
                    _capture_session(conn, no_audio, no_video)
                except Exception as exc:
                    print(f"Capture stopped: {exc}", flush=True)
            print("Waiting for another desktop session. Camera and mic are idle.", flush=True)


class AudioOutput:
    def __init__(self, device: str):
        import sounddevice as sd

        self.frames: queue.Queue[bytes] = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.stream = sd.RawOutputStream(
            samplerate=48_000,
            blocksize=AUDIO_BYTES // 2,
            channels=2,
            dtype="int16",
            device=_device(device),
        )
        self.stream.start()
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def _write(self) -> None:
        import numpy as np

        silence = bytes(AUDIO_BYTES * 2)
        while not self.stop.is_set():
            try:
                mono = self.frames.get(timeout=0.02)
                samples = np.frombuffer(mono, dtype="<i2")
                stereo = np.repeat(samples[:, None], 2, axis=1).tobytes()
                self.stream.write(stereo)
            except queue.Empty:
                self.stream.write(silence)
            except Exception as exc:
                print(f"Virtual microphone output stopped: {exc}", flush=True)
                return

    def offer(self, frame: bytes) -> None:
        try:
            self.frames.put_nowait(frame)
        except queue.Full:
            pass

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=1)
        self.stream.stop()
        self.stream.close()


def _receive_session(conn: socket.socket, no_audio: bool, no_video: bool) -> None:
    output_name = _setting("AUDIO_OUTPUT_DEVICE")
    audio = None
    camera = None
    try:
        while True:
            kind, data = recv_frame(conn)
            if kind == AUDIO and not no_audio and output_name:
                if audio is None:
                    audio = AudioOutput(output_name)
                    print(f"Virtual microphone audio flowing through {output_name}.", flush=True)
                audio.offer(data)
            elif kind == VIDEO and not no_video:
                import numpy as np
                import pyvirtualcam
                from PIL import Image

                if camera is None:
                    camera = pyvirtualcam.Camera(
                        width=WIDTH,
                        height=HEIGHT,
                        fps=FPS,
                        fmt=pyvirtualcam.PixelFormat.RGB,
                        device=_setting("VIRTUAL_CAMERA_DEVICE") or None,
                    )
                    print(f"Virtual camera active: {camera.device}", flush=True)
                with Image.open(BytesIO(data)) as image:
                    if image.size != (WIDTH, HEIGHT):
                        raise ValueError("unexpected JPEG dimensions")
                    camera.send(np.asarray(image.convert("RGB")))
    finally:
        if camera is not None:
            import numpy as np

            with suppress(Exception):
                camera.send(np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))
            with suppress(Exception):
                camera.close()
        if audio is not None:
            audio.close()


def receive(no_audio: bool, no_video: bool) -> None:
    if no_audio and no_video:
        raise ValueError("At least one virtual device must be enabled")
    if not no_audio and not _setting("AUDIO_OUTPUT_DEVICE"):
        print("Set AUDIO_OUTPUT_DEVICE to a virtual cable output. Audio will be ignored until set.", flush=True)
    with closing(_loopback_server(RECEIVER_PORT)) as server:
        print(f"Device helper waiting on 127.0.0.1:{RECEIVER_PORT}.", flush=True)
        while True:
            conn, _ = server.accept()
            print("Desktop session connected. Feeding virtual devices.", flush=True)
            with closing(conn):
                try:
                    conn.sendall(READY)
                    _receive_session(conn, no_audio, no_video)
                except Exception as exc:
                    print(f"Device output stopped: {exc}", flush=True)
            print("Waiting for another desktop session.", flush=True)


def devices() -> None:
    import sounddevice as sd

    print(sd.query_devices())
    print("Camera indexes can be checked with your operating system's camera app.")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description="Local camera and microphone bridge for RustDesk")
    parser.add_argument("mode", choices=("capture", "receive", "devices"))
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    args = parser.parse_args()
    if args.mode == "devices":
        devices()
    elif args.mode == "capture":
        capture(args.no_audio, args.no_video)
    else:
        receive(args.no_audio, args.no_video)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
