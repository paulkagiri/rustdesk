import socket
import struct
import unittest

from device_media.protocol import AUDIO, AUDIO_BYTES, MAX_JPEG_BYTES, VIDEO, recv_frame, send_frame


class ProtocolTest(unittest.TestCase):
    def test_audio_and_video_round_trip(self):
        left, right = socket.socketpair()
        try:
            audio = bytes(AUDIO_BYTES)
            jpeg = b"\xff\xd8picture\xff\xd9"
            send_frame(left, AUDIO, audio)
            send_frame(left, VIDEO, jpeg)
            self.assertEqual(recv_frame(right), (AUDIO, audio))
            self.assertEqual(recv_frame(right), (VIDEO, jpeg))
        finally:
            left.close()
            right.close()

    def test_rejects_oversize_before_reading_payload(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack("!BI", VIDEO, MAX_JPEG_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "too large"):
                recv_frame(right)
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
