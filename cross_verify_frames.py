#!/usr/bin/env python3
"""
cross_verify_frames.py — Cross-verify carved JPEG frames against carved AVI videos.

For each AVI video in videos/, walks the RIFF movi LIST and extracts every
MJPEG frame (00dc/01dc/00db/01db chunks), trims each to the JPEG EOI boundary,
hashes with SHA-256, and compares against the SHA-256 of every file in frames/.

When a recovery manifest is available (from media_carver.py), also performs
disk-offset overlap analysis to classify orphaned frames as remnants of deleted
videos that were on the media before formatting.

Usage:
  # Basic cross-verification:
  python3 cross_verify_frames.py -o /path/to/recovery

  # With manifest for disk-offset overlap analysis:
  python3 cross_verify_frames.py -o /path/to/recovery --manifest

  # Also cross-check photos/ for stills that are secretly video frames:
  python3 cross_verify_frames.py -o /path/to/recovery --include-photos

  # JSON report only (no per-video stdout lines):
  python3 cross_verify_frames.py -o /path/to/recovery --quiet

  # Custom report path:
  python3 cross_verify_frames.py -o /path/to/recovery --report-json /tmp/xv.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import struct
import sys
import time
from pathlib import Path
from typing import Any, BinaryIO, Optional

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HASH_READ_BUFFER = 65536
MAX_AVI_FRAME_SIZE = 80 * 1024 * 1024   # 80 MB ceiling per single frame read
DEFAULT_REPORT_NAME = "cross_verification_report.json"
ORPHAN_REGION_GAP_BYTES = 5 * 1024 * 1024  # 5 MB gap → new region

# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """Stream-hash a file with SHA-256."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(HASH_READ_BUFFER)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# AVI RIFF parser
# ---------------------------------------------------------------------------
def _read_chunk_header(f: BinaryIO) -> Optional[tuple[bytes, int]]:
    """Read a RIFF chunk header (4-byte id + 4-byte LE size). Returns None on EOF/short read."""
    hdr = f.read(8)
    if len(hdr) < 8:
        return None
    return hdr[:4], struct.unpack("<I", hdr[4:8])[0]


def _trim_jpeg_to_eoi(data: bytes) -> bytes:
    """
    Trim JPEG frame data to the last FFD9 (EOI) marker.

    AVI MJPEG chunks often include trailing padding after the JPEG end marker.
    The media_carver extracts JPEGs to their FFD9 boundary, so we must hash the
    same span for SHA-256 comparison to succeed.
    """
    eoi = data.rfind(b"\xff\xd9")
    if eoi >= 0:
        return data[: eoi + 2]
    return data


