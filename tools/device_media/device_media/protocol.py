"""Small, bounded framing protocol used only on loopback sockets."""

from __future__ import annotations

import socket
import struct

AUDIO = 1
VIDEO = 2
AUDIO_BYTES = 1_920
MAX_JPEG_BYTES = 256 * 1024
CAPTURE_PORT = 47831
RECEIVER_PORT = 47832
WIDTH = 640
HEIGHT = 480
FPS = 10
READY = b"\x01"


def valid(kind: int, data: bytes) -> bool:
    if kind == AUDIO:
        return len(data) == AUDIO_BYTES
    if kind == VIDEO:
        return 4 <= len(data) <= MAX_JPEG_BYTES and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
    return False


def send_frame(conn: socket.socket, kind: int, data: bytes) -> None:
    if not valid(kind, data):
        raise ValueError("invalid media frame")
    conn.sendall(struct.pack("!BI", kind, len(data)) + data)


def _read_exact(conn: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        part = conn.recv(size - len(result))
        if not part:
            raise EOFError("media session disconnected")
        result.extend(part)
    return bytes(result)


def recv_frame(conn: socket.socket) -> tuple[int, bytes]:
    kind, size = struct.unpack("!BI", _read_exact(conn, 5))
    maximum = AUDIO_BYTES if kind == AUDIO else MAX_JPEG_BYTES
    if size == 0 or size > maximum:
        raise ValueError("media frame too large")
    data = _read_exact(conn, size)
    if not valid(kind, data):
        raise ValueError("invalid media frame")
    return kind, data
