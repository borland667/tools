#!/usr/bin/env python3
"""
media_classifier.py — Second-pass classifier for media_carver output.

Reads `.scan_state/recovery_manifest.jsonl` (one JSON record per recovered file)
and suggests whether each JPEG is more likely a **still photo** or a **video frame**.

Requires a scan produced with `media_carver.py` (recovery manifest is written by
default; use `--no-recovery-manifest` on the carver to disable).

By default this tool also writes `.scan_state/classification_report.json`;
use `--no-report-json` for stdout-only runs.

Usage:
  python3 media_classifier.py -o /path/to/recovery
  python3 media_classifier.py -o /path/to/recovery --exif --report-json report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional


MANIFEST_NAME = "recovery_manifest.jsonl"
DEFAULT_CLASSIFICATION_REPORT_NAME = "classification_report.json"
CLASSIFIER_VERSION = 1


def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def jpeg_exif_hints(path: Path) -> dict[str, Any]:
    """Optional Pillow EXIF probe; never raises."""
    out: dict[str, Any] = {"exif_readable": False}
    try:
        from PIL import Image
    except ImportError:
        out["pillow"] = False
        return out
    out["pillow"] = True
    try:
        with Image.open(path) as img:
            ex = img.getexif()
    except Exception:
        return out
    if not ex:
        out["exif_readable"] = True
        out["exif_empty"] = True
        return out
    out["exif_readable"] = True
    # EXIF tag numbers (common)
    make = ex.get(271) or ex.get(0x010F)
    model = ex.get(272) or ex.get(0x0110)
    dt_orig = ex.get(36867) or ex.get(0x9003)
    dt = ex.get(306) or ex.get(0x0132)
    if make:
        out["camera_make"] = str(make).strip("\x00")
    if model:
        out["camera_model"] = str(model).strip("\x00")
    if dt_orig:
        out["datetime_original"] = str(dt_orig).strip("\x00")
    if dt:
        out["datetime"] = str(dt).strip("\x00")
    out["has_camera_identity"] = bool(make or model)
    out["has_timestamp"] = bool(dt_orig or dt)
    return out


def score_jpeg(record: dict[str, Any], exif: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Combine carver manifest hints with optional EXIF. Returns suggestion + scores.
    """
    bucket = record.get("bucket", "")
    jpeg = record.get("jpeg") or {}
    score_still = 0
    score_frame = 0
    reasons: list[str] = []

    if bucket == "frames":
        score_frame += 2
        reasons.append("carver_bucket_frames")
    elif bucket == "photos":
        score_still += 1
        reasons.append("carver_bucket_photos")

    if jpeg.get("inside_mjpeg_avi"):
        score_frame += 4
        reasons.append("jpeg_inside_mjpeg_avi")

    if jpeg.get("matches_skip_frame_resolution"):
        score_frame += 2
        reasons.append("matches_skip_frame_resolution")

    nv = jpeg.get("near_video_offset_bytes")
    win = jpeg.get("video_proximity_window_bytes")
    if nv is not None and isinstance(win, int) and nv >= 0 and nv <= win:
        score_frame += 1
        reasons.append("within_video_proximity_window")

    if exif:
        if exif.get("has_camera_identity"):
            score_still += 3
            reasons.append("exif_camera_make_or_model")
        if exif.get("has_timestamp"):
            score_still += 1
            reasons.append("exif_timestamp")

    margin = 2
    if score_still >= score_frame + margin:
        suggested = "likely_still"
    elif score_frame >= score_still + margin:
        suggested = "likely_frame"
    else:
        suggested = "uncertain"

    return {
        "suggested": suggested,
        "score_still": score_still,
        "score_frame": score_frame,
        "reasons": reasons,
    }


def run_classify(
    recovery_dir: Path,
    use_exif: bool,
    report_json: Optional[Path],
    csv_path: Optional[Path],
) -> int:
    manifest_path = recovery_dir / ".scan_state" / MANIFEST_NAME
    records = load_manifest(manifest_path)
    if not records:
        print(f"No manifest at {manifest_path}; run media_carver without --no-recovery-manifest.", file=sys.stderr)
        return 1

    out_rows: list[dict[str, Any]] = []
    summary = {"likely_still": 0, "likely_frame": 0, "uncertain": 0, "skipped_non_jpeg": 0}

    for rec in records:
        if rec.get("format") != "JPEG":
            summary["skipped_non_jpeg"] += 1
            continue
        rel = rec.get("path", "")
        abs_path = recovery_dir / rel
        exif_data = jpeg_exif_hints(abs_path) if use_exif and abs_path.is_file() else None
        classification = score_jpeg(rec, exif_data)
        summary[classification["suggested"]] = summary.get(classification["suggested"], 0) + 1
        row = {
            "path": rel,
            "bucket": rec.get("bucket"),
            "suggested": classification["suggested"],
            "score_still": classification["score_still"],
            "score_frame": classification["score_frame"],
            "reasons": classification["reasons"],
        }
        if exif_data:
            row["exif"] = {k: v for k, v in exif_data.items() if k not in ("pillow",)}
        out_rows.append(row)

    report = {
        "classifier_version": CLASSIFIER_VERSION,
        "recovery_dir": str(recovery_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_entries": len(records),
        "classified_jpegs": len(out_rows),
        "summary": summary,
        "items": out_rows,
    }

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Wrote {report_json}")

    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["path", "bucket", "suggested", "score_still", "score_frame", "reasons"])
            for row in out_rows:
                w.writerow(
                    [
                        row["path"],
                        row["bucket"],
                        row["suggested"],
                        row["score_still"],
                        row["score_frame"],
                        ";".join(row["reasons"]),
                    ]
                )
        print(f"Wrote {csv_path}")

    # Concise stdout summary
    print(f"JPEGs classified: {len(out_rows)}  (manifest lines: {len(records)})")
    print(
        f"  likely_still={summary['likely_still']}  "
        f"likely_frame={summary['likely_frame']}  "
        f"uncertain={summary['uncertain']}  "
        f"(non-JPEG manifest rows skipped: {summary['skipped_non_jpeg']})"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="media_classifier",
        description="Classify recovered JPEGs using media_carver recovery_manifest.jsonl",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Same output directory passed to media_carver.py (-o)",
    )
    parser.add_argument(
        "--exif",
        action="store_true",
        help="Open each file with Pillow and use EXIF when available",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Write full JSON report to PATH "
            f"(default: OUTPUT/.scan_state/{DEFAULT_CLASSIFICATION_REPORT_NAME})"
        ),
    )
    parser.add_argument(
        "--no-report-json",
        action="store_true",
        help="Do not write a JSON report (stdout summary only)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Write CSV summary to this path",
    )
    args = parser.parse_args()
    recovery = Path(args.output).expanduser().resolve()
    if args.no_report_json:
        report_path: Optional[Path] = None
    elif args.report_json is not None:
        report_path = args.report_json
    else:
        report_path = recovery / ".scan_state" / DEFAULT_CLASSIFICATION_REPORT_NAME
    sys.exit(
        run_classify(
            recovery,
            use_exif=args.exif,
            report_json=report_path,
            csv_path=args.csv,
        )
    )


if __name__ == "__main__":
    main()
