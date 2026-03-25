# cross_verify_frames.py

## Purpose

Cross-verify carved JPEG frames against carved AVI MJPEG video chunks.
This helps validate whether the carver’s MJPEG-in-AVI detection and
`frames/` routing are behaving as expected.

## Requirements

- Python 3
- No third-party dependencies

## Quick Start

```bash
python3 cross_verify_frames.py /path/to/recovery
```

## Common Usage Patterns

### <use case 1>

After a `media_carver.py` run (that produced `frames/` and `videos/`):

```bash
python3 cross_verify_frames.py /path/to/recovery
```

## Arguments and Options

### Required

- `<recovery_dir>`: recovery output directory containing `frames/` and
  `videos/`.

## Input and Output

Document:

- Expected input paths/formats:
  - `recovery_dir/frames/*.jpg` (carved JPEG frames)
  - `recovery_dir/videos/*.avi` (carved AVI files to scan for MJPEG chunks)
- Output paths/formats:
  - Writes `recovery_dir/.scan_state/cross_verification_report.json`
    (readable JSON)
- Side effects:
  - Read-only on `frames/` and `videos/`
  - Creates/overwrites the JSON report in `.scan_state/`

## Internal Behavior Summary

High-level flow:

1. Hash all files in `frames/` (SHA-256 per file).
2. For each `.avi` in `videos/`, walks the RIFF `movi` list and extracts
   `00dc/01dc` (and related) chunks as “frame candidates”.
3. For frame candidates that appear to be JPEGs (`FFD8`), trims to the last
   `FFD9` boundary and hashes.
4. Compares AVI-frame SHA-256 hashes against carved-frame hashes.
5. Reports:
   - which carved frames match which AVI + frame index,
   - which carved frames are orphaned (no AVI match),
   - which AVI MJPEG frames weren’t recovered as separate JPEGs.

## Safety Notes

- Safe for recovery workflows: this script does not modify carved media.
- Prefer running on a cloned/recovery output directory, not on source media.

## Known Limitations

- Scans only `videos/*.avi` (not MP4/MOV/etc.).
- “Is JPEG” is detected by `FFD8` and uses a heuristic trim to the last `FFD9`.
- “Is JPEG” is detected by `FFD8` and the verifier trims to the **first** `FFD9`
  (to mirror the carver’s JPEG EOI finder and produce matching hashes).
- Only frames whose AVI chunks look like JPEGs participate in hash matching.
- Output paths assume carved frame files are `.jpg`.

## Validation Checklist

- Sanity check: confirm `frames/` and `videos/` directories exist under your
  recovery output.
- Smoke test: run on a small recovery directory and inspect the JSON report.
- Error-path check: ensure the script exits non-zero when directories are
  missing.

## Maintenance Notes

- If `media_carver` adds new MJPEG container support (or changes frame file
  extensions), update this script accordingly.

