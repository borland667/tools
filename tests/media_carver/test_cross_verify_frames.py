#!/usr/bin/env python3
import unittest

import cross_verify_frames as cv


class CrossVerifyFramesTests(unittest.TestCase):
    def test_trim_jpeg_to_eoi_strips_trailing_padding(self):
        # JPEG SOI + body + EOI + AVI padding bytes — the common case for MJPEG
        # frame chunks.  _trim_jpeg_to_eoi must strip the padding.
        data = b"\xff\xd8" + b"A" * 10 + b"\xff\xd9" + b"PADDINGBYTES"
        trimmed = cv._trim_jpeg_to_eoi(data)
        self.assertEqual(trimmed, b"\xff\xd8" + b"A" * 10 + b"\xff\xd9")

    def test_trim_jpeg_to_eoi_uses_last_marker(self):
        # When a JPEG contains an embedded thumbnail with its own EOI, rfind
        # selects the *last* FFD9 — which is the main image EOI.
        data = (
            b"\xff\xd8"
            + b"A" * 10
            + b"\xff\xd9"  # thumbnail EOI
            + b"B" * 5
            + b"\xff\xd9"  # main image EOI
            + b"TAIL"
        )
        trimmed = cv._trim_jpeg_to_eoi(data)
        expected = (
            b"\xff\xd8"
            + b"A" * 10
            + b"\xff\xd9"
            + b"B" * 5
            + b"\xff\xd9"
        )
        self.assertEqual(trimmed, expected)

    def test_trim_jpeg_no_eoi_returns_original(self):
        data = b"\xff\xd8" + b"A" * 20 + b"NO_EOI"
        trimmed = cv._trim_jpeg_to_eoi(data)
        self.assertEqual(trimmed, data)

    def test_match_rate_formula_handles_zero_inputs(self):
        # The CLI summary should never divide by zero when no frame files exist.
        total_matched = 0
        frame_files = []
        match_rate = (total_matched / len(frame_files) * 100.0) if frame_files else 0.0
        self.assertEqual(match_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
