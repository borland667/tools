#!/usr/bin/env python3
import base64
import os
import struct
import tempfile
import unittest
from pathlib import Path

import media_carver as mc

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _avi_chunk(fourcc: bytes, payload: bytes) -> bytes:
    n = len(payload)
    pad = n % 2
    return fourcc + struct.pack("<I", n) + payload + (b"\x00" * pad)


def _avi_list(list_type: bytes, inner: bytes) -> bytes:
    body = list_type + inner
    return b"LIST" + struct.pack("<I", len(body)) + body


def _build_test_avi(video_handler: bytes) -> bytes:
    avih = _avi_chunk(b"avih", b"\x00" * 56)
    strh_body = b"vids" + video_handler + b"\x00" * 48
    strh = _avi_chunk(b"strh", strh_body)
    strl = _avi_list(b"strl", strh)
    hdrl = _avi_list(b"hdrl", avih + strl)
    riff_inner = b"AVI " + hdrl
    return b"RIFF" + struct.pack("<I", len(riff_inner)) + riff_inner


def _write_temp(data: bytes) -> str:
    fd, path = tempfile.mkstemp(prefix="mc_fmt_", suffix=".bin")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


class FormatHeuristicsTests(unittest.TestCase):
    def test_png_iend_rejects_invalid_ihdr(self):
        # PNG signature + IHDR with width=0 (invalid) + IEND
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = (
            b"\x00\x00\x00\x00"  # width=0 invalid
            b"\x00\x00\x00\x01"  # height=1
            b"\x08\x06\x00\x00\x00"
        )
        ihdr = (13).to_bytes(4, "big") + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
        iend = (0).to_bytes(4, "big") + b"IEND" + b"" + b"\x00\x00\x00\x00"
        blob = sig + ihdr + iend
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                end = mc._find_png_iend(f, 0, len(blob))
            self.assertIsNone(end)
        finally:
            os.unlink(path)

    def test_gif_trailer_requires_structural_blocks(self):
        # Header + LSD + bogus byte + trailer; should be rejected structurally.
        blob = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00" + b"\x7f" + b"\x3b"
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                end = mc._find_gif_trailer(f, 0, len(blob))
            self.assertIsNone(end)
        finally:
            os.unlink(path)

    def test_mpeg_ps_packet_parser_rejects_random_stream(self):
        blob = b"\x00\x00\x01\xba" + (b"\x00" * 256)
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                end = mc._find_mpeg_ps_end(f, 0, len(blob))
            self.assertIsNone(end)
        finally:
            os.unlink(path)

    def test_isobmff_requires_structure(self):
        # ftyp followed by non-printable/invalid box name should fail.
        ftyp = (24).to_bytes(4, "big") + b"ftyp" + b"isom" + b"\x00\x00\x00\x00" + b"isom"
        bad = (16).to_bytes(4, "big") + b"\x01\x02\x03\x04" + b"\x00" * 8
        blob = ftyp + bad
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                end = mc._walk_isobmff(f, 0, len(blob))
            self.assertIsNone(end)
        finally:
            os.unlink(path)

    def test_ebml_segment_search_handles_pre_segment_void(self):
        # EBML header + one void-like element + Segment with unknown size marker.
        ebml_header = b"\x1a\x45\xdf\xa3\x84\x42\x86\x81\x01"
        # Void element: id EC, size 1, payload 00
        pre = b"\xec\x81\x00"
        segment = b"\x18\x53\x80\x67\xff"
        blob = ebml_header + pre + segment + (b"\x00" * 64)
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                end = mc._walk_ebml(f, 0, len(blob))
            self.assertEqual(end, len(blob))
        finally:
            os.unlink(path)

    def test_avi_mjpeg_stream_detection_positive(self):
        blob = _build_test_avi(b"MJPG")
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                self.assertTrue(mc.avi_file_contains_mjpeg_video_stream(f, 0, len(blob)))
        finally:
            os.unlink(path)

    def test_avi_mjpeg_stream_detection_negative(self):
        blob = _build_test_avi(b"XVID")
        path = _write_temp(blob)
        try:
            with open(path, "rb") as f:
                self.assertFalse(mc.avi_file_contains_mjpeg_video_stream(f, 0, len(blob)))
        finally:
            os.unlink(path)

    def test_jpeg_marker_sof_info_fixture_pixel(self):
        jpg_b64_path = FIXTURES_DIR / "pixel_1x1.jpg.b64"
        raw = base64.b64decode(jpg_b64_path.read_text().strip())
        w, h, prog = mc.jpeg_marker_sof_info(raw)
        self.assertEqual((w, h), (1, 1))
        self.assertFalse(prog)

    def test_jpeg_compression_manifest_hints_bpp_without_sof(self):
        hints = mc.jpeg_compression_manifest_hints(b"", 20_000, 100, 100)
        self.assertAlmostEqual(hints["bits_per_pixel"], 16.0, places=3)
        self.assertFalse(hints["matches_common_still_resolution"])


if __name__ == "__main__":
    unittest.main()
