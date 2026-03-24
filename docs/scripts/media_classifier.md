# media_classifier.py

## Purpose

Second-pass **JPEG still vs video-frame** suggestions for output produced by
[`media_carver.py`](../../media_carver.py). It reads per-file metadata emitted
into `.scan_state/recovery_manifest.jsonl` and optionally augments it with
EXIF from recovered files (when Pillow is installed).

## Requirements

- Python 3 (same environment as `media_carver.py` is fine)
- Optional: **Pillow** for `--exif` (`python -m pip install pillow`)

## Usage

```bash
python3 media_classifier.py -o /path/to/recovery
```

By default the JSON report is written to
`/path/to/recovery/.scan_state/classification_report.json`. Use `--no-report-json`
for stdout only, or `--report-json /other/path.json` to override the location.

With Pillow EXIF:

```bash
python3 media_classifier.py -o /path/to/recovery --exif
```

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
- **EXIF** (`--exif`): camera make/model or timestamps nudge toward **still**
  when present (many encoder frames lack rich EXIF).

Outputs `likely_still`, `likely_frame`, or `uncertain`. Use this for review /
re-sorting, not as ground truth.

## Output

- **Stdout**: short counts by suggested class; a second line summarizes manifest
  lines that were not usable (non-JPEG rows, invalid JSON, blanks) when any occur.
- **JSON report** (default: `.scan_state/classification_report.json`, or
  `--report-json PATH`; `--no-report-json` to skip) includes:
  - **`items`**: each JPEG scored, with `recovery_file_present`, classification
    `reasons`, optional `exif`, and optional **`exif_skipped`** (`reason_code` +
    `explanation`) when `--exif` was requested but EXIF was not applied (missing
    file, Pillow missing, unreadable EXIF).
  - **`skipped_entries`**: manifest rows not scored (MP4/PNG/etc. or missing
    `format`), each with **`reason_code`** and a plain-language **`explanation`**.
  - **`manifest_load_issues`**: lines that were not valid JSON (line number,
    parser message, short **`snippet`**).
  - **`manifest_input_stats`**: counts of parsed records, blank lines, invalid
    JSON lines, and total physical lines.
  - **`summary.skipped_entries_by_reason`**: counts grouped by `reason_code`.
- **`--csv`**: optional tabular summary (classified JPEG rows only; use JSON for skips).

## Validation checklist

- [ ] Run after a carver session that did not use `--no-recovery-manifest`
- [ ] With `--exif`, spot-check a few `likely_still` vs `likely_frame` paths
- [ ] Large jobs: keep the default JSON report (or `--report-json`) once, filter it
  rather than re-running EXIF

## Maintenance notes

Keep manifest schema in sync with `media_carver.append_manifest_record`. The
`v` field on each manifest line is the manifest format version.
