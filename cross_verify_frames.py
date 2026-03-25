#!/usr/bin/env python3
"""
Cross-verify carved JPEG frames against carved AVI videos.

For each AVI video, walks the RIFF movi LIST and extracts every MJPEG
frame (00dc/01dc chunks). Hashes each frame with SHA-256 and compares
against the SHA-256 of every file in the frames/ directory.

Produces a report showing:
  - Which frames match which video (and which frame index within the video)
  - Which frames are orphaned (don't match any carved video)
  - Which video frames were NOT recovered as separate JPEGs
  - Per-video match statistics
"""

import hashlib
import json
import os
import struct
import sys
from collections import defaultdict
from pathlib import Path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def trim_jpeg_to_first_eoi(frame_data: bytes) -> bytes:
    """
    Trim JPEG-like bytes to the first 0xFFD9 EOI marker.

    This mirrors the repo's carver behavior more closely than trimming to
    the last EOI marker, which can produce different byte-for-byte hashes
    when an AVI chunk contains padding or additional FFD9 patterns.
    """
    eoi = frame_data.find(b"\xff\xd9", 2)
    if eoi >= 0:
        return frame_data[: eoi + 2]
    return frame_data


def extract_avi_mjpeg_frames(avi_path: str) -> list[dict]:
    """
    Walk the RIFF AVI movi LIST and extract each video frame chunk.
    Returns list of {index, offset, size, sha256} for each JPEG frame.
    """
    frames = []
    frame_idx = 0

    with open(avi_path, "rb") as f:
        # Verify RIFF AVI header
        header = f.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"AVI ":
            return frames

        file_size = os.path.getsize(avi_path)

        # Walk top-level chunks looking for the movi LIST
        pos = 12
        movi_start = None
        movi_end = None

        while pos < file_size - 8:
            f.seek(pos)
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                break
            chunk_id = chunk_hdr[:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]

            if chunk_id == b"LIST":
                list_type = f.read(4)
                if list_type == b"movi":
                    movi_start = pos + 12  # past LIST header + "movi"
                    movi_end = pos + 8 + chunk_size
                    break

            pos += 8 + chunk_size
            if chunk_size % 2:
                pos += 1  # RIFF padding

        if movi_start is None:
            return frames

        # Walk movi chunks
        pos = movi_start
        while pos < movi_end - 8:
            f.seek(pos)
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                break
            chunk_id = chunk_hdr[:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]

            # Handle nested LIST (rec chunks in some AVIs)
            if chunk_id == b"LIST":
                # Skip the 4-byte list type, walk inner chunks
                pos += 12
                continue

            # Video stream chunks: 00dc, 01dc, 00db, 01db
            is_video = (
                len(chunk_id) == 4
                and chunk_id[2:4] in (b"dc", b"db")
                and chunk_id[:2].isdigit()
            )

            if is_video and chunk_size > 0:
                # Read the frame data
                frame_data = f.read(min(chunk_size, 80 * 1024 * 1024))
                if len(frame_data) == chunk_size:
                    # Check if it's actually JPEG data
                    is_jpeg = len(frame_data) >= 2 and frame_data[:2] == b"\xff\xd8"
                    # Trim to JPEG EOI (FFD9) — AVI chunks often include
                    # trailing padding after the JPEG end marker. The carver
                    # extracts to (first) FFD9, so we must hash the same boundary.
                    hash_data = frame_data
                    if is_jpeg:
                        hash_data = trim_jpeg_to_first_eoi(frame_data)
                    frames.append({
                        "index": frame_idx,
                        "offset_in_avi": pos + 8,
                        "size": chunk_size,
                        "jpeg_size": len(hash_data) if is_jpeg else chunk_size,
                        "sha256": sha256_bytes(hash_data),
                        "is_jpeg": is_jpeg,
                    })
                frame_idx += 1

            next_pos = pos + 8 + chunk_size
            if chunk_size % 2:
                next_pos += 1
            pos = next_pos

    return frames


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 cross_verify_frames.py <recovery_dir>")
        sys.exit(1)

    recovery_dir = Path(sys.argv[1])
    frames_dir = recovery_dir / "frames"
    videos_dir = recovery_dir / "videos"

    if not frames_dir.is_dir():
        print(f"No frames/ directory at {frames_dir}")
        sys.exit(1)
    if not videos_dir.is_dir():
        print(f"No videos/ directory at {videos_dir}")
        sys.exit(1)

    # Step 1: Hash all carved frames
    print("Hashing carved frames...")
    frame_files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".jpg"))
    carved_frame_hashes = {}  # sha256 -> filename
    for i, fname in enumerate(frame_files):
        h = sha256_file(str(frames_dir / fname))
        carved_frame_hashes[h] = fname
        if (i + 1) % 500 == 0:
            print(f"  Hashed {i+1}/{len(frame_files)} frames...")
    print(f"  Total carved frames: {len(frame_files)}")

    # Step 2: Extract and hash frames from each AVI
    print("\nExtracting frames from AVI videos...")
    video_files = sorted(f for f in os.listdir(videos_dir) if f.endswith(".avi"))

    # Track matches
    frame_to_video = {}       # carved_frame_filename -> (video_filename, frame_index)
    video_stats = {}          # video_filename -> {total_frames, matched_frames, unmatched_frames}
    all_video_frame_hashes = set()

    for vname in video_files:
        vpath = str(videos_dir / vname)
        avi_frames = extract_avi_mjpeg_frames(vpath)
        total = len(avi_frames)
        jpeg_count = sum(1 for fr in avi_frames if fr["is_jpeg"])
        matched = 0
        matched_list = []
        unrecovered = 0

        for fr in avi_frames:
            h = fr["sha256"]
            all_video_frame_hashes.add(h)
            if h in carved_frame_hashes:
                fname = carved_frame_hashes[h]
                frame_to_video[fname] = (vname, fr["index"])
                matched += 1
                matched_list.append((fname, fr["index"]))
            else:
                unrecovered += 1

        video_stats[vname] = {
            "total_frames": total,
            "jpeg_frames": jpeg_count,
            "matched_carved": matched,
            "unrecovered_frames": unrecovered,
        }
        print(f"  {vname}: {total} frames ({jpeg_count} JPEG), "
              f"{matched} matched to carved, {unrecovered} not in frames/")

    # Step 3: Find orphaned frames (in frames/ but not in any AVI)
    orphaned = []
    for fname in frame_files:
        if fname not in frame_to_video:
            orphaned.append(fname)

    # Summary
    total_matched = len(frame_to_video)
    total_orphaned = len(orphaned)
    total_avi_frames = sum(s["total_frames"] for s in video_stats.values())
    total_unrecovered = sum(s["unrecovered_frames"] for s in video_stats.values())

    print("\n" + "=" * 70)
    print("  CROSS-VERIFICATION REPORT")
    print("=" * 70)
    print(f"\n  Carved frames in frames/:     {len(frame_files)}")
    print(f"  AVI videos analyzed:          {len(video_files)}")
    print(f"  Total frames inside AVIs:     {total_avi_frames}")
    print(f"")
    print(f"  Frames matched to a video:    {total_matched}")
    print(f"  Orphaned frames (no video):   {total_orphaned}")
    print(f"  AVI frames not recovered:     {total_unrecovered}")
    print(f"")
    print(f"  Match rate (carved):          {total_matched/len(frame_files)*100:.1f}%")
    if total_avi_frames > 0:
        print(f"  Recovery rate (AVI frames):   {total_matched/total_avi_frames*100:.1f}%")

    # Per-video breakdown
    print(f"\n  {'Video':<42} {'Frames':>7} {'Matched':>8} {'Missing':>8} {'Rate':>7}")
    print(f"  {'-'*40}  {'-'*7} {'-'*8} {'-'*8} {'-'*7}")
    for vname in video_files:
        s = video_stats[vname]
        rate = s["matched_carved"] / s["total_frames"] * 100 if s["total_frames"] else 0
        print(f"  {vname:<42} {s['total_frames']:>7} {s['matched_carved']:>8} "
              f"{s['unrecovered_frames']:>8} {rate:>6.1f}%")

    # Orphaned frames detail
    if orphaned:
        print(f"\n  Orphaned frames (from deleted/missing videos):")
        for fname in orphaned[:20]:
            sz = os.path.getsize(str(frames_dir / fname)) // 1024
            print(f"    {fname} ({sz}KB)")
        if len(orphaned) > 20:
            print(f"    ... and {len(orphaned) - 20} more")

    print("=" * 70)

    # Write JSON report
    report = {
        "summary": {
            "carved_frames": len(frame_files),
            "videos_analyzed": len(video_files),
            "total_avi_frames": total_avi_frames,
            "matched": total_matched,
            "orphaned": total_orphaned,
            "unrecovered_avi_frames": total_unrecovered,
            "match_rate_carved": round(total_matched / len(frame_files) * 100, 2) if frame_files else 0,
            "recovery_rate_avi": round(total_matched / total_avi_frames * 100, 2) if total_avi_frames else 0,
        },
        "per_video": video_stats,
        "frame_to_video_map": {k: {"video": v[0], "frame_index": v[1]} for k, v in frame_to_video.items()},
        "orphaned_frames": orphaned,
    }

    report_path = recovery_dir / ".scan_state" / "cross_verification_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    main()