def extract_avi_frames(avi_path: Path) -> list[dict[str, Any]]:
    """
    Walk the RIFF AVI movi LIST and extract metadata + hash for each video frame.

    Returns a list of dicts with keys:
        index, offset_in_avi, chunk_size, jpeg_size, sha256, is_jpeg
    """
    frames: list[dict[str, Any]] = []
    frame_idx = 0
    file_size = avi_path.stat().st_size

    try:
        with open(avi_path, "rb") as f:
            # --- Validate RIFF AVI header ---
            header = f.read(12)
            if len(header) < 12:
                logging.warning("Truncated file (< 12 bytes): %s", avi_path.name)
                return frames
            if header[:4] != b"RIFF" or header[8:12] != b"AVI ":
                logging.warning("Not a valid RIFF AVI: %s", avi_path.name)
                return frames

            # --- Locate the movi LIST ---
            pos = 12
            movi_start: Optional[int] = None
            movi_end: Optional[int] = None

            while pos < file_size - 8:
                f.seek(pos)
                result = _read_chunk_header(f)
                if result is None:
                    break
                chunk_id, chunk_size = result

                # Guard against corrupted chunk sizes
                if chunk_size > file_size - pos:
                    logging.debug(
                        "Chunk size %d exceeds remaining file at offset %d in %s",
                        chunk_size, pos, avi_path.name,
                    )
                    break

                if chunk_id == b"LIST":
                    list_type = f.read(4)
                    if len(list_type) < 4:
                        break
                    if list_type == b"movi":
                        movi_start = pos + 12  # past LIST hdr + "movi"
                        movi_end = pos + 8 + chunk_size
                        break

                # Advance past this chunk (+ RIFF word-alignment padding)
                pos += 8 + chunk_size + (chunk_size % 2)

            if movi_start is None:
                logging.warning("No movi LIST found in %s", avi_path.name)
                return frames

            # Clamp movi_end to file boundary
            if movi_end is not None and movi_end > file_size:
                movi_end = file_size

            # --- Walk movi chunks ---
            pos = movi_start
            while pos < movi_end - 8:
                f.seek(pos)
                result = _read_chunk_header(f)
                if result is None:
                    break
                chunk_id, chunk_size = result

                # Guard against runaway chunk sizes
                if chunk_size > movi_end - (pos + 8):
                    logging.debug(
                        "movi chunk at %d claims %d bytes, "
                        "exceeding movi boundary in %s",
                        pos, chunk_size, avi_path.name,
                    )
                    break

                # Nested LIST (rec chunks in some AVIs)
                if chunk_id == b"LIST":
                    pos += 12
                    continue

                # Video stream chunks: NNdc or NNdb (compressed/uncompressed)
                is_video = (
                    len(chunk_id) == 4
                    and chunk_id[2:4] in (b"dc", b"db")
                    and chunk_id[:2].isdigit()
                )

                if is_video and chunk_size > 0:
                    read_size = min(chunk_size, MAX_AVI_FRAME_SIZE)
                    frame_data = f.read(read_size)
                    if len(frame_data) == chunk_size:
                        is_jpeg = len(frame_data) >= 2 and frame_data[:2] == b"\xff\xd8"
                        hash_data = _trim_jpeg_to_eoi(frame_data) if is_jpeg else frame_data
                        frames.append({
                            "index": frame_idx,
                            "offset_in_avi": pos + 8,
                            "chunk_size": chunk_size,
                            "jpeg_size": len(hash_data) if is_jpeg else chunk_size,
                            "sha256": sha256_bytes(hash_data),
                            "is_jpeg": is_jpeg,
                        })
                    else:
                        logging.debug(
                            "Short read for frame %d at offset %d in %s "
                            "(wanted %d, got %d)",
                            frame_idx, pos + 8, avi_path.name,
                            chunk_size, len(frame_data),
                        )
                    frame_idx += 1

                # Advance (+ RIFF word-alignment padding)
                next_pos = pos + 8 + chunk_size + (chunk_size % 2)
                if next_pos <= pos:
                    # Zero-size chunk or overflow: bail to avoid infinite loop
                    break
                pos = next_pos

    except OSError as e:
        logging.error("Failed to read AVI %s: %s", avi_path.name, e)

    return frames


# ---------------------------------------------------------------------------
# Manifest helpers (optional disk-offset overlap analysis)
# ---------------------------------------------------------------------------
def load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    """Load recovery_manifest.jsonl, skipping invalid lines."""
    records: list[dict[str, Any]] = []
    if not manifest_path.is_file():
        return records
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return records


def build_video_spans(
    manifest: list[dict[str, Any]],
) -> list[tuple[int, int, str]]:
    """Extract (start_offset, end_offset, path) for each AVI in the manifest."""
    spans = []
    for rec in manifest:
        if rec.get("format") == "AVI":
            start = rec.get("source_offset")
            end = rec.get("source_end")
            path = rec.get("path", "")
            if isinstance(start, int) and isinstance(end, int):
                spans.append((start, end, path))
    return sorted(spans)


def build_frame_offsets(
    manifest: list[dict[str, Any]],
) -> dict[str, tuple[int, int]]:
    """Map frame filename → (source_offset, source_end) from manifest."""
    offsets: dict[str, tuple[int, int]] = {}
    for rec in manifest:
        if rec.get("format") != "JPEG":
            continue
        jp = rec.get("jpeg") or {}
        if not jp.get("matches_skip_frame_resolution"):
            continue
        path = rec.get("path", "")
        fname = Path(path).name
        start = rec.get("source_offset")
        end = rec.get("source_end")
        if isinstance(start, int) and isinstance(end, int):
            offsets[fname] = (start, end)
    return offsets


