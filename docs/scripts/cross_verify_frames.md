# cross_verify_frames.py

## Purpose

Cross-verify carved JPEG frames against carved AVI videos. For each AVI in
`videos/`, the script walks the RIFF movi LIST, extracts every MJPEG frame
chunk, trims to the JPEG EOI boundary, hashes with SHA-256, and compares
against every JPEG file in `frames/` (and optionally `photos/`).

Use this after running `media_carver.py` and `media_classifier.py` to answer:

- Which carved frames belong to which carved video?
- Which frames are orphaned (from deleted videos not recovered as AVI files)?
- How many AVI frames were or were not individually recovered?

With `--manifest`, the script also uses disk-offset data from
`recovery_manifest.jsonl` to classify orphaned frames into contiguous
deleted-video regions.

## Requirements

- Python 3.10+
- No third-party dependencies (standard library only)
- A recovery output directory produced by `media_carver.py` containing
  `frames/`, `videos/`, and optionally `.scan_state/recovery_manifest.jsonl`

## Quick Start

```bash
python3 cross_verify_frames.py -o /path/to/recovery
```

## Common Usage Patterns

### Basic cross-verification

```bash
python3 cross_verify_frames.py -o /path/to/recovery
```

### With manifest disk-offset overlap analysis

```bash
python3 cross_verify_frames.py -o /path/to/recovery --manifest
```

### Also check photos/ for misclassified video frames

```bash
python3 cross_verify_frames.py -o /path/to/recovery --include-photos
```

### Quiet mode (JSON report only, no per-video lines)

```bash
python3 cross_verify_frames.py -o /path/to/recovery --quiet
```

### Custom report path

```bash
python3 cross_verify_frames.py -o /path/to/recovery --report-json /tmp/xv.json
```

### No report file (stdout only)

```bash
python3 cross_verify_frames.py -o /path/to/recovery --no-report-json
```

## Arguments and Options

### Required

- `-o`, `--output`: recovery output directory (same `-o` passed to
  `media_carver.py`)

### Optional

- `--include-photos`: also check `photos/` JPEGs against AVI frames (detects
  stills that are actually video frames)
- `--manifest`: use `.scan_state/recovery_manifest.jsonl` for disk-offset
  overlap analysis (classifies orphaned frames into deleted-video regions)
- `--report-json PATH`: write JSON report to PATH (default:
  `OUTPUT/.scan_state/cross_verification_report.json`)
- `--no-report-json`: do not write a JSON report (stdout summary only)
- `-q`, `--quiet`: suppress per-video progress lines
- `-v`, `--verbose`: debug-level logging (AVI parser details)
- `--version`: print version

## Output Structure

### Console

- Summary counts: JPEGs checked, videos analyzed, matched, orphaned,
  unrecovered AVI frames, match/recovery rates, elapsed time.
- Per-video table: frames, matched, missing, rate.
- Orphaned frame listing (first 10 shown, total count).

### JSON report

Default path: `OUTPUT/.scan_state/cross_verification_report.json`

Top-level keys:

- `version`: script version string.
- `recovery_dir`: absolute path to the recovery directory.
- `include_photos`: whether `photos/` was included.
- `summary`: aggregate counts and rates.
- `per_video`: per-AVI stats (total_frames, jpeg_frames, matched_carved,
  unrecovered_frames).
- `frame_to_video_map`: `{filename: {video, frame_index, bucket}}` for every
  matched frame.
- `orphaned_frames`: list of filenames with no video match.
- `manifest_analysis` (when `--manifest`): disk-offset overlap stats including
  inside_video_span, outside_all_video_spans, orphan_regions count, and
  orphan_region_details (start/end MB, frame count per region).

## Internal Behavior Summary

1. Hash every JPEG in `frames/` (and optionally `photos/`) with SHA-256.
2. For each AVI in `videos/`, validate the RIFF AVI header.
3. Locate the `movi` LIST and walk its chunks.
4. For each video stream chunk (`NNdc`/`NNdb`), read the frame data.
5. Trim JPEG frames to the last `FFD9` (EOI) marker — AVI chunks often include
   trailing padding that the carver does not extract. Hashing the same boundary
   is critical for SHA-256 comparison.
6. Compare AVI frame hashes against carved JPEG hashes.
7. Any carved JPEG not matched to any AVI is classified as orphaned.
8. With `--manifest`, use `source_offset` from the recovery manifest to
   determine whether frames fall inside or outside carved video spans, and
   group orphans into contiguous deleted-video regions.

## Safety Notes

- Read-only: the script never modifies the recovery directory or its files.
- AVI parser is defensive: corrupted chunk sizes, short reads, and truncated
  files are handled gracefully with warnings rather than crashes.
- No external dependencies: runs in any Python 3.10+ environment.

## Known Limitations

- Only verifies against AVI (RIFF) videos. MP4/MKV/other containers are not
  yet supported for frame extraction.
- The EOI-trimming heuristic uses `rfind(FFD9)` which could mismatch if a
  JPEG has embedded thumbnail data with its own EOI before the main image EOI.
  In practice this is rare for MJPEG video frames.
- `--manifest` overlap analysis requires that the recovery manifest was written
  by the carver (`--recovery-manifest`, which is the default). If the manifest
  is missing or incomplete, overlap analysis is skipped.
- Orphan region grouping uses a fixed 5 MB gap threshold. Tightly packed
  deleted videos separated by less than 5 MB will be grouped as one region.

## Validation Checklist

- `python3 cross_verify_frames.py --help` succeeds.
- `python3 cross_verify_frames.py --version` prints version.
- Basic run on a populated recovery directory produces console report and JSON
  file.
- `--manifest` adds `manifest_analysis` to the JSON report.
- `--include-photos` checks both `photos/` and `frames/`.
- `--no-report-json` produces console output only, no file written.
- `--quiet` suppresses per-video lines but still writes the JSON report.
- Handles empty `frames/` or `videos/` directories gracefully (zero counts,
  no crash).

## Maintenance Notes

When updating this script, keep docs in sync for:

- new/changed flags,
- JSON report schema changes,
- AVI parser behavior changes,
- new container format support.
