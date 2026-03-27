#!/usr/bin/env python3
"""Tests for manifest-based helpers in cross_verify_frames.py."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import cross_verify_frames as cv


class CrossVerifyManifestTests(unittest.TestCase):
    def test_load_manifest_skips_blank_and_invalid_lines(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            manifest = tmp / "manifest.jsonl"
            lines = [
                json.dumps({"v": 2, "path": "frames/a.jpg", "format": "JPEG"}),
                "",
                "NOT JSON",
                json.dumps({"v": 2, "path": "videos/b.avi", "format": "AVI"}),
            ]
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records = cv.load_manifest(manifest)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["path"], "frames/a.jpg")
            self.assertEqual(records[1]["path"], "videos/b.avi")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_build_video_spans_from_manifest(self):
        records = [
            {"v": 2, "path": "frames/f.jpg", "format": "JPEG",
             "source_offset": 100, "source_end": 200},
            {"v": 2, "path": "videos/v.avi", "format": "AVI",
             "source_offset": 1000, "source_end": 5000},
            {"v": 2, "path": "videos/w.avi", "format": "AVI",
             "source_offset": 8000, "source_end": 12000},
        ]
        spans = cv.build_video_spans(records)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0], (1000, 5000, "videos/v.avi"))
        self.assertEqual(spans[1], (8000, 12000, "videos/w.avi"))

    def test_build_frame_offsets_from_manifest(self):
        records = [
            {"v": 2, "path": "frames/frame_001.jpg", "format": "JPEG",
             "source_offset": 100, "source_end": 200,
             "jpeg": {"matches_skip_frame_resolution": True}},
            {"v": 2, "path": "photos/photo_001.jpg", "format": "JPEG",
             "source_offset": 500, "source_end": 900,
             "jpeg": {"matches_skip_frame_resolution": False}},
            {"v": 2, "path": "videos/v.avi", "format": "AVI",
             "source_offset": 1000, "source_end": 5000},
        ]
        offsets = cv.build_frame_offsets(records)
        # Only JPEGs with matches_skip_frame_resolution should appear
        self.assertIn("frame_001.jpg", offsets)
        self.assertNotIn("photo_001.jpg", offsets)
        self.assertNotIn("v.avi", offsets)
        self.assertEqual(offsets["frame_001.jpg"], (100, 200))

    def test_classify_orphan_regions_groups_nearby_frames(self):
        # Two frames close together (< 5 MB gap) → one region.
        # One frame far away → separate region.
        frame_offsets = {
            "a.jpg": (1_000_000, 1_010_000),      # ~1 MB
            "b.jpg": (2_000_000, 2_010_000),      # ~2 MB (1 MB gap from a)
            "c.jpg": (50_000_000, 50_010_000),    # ~50 MB (48 MB gap from b)
        }
        orphaned = ["a.jpg", "b.jpg", "c.jpg"]
        regions = cv.classify_orphan_regions(orphaned, frame_offsets)
        self.assertEqual(len(regions), 2)
        # First region has a and b
        self.assertEqual(regions[0]["frame_count"], 2)
        # Second region has c
        self.assertEqual(regions[1]["frame_count"], 1)


if __name__ == "__main__":
    unittest.main()
