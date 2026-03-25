# media_classifier.py

## Purpose

Second-pass **JPEG still vs video-frame** suggestions for output produced by
[`media_carver.py`](../../media_carver.py). It reads per-file metadata emitted
into `.scan_state/recovery_manifest.jsonl` and augments it with EXIF from
recovered JPEGs **by default** (when Pillow is installed).

## Requirements

- Python 3 (same environment as `media_carver.py` is fine)
- Optional: **Pillow** for EXIF (`python -m pip install pillow`); without it,
  classification still runs and `exif_skipped` records that Pillow was not found.

## Usage

```bash
python3 media_classifier.py -o /path/to/recovery
```

By default the JSON report is written to
`/path/to/recovery/.scan_state/classification_report.json`. Use `--no-report-json`
for stdout only, or `--report-json /other/path.json` to override the location.

**EXIF** is on by default (`--exif`). Use **`--no-exif`** to score from carver
manifest hints only (faster, no Pillow opens).

CSV (in addition to the default JSON report unless `--no-report-json`):

```bash
python3 media_classifier.py -o /path/to/recovery --csv /tmp/jpeg_classes.csv
```

## Manifest input

`media_carver.py` appends one JSON object per line to:

`/path/to/recovery/.scan_state/recovery_manifest.jsonl`

Disable manifest emission with:

```bash
python3 media_carver.py image.img -o /path/to/recovery --no-recovery-manifest
```

`--reset` on the carver clears the manifest along with other scan state.

## Classification model

Scores are **heuristic** and conservative:

- **Carver hints** (bucket `photos` vs `frames`, MJPEG AVI span, default frame
  resolutions, proximity to a recovered video) push toward **frame** or **still**.
- **Manifest JPEG metadata** (from `media_carver` recovery manifest **v2+**):
  - **`matches_common_still_resolution`**: +still (typical phone/compact sizes).
  - **`bits_per_pixel`**: very low values (+frame, heavy compression common on
    video frames); higher values (+still, milder compression).
  - **`progressive_jpeg`**: +still (weak signal; baseline is common in MJPEG).
  Older manifests without these keys are scored from carver hints and EXIF only.
- **EXIF** (default on; **`--no-exif`** to disable): camera make/model or timestamps
  nudge toward **still** when present (many encoder frames lack rich EXIF).

Outputs `likely_still`, `likely_frame`, or `uncertain`. Use this for review /
re-sorting, not as ground truth.

## Reorganizing `photos/` vs `frames/` (optional)

When the suggestion disagrees with the folder a JPEG is in today, a move may be
appropriate:

- **`likely_still`** but file is under **`frames/`** → would move to **`photos/`**
- **`likely_frame`** but file is under **`photos/`** → would move to **`frames/`**

**`--reorganize-buckets`** (default behavior): records each planned move in the
JSON report (`bucket_moves` entries with `status: "planned"`). **No files are
renamed.**

**`--apply-bucket-moves`** (with **`--reorganize-buckets`**): performs those
renames. Use list-only first, review the report, then add **`--apply-bucket-moves`**.

**Not moved:** `uncertain`, paths not under `photos/` or `frames/` (e.g.
`videos/`), missing files, or unsafe relative paths. If the destination name
already exists, a suffix like `_reclass` is used before the extension.

```bash
# List planned moves in the report only (default for --reorganize-buckets)
python3 media_classifier.py -o /path/to/recovery --reorganize-buckets

# Execute renames after reviewing the report
python3 media_classifier.py -o /path/to/recovery --reorganize-buckets --apply-bucket-moves
```

**`recovery_manifest.jsonl` is not rewritten** — it still lists original paths
from the carver. After moving, either treat the report’s `items[].path` and
`bucket_moves` as truth for locations, or re-run a carve if you need the manifest
to match disk exactly.

The JSON report includes **`bucket_moves`** (per file: `status` — `planned`,
`moved`, `skipped`, `error` — `path_before`, `path_after`, `apply_executed`,
`reason` when skipped) and **`summary.bucket_reorganization`** (`apply_executed`,
counts). Exit code **1** if **`--apply-bucket-moves`** was used and any rename fails.

## Output

- **Stdout**: short counts by suggested class; a second line summarizes manifest
  lines that were not usable (non-JPEG rows, invalid JSON, blanks) when any occur.
- **JSON report** (default: `.scan_state/classification_report.json`, or
  `--report-json PATH`; `--no-report-json` to skip) includes:
  - **`items`**: each JPEG scored, with `recovery_file_present`, classification
    `reasons`, optional `exif`, and optional **`exif_skipped`** (`reason_code` +
    `explanation`) when EXIF was enabled but not applied (missing file, Pillow
    missing, unreadable EXIF). With **`--no-exif`**, EXIF is not read.
  - **`skipped_entries`**: manifest rows not scored (MP4/PNG/etc. or missing
    `format`), each with **`reason_code`** and a plain-language **`explanation`**.
  - **`manifest_load_issues`**: lines that were not valid JSON (line number,
    parser message, short **`snippet`**).
  - **`manifest_input_stats`**: counts of parsed records, blank lines, invalid
    JSON lines, and total physical lines.
  - **`summary.skipped_entries_by_reason`**: counts grouped by `reason_code`.
  - **`bucket_moves`**: when `--reorganize-buckets` is used, each JPEG row’s
    planned or completed move (or skip reason).
  - **`classifier_version`**: report schema version (currently **5**).
- **`--csv`**: optional tabular summary (classified JPEG rows only; use JSON for skips).

## Validation checklist

- [ ] Run after a carver session that did not use `--no-recovery-manifest`
- [ ] Spot-check a few `likely_still` vs `likely_frame` paths (EXIF on by default)
- [ ] Large jobs: keep the default JSON report (or `--report-json`) once, filter it
  rather than re-running EXIF

## Maintenance notes

Keep manifest schema in sync with `media_carver.append_manifest_record`. The
`v` field on each manifest line is the manifest format version.