def classify_orphan_regions(
    orphaned: list[str],
    frame_offsets: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    """
    Group orphaned frames into contiguous disk regions.

    Each region likely represents a deleted video that was on the media
    before formatting.
    """
    # Collect offsets for orphans that have manifest entries
    entries = []
    for fname in orphaned:
        off = frame_offsets.get(fname)
        if off:
            entries.append((off[0], off[1], fname))
    entries.sort()

    if not entries:
        return []

    regions: list[dict[str, Any]] = []
    region_start = entries[0][0]
    region_end = entries[0][1]
    region_frames = [entries[0][2]]

    for offset_start, offset_end, fname in entries[1:]:
        if offset_start - region_end > ORPHAN_REGION_GAP_BYTES:
            regions.append({
                "start_offset": region_start,
                "end_offset": region_end,
                "start_mb": round(region_start / (1024 * 1024), 1),
                "end_mb": round(region_end / (1024 * 1024), 1),
                "frame_count": len(region_frames),
                "frames": region_frames,
            })
            region_start = offset_start
            region_end = offset_end
            region_frames = [fname]
        else:
            region_end = max(region_end, offset_end)
            region_frames.append(fname)

    regions.append({
        "start_offset": region_start,
        "end_offset": region_end,
        "start_mb": round(region_start / (1024 * 1024), 1),
        "end_mb": round(region_end / (1024 * 1024), 1),
        "frame_count": len(region_frames),
        "frames": region_frames,
    })

    return regions


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def run_cross_verify(
    recovery_dir: Path,
    *,
    include_photos: bool = False,
    use_manifest: bool = False,
    report_json: Optional[Path] = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """
    Cross-verify carved JPEG frames against carved AVI videos.

    Returns the full report dict.
    """
    frames_dir = recovery_dir / "frames"
    videos_dir = recovery_dir / "videos"
    run_start = time.time()

    # --- Collect JPEG files to verify ---
    jpeg_dirs: list[tuple[Path, str]] = []
    if frames_dir.is_dir():
        jpeg_dirs.append((frames_dir, "frames"))
    if include_photos and (recovery_dir / "photos").is_dir():
        jpeg_dirs.append((recovery_dir / "photos", "photos"))

    if not jpeg_dirs:
        logging.error("No frames/ directory found at %s", recovery_dir)
        return {"error": "no_frames_directory"}

    if not videos_dir.is_dir():
        logging.error("No videos/ directory found at %s", recovery_dir)
        return {"error": "no_videos_directory"}

    # --- Hash all target JPEGs ---
    carved_hashes: dict[str, tuple[str, str]] = {}  # sha256 → (filename, bucket)
    total_jpegs = 0
    for jdir, bucket in jpeg_dirs:
        files = sorted(f for f in os.listdir(jdir) if f.lower().endswith((".jpg", ".jpeg")))
        for i, fname in enumerate(files):
            h = sha256_file(jdir / fname)
            carved_hashes[h] = (fname, bucket)
            total_jpegs += 1
            if not quiet and (i + 1) % 1000 == 0:
                logging.info("Hashed %d/%d JPEGs from %s/...", i + 1, len(files), bucket)

    logging.info("Hashed %d JPEG files for comparison.", total_jpegs)

    # --- Collect and hash AVI video frames ---
    video_files = sorted(
        f for f in os.listdir(videos_dir)
        if f.lower().endswith(".avi")
    )

    frame_to_video: dict[str, dict[str, Any]] = {}
    video_stats: dict[str, dict[str, Any]] = {}
    all_video_hashes: set[str] = set()

    for vname in video_files:
        avi_frames = extract_avi_frames(videos_dir / vname)
        total = len(avi_frames)
        jpeg_count = sum(1 for fr in avi_frames if fr["is_jpeg"])
        matched = 0

        for fr in avi_frames:
            h = fr["sha256"]
            all_video_hashes.add(h)
            if h in carved_hashes:
                fname, bucket = carved_hashes[h]
                frame_to_video[fname] = {
                    "video": vname,
                    "frame_index": fr["index"],
                    "bucket": bucket,
                }
                matched += 1

        video_stats[vname] = {
            "total_frames": total,
            "jpeg_frames": jpeg_count,
            "matched_carved": matched,
            "unrecovered_frames": total - matched,
        }

        if not quiet:
            logging.info(
                "  %s: %d frames (%d JPEG), %d matched, %d unrecovered",
                vname, total, jpeg_count, matched, total - matched,
            )

    # --- Identify orphaned frames ---
    all_target_files: list[str] = []
    for jdir, bucket in jpeg_dirs:
        all_target_files.extend(
            f for f in os.listdir(jdir) if f.lower().endswith((".jpg", ".jpeg"))
        )
    orphaned = sorted(f for f in all_target_files if f not in frame_to_video)

    # --- Manifest-based overlap analysis ---
    manifest_analysis: Optional[dict[str, Any]] = None
    if use_manifest:
        manifest_path = recovery_dir / ".scan_state" / "recovery_manifest.jsonl"
        manifest = load_manifest(manifest_path)
        if manifest:
            video_spans = build_video_spans(manifest)
            frame_offsets = build_frame_offsets(manifest)

            inside_count = 0
            outside_count = 0
            for fname in all_target_files:
                off = frame_offsets.get(fname)
                if off is None:
                    continue
                is_inside = any(
                    off[0] >= vs and off[0] < ve
                    for vs, ve, _ in video_spans
                )
                if is_inside:
                    inside_count += 1
                else:
                    outside_count += 1

            orphan_regions = classify_orphan_regions(orphaned, frame_offsets)

            manifest_analysis = {
                "manifest_records": len(manifest),
                "video_spans": len(video_spans),
                "frames_with_offsets": len(frame_offsets),
                "inside_video_span": inside_count,
                "outside_all_video_spans": outside_count,
                "orphan_regions": len(orphan_regions),
                "orphan_region_details": [
                    {k: v for k, v in r.items() if k != "frames"}
                    for r in orphan_regions
                ],
            }

            if not quiet and orphan_regions:
                logging.info("")
                logging.info(
                    "Manifest overlap: %d frames inside video spans, "
                    "%d outside (from ~%d deleted video region(s))",
                    inside_count, outside_count, len(orphan_regions),
                )
                for i, region in enumerate(orphan_regions):
                    logging.info(
                        "  Region %d: %.1f-%.1f MB (%d frames)",
                        i + 1, region["start_mb"], region["end_mb"],
                        region["frame_count"],
                    )
        else:
            logging.warning(
                "No manifest at %s; skipping overlap analysis.", manifest_path,
            )

    # --- Compute summary ---
    total_avi_frames = sum(s["total_frames"] for s in video_stats.values())
    total_matched = len(frame_to_video)
    total_orphaned = len(orphaned)
    elapsed = time.time() - run_start

    summary = {
        "carved_jpegs_checked": total_jpegs,
        "videos_analyzed": len(video_files),
        "total_avi_frames": total_avi_frames,
        "matched_to_video": total_matched,
        "orphaned": total_orphaned,
        "unrecovered_avi_frames": sum(
            s["unrecovered_frames"] for s in video_stats.values()
        ),
        "match_rate_percent": (
            round(total_matched / total_jpegs * 100, 2)
            if total_jpegs else 0
        ),
        "recovery_rate_percent": (
            round(total_matched / total_avi_frames * 100, 2)
            if total_avi_frames else 0
        ),
        "elapsed_seconds": round(elapsed, 2),
    }

    report: dict[str, Any] = {
        "version": VERSION,
        "recovery_dir": str(recovery_dir.resolve()),
        "include_photos": include_photos,
        "summary": summary,
        "per_video": video_stats,
        "frame_to_video_map": frame_to_video,
        "orphaned_frames": orphaned,
    }
    if manifest_analysis:
        report["manifest_analysis"] = manifest_analysis

    # --- Console report ---
    if not quiet:
        w = 70
        print()
        print("=" * w)
        print("  CROSS-VERIFICATION REPORT")
        print("=" * w)
        print()
        print(f"  JPEGs checked:                {total_jpegs}")
        print(f"  AVI videos analyzed:          {len(video_files)}")
        print(f"  Total frames inside AVIs:     {total_avi_frames}")
        print()
        print(f"  Matched to a video:           {total_matched}")
        print(f"  Orphaned (no video match):    {total_orphaned}")
        print(f"  AVI frames not recovered:     {summary['unrecovered_avi_frames']}")
        print()
        print(f"  Match rate (carved):          {summary['match_rate_percent']}%")
        print(f"  Recovery rate (AVI frames):   {summary['recovery_rate_percent']}%")
        print(f"  Elapsed:                      {elapsed:.1f}s")

        # Per-video table
        col_v, col_f, col_m, col_x, col_r = 42, 7, 8, 8, 7
        print()
        print(
            f"  {'Video':<{col_v}} {'Frames':>{col_f}} "
            f"{'Matched':>{col_m}} {'Missing':>{col_x}} {'Rate':>{col_r}}"
        )
        print(
            f"  {'-' * col_v} {'-' * col_f} "
            f"{'-' * col_m} {'-' * col_x} {'-' * col_r}"
        )
        for vname in video_files:
            s = video_stats[vname]
            rate = (
                s["matched_carved"] / s["total_frames"] * 100
                if s["total_frames"] else 0
            )
            print(
                f"  {vname:<{col_v}} {s['total_frames']:>{col_f}} "
                f"{s['matched_carved']:>{col_m}} "
                f"{s['unrecovered_frames']:>{col_x}} {rate:>{col_r - 1}.1f}%"
            )

        # Orphan summary
        if orphaned:
            print()
            print(f"  Orphaned frames ({total_orphaned} total):")
            shown = min(10, len(orphaned))
            for fname in orphaned[:shown]:
                for jdir, bucket in jpeg_dirs:
                    fpath = jdir / fname
                    if fpath.is_file():
                        sz = fpath.stat().st_size // 1024
                        print(f"    {fname} ({sz}KB)")
                        break
            if len(orphaned) > shown:
                print(f"    ... and {len(orphaned) - shown} more")

        print()
        print("=" * w)

    # --- Write JSON report ---
    if report_json is not None:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        with open(report_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Report: {report_json}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cross_verify_frames",
        description=(
            "Cross-verify carved JPEG frames against carved AVI videos. "
            "Matches SHA-256 hashes of frames/ JPEGs to MJPEG frame chunks "
            "extracted from videos/, producing per-video match statistics "
            "and identifying orphaned frames from deleted videos."
        ),
        epilog=(
            "Examples:\n"
            "  # Basic cross-verification:\n"
            "  python3 cross_verify_frames.py -o /path/to/recovery\n\n"
            "  # With manifest disk-offset analysis:\n"
            "  python3 cross_verify_frames.py -o /path/to/recovery --manifest\n\n"
            "  # Include photos/ in the check:\n"
            "  python3 cross_verify_frames.py -o /path/to/recovery --include-photos\n\n"
            "  # Quiet mode (JSON report only):\n"
            "  python3 cross_verify_frames.py -o /path/to/recovery --quiet\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        type=Path,
        help="Recovery output directory (same -o passed to media_carver.py)",
    )
    parser.add_argument(
        "--include-photos",
        action="store_true",
        help=(
            "Also check photos/ JPEGs against AVI frames "
            "(detects stills that are actually video frames)"
        ),
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help=(
            "Use .scan_state/recovery_manifest.jsonl for disk-offset overlap "
            "analysis (classifies orphaned frames into deleted-video regions)"
        ),
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            f"Write JSON report to PATH "
            f"(default: OUTPUT/.scan_state/{DEFAULT_REPORT_NAME})"
        ),
    )
    parser.add_argument(
        "--no-report-json",
        action="store_true",
        help="Do not write a JSON report (stdout summary only)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-video progress lines (report file still written)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging (debug-level AVI parser messages)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    args = parser.parse_args()

    # Logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )

    recovery = args.output.expanduser().resolve()
    if not recovery.is_dir():
        parser.error(f"Recovery directory does not exist: {recovery}")

    # Report path
    if args.no_report_json:
        report_path: Optional[Path] = None
    elif args.report_json is not None:
        report_path = args.report_json
    else:
        report_path = recovery / ".scan_state" / DEFAULT_REPORT_NAME

    report = run_cross_verify(
        recovery,
        include_photos=args.include_photos,
        use_manifest=args.manifest,
        report_json=report_path,
        quiet=args.quiet,
    )

    # Exit 1 if the report itself flagged an error (missing dirs, etc.)
    if "error" in report:
        sys.exit(1)


if __name__ == "__main__":
    main()
