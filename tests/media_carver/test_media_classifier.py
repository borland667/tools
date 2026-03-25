#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import media_classifier as mc


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_SCRIPT = REPO_ROOT / "media_classifier.py"
PYTHON = sys.executable


class MediaClassifierTests(unittest.TestCase):
    def test_score_jpeg_low_bpp_and_mjpeg_suggests_frame(self):
        rec = {
            "bucket": "photos",
            "format": "JPEG",
            "jpeg": {"bits_per_pixel": 0.1, "inside_mjpeg_avi": True},
        }
        out = mc.score_jpeg(rec, None)
        self.assertEqual(out["suggested"], "likely_frame")

    def test_score_jpeg_common_still_and_exif_overrides_frames_bucket(self):
        rec = {
            "bucket": "frames",
            "format": "JPEG",
            "jpeg": {"matches_common_still_resolution": True, "bits_per_pixel": 1.2},
        }
        exif = {"has_camera_identity": True, "exif_readable": True}
        out = mc.score_jpeg(rec, exif)
        self.assertEqual(out["suggested"], "likely_still")

    def test_score_jpeg_mjpeg_span_suggests_frame(self):
        rec = {
            "bucket": "photos",
            "format": "JPEG",
            "jpeg": {"inside_mjpeg_avi": True},
        }
        out = mc.score_jpeg(rec, None)
        self.assertEqual(out["suggested"], "likely_frame")

    def test_score_jpeg_exif_camera_suggests_still(self):
        rec = {
            "bucket": "frames",
            "format": "JPEG",
            "jpeg": {},
        }
        exif = {"has_camera_identity": True, "has_timestamp": True, "exif_readable": True}
        out = mc.score_jpeg(rec, exif)
        self.assertEqual(out["suggested"], "likely_still")

    def test_run_classify_no_manifest_exits_error(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / ".scan_state").mkdir(parents=True)
            r = subprocess.run(
                [PYTHON, str(CLASSIFIER_SCRIPT), "-o", str(tmp)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_classify_with_manifest(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            rec = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {"width": 100, "height": 100, "inside_mjpeg_avi": False},
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(rec) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
                [PYTHON, str(CLASSIFIER_SCRIPT), "-o", str(tmp)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("JPEGs classified", r.stdout)
            rep = state / "classification_report.json"
            self.assertTrue(rep.is_file(), rep)
            data = json.loads(rep.read_text(encoding="utf-8"))
            self.assertEqual(data.get("classifier_version"), mc.CLASSIFIER_VERSION)
            self.assertEqual(len(data.get("items", [])), 1)
            self.assertEqual(data.get("skipped_entries"), [])
            self.assertIn("manifest_load_issues", data)
            self.assertEqual(data.get("manifest_load_issues"), [])
            self.assertEqual(data.get("bucket_moves"), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reorganize_buckets_default_lists_only_no_rename(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            photos = tmp / "photos"
            photos.mkdir(parents=True)
            (photos / "x.jpg").write_bytes(b"fakejpeg")
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            rec = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {
                    "width": 100,
                    "height": 100,
                    "inside_mjpeg_avi": True,
                    "matches_skip_frame_resolution": False,
                },
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(rec) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
                [
                    PYTHON,
                    str(CLASSIFIER_SCRIPT),
                    "-o",
                    str(tmp),
                    "--reorganize-buckets",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("planned only", r.stdout)
            self.assertTrue((photos / "x.jpg").is_file())
            self.assertFalse((tmp / "frames" / "x.jpg").exists())
            data = json.loads((state / "classification_report.json").read_text(encoding="utf-8"))
            self.assertFalse(data["summary"]["bucket_reorganization"]["apply_executed"])
            self.assertTrue(any(m.get("status") == "planned" for m in data["bucket_moves"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reorganize_buckets_moves_file(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            photos = tmp / "photos"
            photos.mkdir(parents=True)
            (photos / "x.jpg").write_bytes(b"fakejpeg")
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            rec = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {
                    "width": 100,
                    "height": 100,
                    "inside_mjpeg_avi": True,
                    "matches_skip_frame_resolution": False,
                },
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(rec) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
                [
                    PYTHON,
                    str(CLASSIFIER_SCRIPT),
                    "-o",
                    str(tmp),
                    "--reorganize-buckets",
                    "--apply-bucket-moves",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertIn("applied", r.stdout)
            self.assertFalse((photos / "x.jpg").exists())
            self.assertTrue((tmp / "frames" / "x.jpg").is_file())
            data = json.loads((state / "classification_report.json").read_text(encoding="utf-8"))
            self.assertTrue(data["summary"]["bucket_reorganization"]["apply_executed"])
            self.assertTrue(any(m.get("status") == "moved" for m in data["bucket_moves"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_apply_bucket_moves_requires_reorganize(self):
        r = subprocess.run(
            [PYTHON, str(CLASSIFIER_SCRIPT), "-o", "/tmp", "--apply-bucket-moves"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("apply-bucket-moves", r.stderr.lower())

    def test_plan_bucket_move_skips_uncertain(self):
        src, dest, new_rel, skip = mc.plan_bucket_move(
            Path("/tmp"), "photos/x.jpg", "uncertain"
        )
        self.assertEqual(skip, "uncertain_or_neutral_suggestion")
        self.assertIsNone(src)

    def test_load_manifest_tracks_invalid_json(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            man = tmp / "recovery_manifest.jsonl"
            man.write_text('{"format":"JPEG","path":"a.jpg"}\nnot-json\n', encoding="utf-8")
            recs, issues, blanks = mc.load_manifest(man)
            self.assertEqual(len(recs), 1)
            self.assertEqual(blanks, 0)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].get("reason"), "invalid_json")
            self.assertEqual(issues[0].get("line"), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_classify_non_jpeg_skipped_with_explanations(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            jpg = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {"width": 100, "height": 100, "inside_mjpeg_avi": False},
            }
            mp4 = {
                "v": 1,
                "path": "videos/x.mp4",
                "bucket": "videos",
                "format": "MP4",
                "extension": "mp4",
                "source_offset": 0,
                "source_end": 1000,
                "size_bytes": 1000,
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(jpg) + "\n" + json.dumps(mp4) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
                [PYTHON, str(CLASSIFIER_SCRIPT), "-o", str(tmp), "--no-report-json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("not scored", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_classify_report_lists_skipped_and_json_errors(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            jpg = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {"width": 100, "height": 100, "inside_mjpeg_avi": False},
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(jpg)
                + "\n{not valid json\n"
                + json.dumps({"format": "PNG", "path": "p.png", "bucket": "photos"})
                + "\n",
                encoding="utf-8",
            )
            r = subprocess.run(
                [PYTHON, str(CLASSIFIER_SCRIPT), "-o", str(tmp)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            rep = state / "classification_report.json"
            data = json.loads(rep.read_text(encoding="utf-8"))
            self.assertEqual(len(data["manifest_load_issues"]), 1)
            self.assertEqual(len(data["skipped_entries"]), 1)
            self.assertEqual(data["skipped_entries"][0]["reason_code"], "format_not_jpeg")
            self.assertIn("explanation", data["skipped_entries"][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_run_classify_no_report_json(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            state = tmp / ".scan_state"
            state.mkdir(parents=True)
            rec = {
                "v": 1,
                "path": "photos/x.jpg",
                "bucket": "photos",
                "format": "JPEG",
                "extension": "jpg",
                "source_offset": 0,
                "source_end": 100,
                "size_bytes": 100,
                "jpeg": {"width": 100, "height": 100, "inside_mjpeg_avi": False},
            }
            (state / "recovery_manifest.jsonl").write_text(
                json.dumps(rec) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
                [PYTHON, str(CLASSIFIER_SCRIPT), "-o", str(tmp), "--no-report-json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((state / "classification_report.json").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
