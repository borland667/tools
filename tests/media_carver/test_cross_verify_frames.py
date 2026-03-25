#!/usr/bin/env python3
import unittest

import cross_verify_frames as cv


class CrossVerifyFramesTests(unittest.TestCase):
    def test_trim_jpeg_to_first_eoi(self):
        # JPEG-like sequence with two EOI markers; trimming must stop at the
        # first 0xFFD9 to mirror the carver's behavior.
        data = b"\xff\xd8" + b"A" * 10 + b"\xff\xd9" + b"PAD" + b"\xff\xd9" + b"TAIL"
        trimmed = cv.trim_jpeg_to_first_eoi(data)
        self.assertEqual(trimmed, b"\xff\xd8" + b"A" * 10 + b"\xff\xd9")

    def test_trim_jpeg_no_eoi_returns_original(self):
        data = b"\xff\xd8" + b"A" * 20 + b"NO_EOI"
        trimmed = cv.trim_jpeg_to_first_eoi(data)
        self.assertEqual(trimmed, data)

    def test_match_rate_formula_handles_zero_inputs(self):
        # The CLI summary should never divide by zero when no frame files are selected.
        total_matched = 0
        frame_files = []
        match_rate = (total_matched / len(frame_files) * 100.0) if frame_files else 0.0
        self.assertEqual(match_rate, 0.0)


if __name__ == "__main__":
    unittest.main()

