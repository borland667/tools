#!/usr/bin/env python3
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import base64


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "media_carver.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PYTHON_BIN = shutil.which("python3") or "python3"


def run_cmd(args, cwd):
    return subprocess.run(
        [PYTHON_BIN, str(SCRIPT_PATH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def write_fixture_image(path: Path):
    png_b64_path = FIXTURES_DIR / "pixel_1x1.png.b64"
    png = base64.b64decode(png_b64_path.read_text().strip())
    with path.open("wb") as f:
        f.write(b"\x00" * 4096)
        f.write(png)
        f.write(b"\x11" * 2048)
        f.write(png)
        f.write(b"\x22" * 4096)


def write_fixture_video_then_jpeg(path: Path):
    jpg_b64_path = FIXTURES_DIR / "pixel_1x1.jpg.b64"
    jpg = base64.b64decode(jpg_b64_path.read_text().strip())

    # Minimal fake AVI container with valid RIFF size and AVI marker.
    # Size field is payload size excluding first 8 bytes.
    total_size = 60 * 1024
    riff_size = total_size - 8
    avi = b"RIFF" + riff_size.to_bytes(4, "little") + b"AVI " + (b"\x00" * (total_size - 12))

    with path.open("wb") as f:
        f.write(b"\x33" * 2048)
        f.write(avi)
        f.write(b"\x44" * 2048)
        f.write(jpg)
        f.write(b"\x55" * 1024)


class MediaCarverCliModesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.fixture = self.tmp_path / "fixture.img"
        self.out = self.tmp_path / "out"
        write_fixture_image(self.fixture)

    def tearDown(self):
        self.tmp.cleanup()

    def test_help_mode(self):
        result = run_cmd(["--help"], self.tmp_path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_version_mode(self):
        result = run_cmd(["--version"], self.tmp_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("media_carver", result.stdout)

    def test_report_mode_without_existing_image(self):
        missing = self.tmp_path / "missing.img"
        result = run_cmd([str(missing), "-o", str(self.out), "--report"], self.tmp_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RECOVERY REPORT", result.stdout)
        self.assertIn("Started at:", result.stdout)
        self.assertIn("Finished at:", result.stdout)
        self.assertIn("Elapsed:", result.stdout)

    def test_invalid_chunk_mb_is_rejected(self):
        result = run_cmd(
            [str(self.fixture), "-o", str(self.out), "--chunk-mb", "0"],
            self.tmp_path,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--chunk-mb must be > 0", result.stderr)

    def test_invalid_range_is_rejected(self):
        result = run_cmd(
            [str(self.fixture), "-o", str(self.out), "--start", "5", "--end", "4"],
            self.tmp_path,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--end must be greater than --start", result.stderr)

    def test_full_scan_default_strict_dedup(self):
        result = run_cmd(
            [str(self.fixture), "-o", str(self.out), "--min-size", "16", "--min-dim", "1"],
            self.tmp_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        photos = list((self.out / "photos").glob("*"))
        self.assertEqual(len(photos), 1)

        sha_file = self.out / ".scan_state" / "seen_sha256.txt"
        self.assertTrue(sha_file.exists())
        self.assertGreater(len(sha_file.read_text().strip()), 0)

    def test_range_scan_mode(self):
        result = run_cmd(
            [
                str(self.fixture),
                "-o",
                str(self.out),
                "--start",
                "0",
                "--end",
                "1",
                "--min-size",
                "16",
                "--min-dim",
                "1",
            ],
            self.tmp_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / ".scan_state" / "scan_log.txt").exists())

    def test_fast_dedup_mode(self):
        result = run_cmd(
            [
                str(self.fixture),
                "-o",
                str(self.out),
                "--fast-dedup",
                "--min-size",
                "16",
                "--min-dim",
                "1",
            ],
            self.tmp_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / ".scan_state" / "seen_hashes.txt").exists())

    def test_reset_mode(self):
        first = run_cmd(
            [str(self.fixture), "-o", str(self.out), "--min-size", "16", "--min-dim", "1"],
            self.tmp_path,
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        second = run_cmd(
            [
                str(self.fixture),
                "-o",
                str(self.out),
                "--reset",
                "--min-size",
                "16",
                "--min-dim",
                "1",
            ],
            self.tmp_path,
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        counters_path = self.out / ".scan_state" / "counters.json"
        counters = json.loads(counters_path.read_text())
        self.assertGreaterEqual(counters.get("photo", 0), 1)
        self.assertTrue((self.out / "photos" / "photo_00001_PNG_0KB.png").exists())

    def test_default_skips_jpeg_after_first_video(self):
        fixture2 = self.tmp_path / "fixture_video_then_jpg.img"
        out2 = self.tmp_path / "out_video_default_skip"
        write_fixture_video_then_jpeg(fixture2)

        result = run_cmd(
            [str(fixture2), "-o", str(out2), "--min-size", "16", "--min-dim", "1"],
            self.tmp_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        videos = list((out2 / "videos").glob("*.avi"))
        frames = list((out2 / "frames").glob("*"))
        photos = list((out2 / "photos").glob("*.jpg"))

        self.assertGreaterEqual(len(videos), 1)
        self.assertEqual(len(frames), 0)
        self.assertEqual(len(photos), 0)

    def test_keep_jpeg_after_video_routes_to_frames(self):
        fixture2 = self.tmp_path / "fixture_video_then_jpg_keep.img"
        out2 = self.tmp_path / "out_video_keep_jpeg"
        write_fixture_video_then_jpeg(fixture2)

        result = run_cmd(
            [
                str(fixture2),
                "-o",
                str(out2),
                "--keep-jpeg-after-video",
                "--min-size",
                "16",
                "--min-dim",
                "1",
            ],
            self.tmp_path,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        frames = list((out2 / "frames").glob("video_frame_*_JPEG*.jpg"))
        photos = list((out2 / "photos").glob("*.jpg"))
        self.assertGreaterEqual(len(frames), 1)
        self.assertEqual(len(photos), 0)


if __name__ == "__main__":
    unittest.main()
