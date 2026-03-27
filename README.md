# Tools Repository

Personal scripts and utilities for recovery, automation, and one-off workflows.

## Repository Conventions

These rules apply to all current and future scripts, regardless of language.

### Design Principles

- Keep each script focused on one clear job.
- Prefer the simplest working approach over over-engineered abstractions.
- Preserve intended behavior when refactoring.
- Make small, isolated changes instead of broad rewrites.

### File and Naming Conventions

- Use lowercase snake_case for script filenames (`my_script.py`, `sync_logs.sh`).
- Keep root-level scripts intentional; avoid dumping temporary files in root.
- Use explicit output directories rather than hidden side effects.
- Do not commit generated artifacts unless explicitly required.

### CLI and UX Conventions

- Every script should support `--help` and provide practical examples.
- Use clear, descriptive flags (`--output`, `--dry-run`, `--verbose`).
- Prefer safe defaults; require explicit opt-in for destructive actions.
- Exit with non-zero status on real errors.
- Keep logs actionable and concise.

### Runtime and Dependencies

- Pin runtime expectations in script docs (language version, system tools).
- Keep dependencies minimal and justified.
- Prefer standard-library solutions first.
- Document optional dependencies and degraded behavior when absent.

### Safety and Data Handling

- Never mutate source data unless the script is explicitly for mutation.
- Prefer read-only workflows for recovery/forensics scripts.
- Keep outputs separate from source inputs.
- Avoid writing secrets or tokens into logs.

### Documentation Conventions

- Root `README.md` remains conventions-first and indexes available scripts.
- Each script must have a dedicated doc under `docs/scripts/`.
- Script docs should include:
  - purpose,
  - requirements,
  - usage examples,
  - arguments/options,
  - output behavior,
  - safety notes,
  - known limitations.
- Update docs in the same change whenever behavior or flags change.

### Quality and Validation

- Add a quick validation checklist in each script doc.
- Run lightweight sanity checks after substantive changes.
- Prefer deterministic outputs when practical.

## Repository Layout

- `media_carver.py` — media recovery script for raw images/devices.
- `docs/scripts/media_carver.md` — script-specific documentation.
- `docs/recovery-guide.md` — end-to-end recovery guide (image/device through verification).
- `docs/workflow-sd-card-recovery.md` — benchmark results from SD card test run.
- `docs/scripts/_template.md` — template for documenting new scripts.
- `scripts/install-to-bin.sh` — install scripts into `~/bin`.
- `scripts/README.md` — documentation for helper scripts.
- `tests/media_carver/` — CLI mode and parser-heuristic tests for `media_carver.py`.
- `.github/pull_request_template.md` — default PR checklist/template.
- `AGENTS.md` — guidance for coding agents working in this repository.
- `LICENSE` — repository license.

## Script Index

- [`media_carver.py`](./media_carver.py): carve media files from raw images and
  block devices. Full usage and internals are in
  [`docs/scripts/media_carver.md`](./docs/scripts/media_carver.md).
  It classifies likely video-frame JPEGs using MJPEG AVI headers, default
  **720p / 1080p** frame sizes, and optional burst clustering (see the script
  doc). Defaults favor **aggressive recovery** (maximize extracted files).
  Writes per-file metadata to `.scan_state/recovery_manifest.jsonl` by default
  (`--no-recovery-manifest` to disable).
- [`media_classifier.py`](./media_classifier.py): second-pass JPEG **still vs frame**
  suggestions using that manifest; uses Pillow **EXIF** by default (`--no-exif` to
  skip); writes `.scan_state/classification_report.json` by default (`--no-report-json`
  to skip), including skip diagnostics; optional `--reorganize-buckets` (list planned
  moves) and `--apply-bucket-moves` (execute renames) between `photos/` and `frames/`.
  Scoring uses carver manifest **v2** JPEG hints (bpp, progressive, common still
  sizes) when present. See [`docs/scripts/media_classifier.md`](./docs/scripts/media_classifier.md).
- [`cross_verify_frames.py`](./cross_verify_frames.py): optional validation that
  cross-checks carved `frames/` JPEGs against MJPEG frames found inside carved
  AVI files in `videos/`; see [`docs/scripts/cross_verify_frames.md`](./docs/scripts/cross_verify_frames.md).
- [`entropy_scanner.py`](./entropy_scanner.py): post-carve validation that scans the
  raw image for high-entropy regions not covered by recovered files; cross-references
  the recovery manifest to flag potential gaps; see
  [`docs/scripts/entropy_scanner.md`](./docs/scripts/entropy_scanner.md).

## Optional Libraries (media_carver)

`media_carver.py` works with standard-library Python. Optional libraries improve
validation quality when installed.

Install all optional validators:

```bash
python -m pip install pillow pillow-heif opencv-python av pymediainfo imagecodecs rawpy
```

For full details (benefits, startup warnings, and install guidance), see
`docs/scripts/media_carver.md`.

## Adding a New Script

1. Add the script with clear `--help` output.
2. Create a script doc from `docs/scripts/_template.md`.
3. Add the script to the repository layout and script index above.
4. Include at least one realistic usage example.

## Running Scripts via PATH (`~/bin`)

Use the helper installer to expose scripts via `~/bin`:

```bash
scripts/install-to-bin.sh media_carver.py
```

Install all top-level executable scripts:

```bash
scripts/install-to-bin.sh --all
```

Preview actions without changes:

```bash
scripts/install-to-bin.sh --all --dry-run
```

If `~/bin` is not in PATH, add:

```bash
export PATH="$HOME/bin:$PATH"
```

See `scripts/README.md` for full installer options.
