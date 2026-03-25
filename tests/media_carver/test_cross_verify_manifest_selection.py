#!/usr/bin/env python3
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import cross_verify_frames as cv


class CrossVerifyManifestSelectionTests(unittest.TestCase):
    def test_manifest_frame_candidates_and_locate_after_move(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / ".scan_state").mkdir(parents=True)
            (tmp / "frames").mkdir()
            (tmp / "photos").mkdir()

            # Carver-style manifest says this JPEG was a frame (bucket frames).
            rec = {
                "v": 1,
                "path": "frames/video_frame_00001_JPEG_1280x720_10KB.jpg",
                "bucket": "frames",
                "format": "JPEG",
                "jpeg": {"inside_mjpeg_avi": True},
            }
            (tmp / ".scan_state" / "recovery_manifest.jsonl").write_text(
                json.dumps(rec) + "\n", encoding="utf-8"
            )

            candidates = cv._manifest_frame_candidates([rec])
            self.assertEqual(candidates, ["video_frame_00001_JPEG_1280x720_10KB.jpg"])

            # File is no longer in frames/ (simulating reorg); it exists in photos/.
            moved = tmp / "photos" / candidates[0]
            moved.write_bytes(b"fakejpeg")
            located = cv._locate_by_filename(tmp, candidates[0])
            self.assertEqual(located, moved)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

