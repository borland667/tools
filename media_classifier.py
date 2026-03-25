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
  python3 media_classifier.py -o /path/to/recovery --no-exif
  python3 media_classifier.py -o /path/to/recovery --reorganize-buckets
  python3 media_classifier.py -o /path/to/recovery --reorganize-buckets --apply-bucket-moves
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional


MANIFEST_NAME = "recovery_manifest.jsonl"
DEFAULT_CLASSIFICATION_REPORT_NAME = "classification_report.json"
CLASSIFIER_VERSION = 5


def load_manifest(
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """
    Parse JSONL manifest. Returns (records, json_errors, blank_line_count).
    Each json_errors item includes: line, reason, detail, snippet (trimmed).
    """
    if not manifest_path.is_file():
        return [], [], 0
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    blank_lines = 0
    with open(manifest_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                issues.append(
                    {
                        "line": line_no,
                        "reason": "invalid_json",
                        "detail": str(e),
                        "snippet": stripped if len(stripped) <= 240 else stripped[:240] + "…",
                    }
                )
    return rows, issues, blank_lines


def skip_reason_not_jpeg(rec: dict[str, Any]) -> dict[str, Any]:
    """Structured reason for a manifest row that is not classified as JPEG."""
    fmt = rec.get("format")
    path = rec.get("path", "")
    bucket = rec.get("bucket")
    if fmt is None or fmt == "":
        code = "missing_format"
        explanation = (
            "Manifest row has no 'format' field (or it is empty). "
            "Only entries with format exactly 'JPEG' are scored for still vs frame."
        )
    else:
        code = "format_not_jpeg"
        explanation = (
            f"This tool only runs the still-vs-frame heuristic on JPEG entries. "
            f"Rows for format {fmt!r} (e.g. MP4, PNG) are inventory from the carver "
            f"and are not scored here."
        )
    return {
        "path": path,
        "bucket": bucket,
        "format": fmt,
        "reason_code": code,
        "explanation": explanation,
    }


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


def target_bucket_for_suggestion(suggested: str) -> Optional[str]:
    """Folder name under recovery root, or None if classification does not imply a move."""
    if suggested == "likely_frame":
        return "frames"
    if suggested == "likely_still":
        return "photos"
    return None


def bucket_from_manifest_path(rel: str) -> Optional[str]:
    """Top-level bucket (photos/frames) from manifest-relative path, or None."""
    parts = Path(rel).parts
    if not parts:
        return None
    top = parts[0]
    if top in ("photos", "frames"):
        return top
    return None


def path_under_recovery(path: Path, recovery_dir: Path) -> bool:
    try:
        path.resolve().relative_to(recovery_dir.resolve())
    except ValueError:
        return False
    return True


def uniquify_destination(dest: Path) -> Path:
    """If dest exists, add _reclass, _reclass_2, ... before the suffix."""
    if not dest.exists():
        return dest
    parent = dest.parent
    stem = dest.stem
    suffix = dest.suffix
    n = 1
    while True:
        label = f"{stem}_reclass" if n == 1 else f"{stem}_reclass_{n}"
        candidate = parent / f"{label}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def plan_bucket_move(
    recovery_dir: Path,
    rel: str,
    suggested: str,
) -> tuple[Optional[Path], Optional[Path], Optional[str], str]:
    """
    Returns (src, dest, new_rel, skip_reason).
    skip_reason is empty when a move should be attempted; otherwise explains why not.
    """
    want_bucket = target_bucket_for_suggestion(suggested)
    have_bucket = bucket_from_manifest_path(rel)
    if want_bucket is None:
        return None, None, None, "uncertain_or_neutral_suggestion"
    if have_bucket is None:
        return None, None, None, "not_under_photos_or_frames"
    if have_bucket == want_bucket:
        return None, None, None, "already_in_target_bucket"
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None, None, None, "unsafe_relative_path"
    root = recovery_dir.resolve()
    src = (root / rel_path).resolve()
    if not path_under_recovery(src, recovery_dir):
        return None, None, None, "source_outside_recovery_dir"
    remainder = Path(*rel_path.parts[1:]) if len(rel_path.parts) > 1 else Path(rel_path.name)
    dest = root / want_bucket / remainder
    try:
        dest.resolve().relative_to(root)
    except ValueError:
        return None, None, None, "destination_outside_recovery_dir"
    dest_parent = dest.parent
    try:
        dest_parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    dest_final = uniquify_destination(dest)
    new_rel = str(dest_final.resolve().relative_to(root))
    return src, dest_final, new_rel, ""


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

    matches_frame_res = jpeg.get("matches_skip_frame_resolution", False)
    if matches_frame_res:
        score_frame += 4
        reasons.append("matches_skip_frame_resolution")

    nv = jpeg.get("near_video_offset_bytes")
    win = jpeg.get("video_proximity_window_bytes")
    if nv is not None and isinstance(win, int) and nv >= 0 and nv <= win:
        score_frame += 1
        reasons.append("within_video_proximity_window")

    if jpeg.get("matches_common_still_resolution"):
        score_still += 2
        reasons.append("common_still_photo_resolution")

    bpp = jpeg.get("bits_per_pixel")
    if isinstance(bpp, (int, float)) and bpp > 0:
        if bpp < 0.22:
            score_frame += 2
            reasons.append("low_bits_per_pixel_heavy_compression")
        elif bpp > 0.72 and not matches_frame_res:
            # Higher BPP suggests a still, but not when the resolution
            # explicitly matches user-declared video frame sizes.
            score_still += 1
            reasons.append("higher_bits_per_pixel_milder_compression")

    if jpeg.get("progressive_jpeg") is True:
        score_still += 1
        reasons.append("progressive_jpeg")

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
    reorganize_buckets: bool = False,
    apply_bucket_moves: bool = False,
) -> int:
    manifest_path = recovery_dir / ".scan_state" / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"No manifest at {manifest_path}; run media_carver without --no-recovery-manifest.", file=sys.stderr)
        return 1

    records, manifest_load_issues, blank_line_count = load_manifest(manifest_path)
    if not records and not manifest_load_issues and blank_line_count == 0:
        print(f"Manifest at {manifest_path} is empty.", file=sys.stderr)
        return 1

    out_rows: list[dict[str, Any]] = []
    skipped_entries: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "likely_still": 0,
        "likely_frame": 0,
        "uncertain": 0,
        "skipped_non_jpeg": 0,
    }

    for rec in records:
        if rec.get("format") != "JPEG":
            summary["skipped_non_jpeg"] += 1
            skipped_entries.append(skip_reason_not_jpeg(rec))
            continue
        rel = rec.get("path", "")
        abs_path = recovery_dir / rel
        on_disk = abs_path.is_file()
        exif_data = None
        exif_skipped: Optional[dict[str, Any]] = None
        if use_exif:
            if on_disk:
                exif_data = jpeg_exif_hints(abs_path)
            else:
                exif_skipped = {
                    "reason_code": "recovery_file_not_found",
                    "explanation": (
                        f"No file at {rel!r} under the recovery directory; EXIF was not read. "
                        "Scores use carver manifest hints only."
                    ),
                }
        classification = score_jpeg(rec, exif_data)
        summary[classification["suggested"]] = summary.get(classification["suggested"], 0) + 1
        row: dict[str, Any] = {
            "path": rel,
            "bucket": rec.get("bucket"),
            "recovery_file_present": on_disk,
            "suggested": classification["suggested"],
            "score_still": classification["score_still"],
            "score_frame": classification["score_frame"],
            "reasons": classification["reasons"],
        }
        if exif_skipped:
            row["exif_skipped"] = exif_skipped
        elif use_exif and on_disk and exif_data:
            if exif_data.get("pillow") is False:
                row["exif_skipped"] = {
                    "reason_code": "pillow_not_installed",
                    "explanation": (
                        "Pillow is not installed (`pip install pillow`); EXIF was not read."
                    ),
                }
            elif not exif_data.get("exif_readable"):
                row["exif_skipped"] = {
                    "reason_code": "exif_unreadable",
                    "explanation": (
                        "Pillow could not read EXIF from this file (open/decode error or no EXIF). "
                        "Classification used manifest hints only."
                    ),
                }
            else:
                row["exif"] = {k: v for k, v in exif_data.items() if k not in ("pillow",)}
        out_rows.append(row)

    bucket_moves: list[dict[str, Any]] = []
    move_failures = 0
    if reorganize_buckets:
        for row in out_rows:
            rel = row["path"]
            suggested = row["suggested"]
            entry: dict[str, Any] = {
                "path_before": rel,
                "suggested": suggested,
                "apply_executed": apply_bucket_moves,
            }
            if not row.get("recovery_file_present"):
                entry["status"] = "skipped"
                entry["reason"] = "file_not_found"
                bucket_moves.append(entry)
                continue
            src, dest, new_rel, skip = plan_bucket_move(recovery_dir, rel, suggested)
            if skip:
                entry["status"] = "skipped"
                entry["reason"] = skip
                bucket_moves.append(entry)
                continue
            assert src is not None and dest is not None and new_rel is not None
            entry["path_after"] = new_rel
            if not apply_bucket_moves:
                entry["status"] = "planned"
                bucket_moves.append(entry)
                continue
            try:
                if not src.is_file():
                    entry["status"] = "skipped"
                    entry["reason"] = "file_not_found_at_rename"
                    bucket_moves.append(entry)
                    continue
                src.rename(dest)
                entry["status"] = "moved"
                row["path"] = new_rel
                row["bucket"] = bucket_from_manifest_path(new_rel)
                bucket_moves.append(entry)
            except OSError as e:
                entry["status"] = "error"
                entry["error"] = str(e)
                move_failures += 1
                bucket_moves.append(entry)

        summary["bucket_reorganization"] = {
            "requested": True,
            "apply_executed": apply_bucket_moves,
            "moved": sum(1 for m in bucket_moves if m.get("status") == "moved"),
            "planned": sum(1 for m in bucket_moves if m.get("status") == "planned"),
            "skipped": sum(1 for m in bucket_moves if m.get("status") == "skipped"),
            "errors": move_failures,
        }
    else:
        summary["bucket_reorganization"] = {"requested": False}

    skip_counts = dict(Counter(s["reason_code"] for s in skipped_entries))
    summary["skipped_entries_by_reason"] = skip_counts
    summary["manifest_blank_lines"] = blank_line_count
    summary["manifest_invalid_json_lines"] = len(manifest_load_issues)

    manifest_input_stats = {
        "parsed_records": len(records),
        "blank_lines": blank_line_count,
        "invalid_json_lines": len(manifest_load_issues),
        "physical_lines": blank_line_count + len(manifest_load_issues) + len(records),
    }

    report = {
        "classifier_version": CLASSIFIER_VERSION,
        "recovery_dir": str(recovery_dir.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_input_stats": manifest_input_stats,
        "manifest_load_issues": manifest_load_issues,
        "classified_jpegs": len(out_rows),
        "summary": summary,
        "skipped_entries": skipped_entries,
        "bucket_moves": bucket_moves,
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

    print(f"JPEGs classified: {len(out_rows)}  (parsed manifest records: {len(records)})")
    print(
        f"  likely_still={summary['likely_still']}  "
        f"likely_frame={summary['likely_frame']}  "
        f"uncertain={summary['uncertain']}"
    )
    if summary["skipped_non_jpeg"] or manifest_load_issues or blank_line_count:
        parts = []
        if summary["skipped_non_jpeg"]:
            parts.append(f"not scored (non-JPEG / bad format field): {summary['skipped_non_jpeg']}")
        if manifest_load_issues:
            parts.append(f"invalid JSON lines: {len(manifest_load_issues)}")
        if blank_line_count:
            parts.append(f"blank manifest lines: {blank_line_count}")
        print("  Manifest / skips: " + "; ".join(parts) + " — see JSON report for details.", flush=True)
    br = summary.get("bucket_reorganization") or {}
    if br.get("requested"):
        if br.get("apply_executed"):
            print(
                f"  Bucket reorganization (applied): moved {br.get('moved', 0)}, "
                f"skipped {br.get('skipped', 0)}, errors {br.get('errors', 0)}.",
                flush=True,
            )
        else:
            planned_n = br.get("planned", 0)
            print(
                f"  Bucket reorganization (planned only): {planned_n} move(s) listed — "
                "use --apply-bucket-moves to execute.",
                flush=True,
            )
        print(
            "  Note: recovery_manifest.jsonl still lists original paths until you re-carve or edit it.",
            flush=True,
        )
    if reorganize_buckets and apply_bucket_moves and move_failures > 0:
        return 1
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
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Read EXIF from each recovered JPEG with Pillow when available "
            "(default: --exif; use --no-exif for manifest-only scoring)"
        ),
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
    parser.add_argument(
        "--reorganize-buckets",
        action="store_true",
        help=(
            "List planned JPEG moves between photos/ and frames/ when classification "
            "disagrees with the current folder (written to the JSON report; no renames "
            "unless you also pass --apply-bucket-moves)."
        ),
    )
    parser.add_argument(
        "--apply-bucket-moves",
        action="store_true",
        help=(
            "With --reorganize-buckets, actually rename files (likely_still in frames/ "
            "-> photos/; likely_frame in photos/ -> frames/). Default is list-only."
        ),
    )
    args = parser.parse_args()
    if args.apply_bucket_moves and not args.reorganize_buckets:
        parser.error("--apply-bucket-moves requires --reorganize-buckets")
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
            reorganize_buckets=args.reorganize_buckets,
            apply_bucket_moves=args.apply_bucket_moves,
        )
    )


if __name__ == "__main__":
    main()
