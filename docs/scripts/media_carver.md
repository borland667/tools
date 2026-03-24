# media_carver.py

## Purpose

`media_carver.py` recovers photos and videos from raw disk images or block
devices by scanning for known file signatures and estimating file boundaries
with format-specific logic.

It is designed for large-source recovery with:

- chunked full-image scanning,
- manual byte-range scanning,
- persistent dedup across runs,
- resilient extraction with progress logging.

## Requirements

- Python 3.10+
- Optional: Pillow (`pip install pillow`) for stronger JPEG validation
- Read permission for source image/device
- Enough free disk space in output path

## Python Setup with pyenv (Recommended)

Use `pyenv` to install and pin a compatible Python version for this script.

### 1) Install pyenv

On macOS (Homebrew):

```bash
brew update
brew install pyenv
```

Add to Bash profile (`~/.bashrc`):

```bash
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
```

Reload shell:

```bash
source ~/.bashrc
```

### 2) Install Python and set local version

From this repository root:

```bash
pyenv install 3.11.11
pyenv local 3.11.11
python --version
```

This creates a local `.python-version` for the repo so `python`/`python3` use
that version when you are in this directory.

### 3) (Optional) Virtual environment + Pillow

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install pillow
```

## Quick Start

```bash
python3 media_carver.py /path/to/image.img -o /path/to/output
```

## Common Usage Patterns

### Full scan (auto chunking)

```bash
python3 media_carver.py image.img -o /recovery
```

### Manual range scan (MB offsets)

```bash
python3 media_carver.py image.img -o /recovery --start 0 --end 1024
```

### Scan a block device

```bash
sudo python3 media_carver.py /dev/sdb -o /recovery
```

### Filter known embedded JPEG frames by resolution

```bash
python3 media_carver.py image.img -o /recovery --skip-video-frame-res 1280x720
```

### Reset dedup/counter state and restart

```bash
python3 media_carver.py image.img -o /recovery --reset
```

### Report existing output only

```bash
python3 media_carver.py image.img -o /recovery --report
```

In report mode, the source image does not need to exist; only the output folder
is used.

## Arguments and Options

### Required

- `image`: path to source disk image or block device
- `-o`, `--output`: output directory

### Optional

- `--start <MB>` / `--end <MB>`: manual range mode; both required together
- `--chunk-mb <N>`: chunk size for full scan mode (default `768`)
- `--min-size <bytes>`: minimum photo size and lower bound for video threshold
- `--min-dim <px>`: minimum JPEG dimensions when Pillow is available
- `--skip-video-frame-res WxH`: skip JPEGs at exact resolution
- `--reset`: clear `.scan_state` before scan
- `--report` (alias `--report-only`): print recovered-file summary without scanning
- default dedup mode: extract first, then deduplicate by full-file SHA-256
- `--fast-dedup`: use sampled-hash dedup instead of full SHA-256
- `-v`, `--verbose`: verbose logging
- `--version`: print version

Validation rules:

- `--chunk-mb`, `--min-size`, and `--min-dim` must be greater than `0`
- `--start` must be `>= 0`
- `--end` must be `> 0` and greater than `--start` when both are provided

## Output Structure

For `-o /recovery`:

```text
/recovery/
  photos/
  videos/
  .scan_state/
    seen_hashes.txt
    seen_sha256.txt
    counters.json
    scan_log.txt
```

Recovered files are named as:

```text
{media_type}_{id}_{format}_{dimensions?}_{size}.{ext}
```

Examples:

- `photo_00001_JPEG_4032x3024_2611KB.jpg`
- `video_00001_MP4_81MB.mp4`

## Internal Behavior Summary

1. Reads source in fixed-size buffers plus overlap.
2. Detects candidate starts from signature bytes and specialized patterns.
3. Detects source size with file/device-aware fallbacks before scanning.
4. Uses per-format end-finders (marker walk, size headers, container traversal).
5. Applies min-size checks and JPEG validation (if Pillow is present).
6. Deduplicates by full-file SHA-256 by default (`seen_sha256.txt`).
   `--fast-dedup` switches to sampled-hash mode (`seen_hashes.txt`).
7. Extracts recovered payloads into media-specific directories.

## Format Coverage

### Photos

JPEG, PNG, TIFF, BMP, GIF, WebP, HEIF/HEIC, AVIF, and multiple RAW subtypes
(CR2/CR3, NEF, ARW, DNG, ORF, RAF, RW2, SRW, PEF).

### Videos

AVI, MP4/MOV, Matroska/WebM, MPEG-TS, MPEG-PS, FLV, ASF/WMV, and 3GP-family
variants detected via ISOBMFF brands.

## Safety Notes

- Prefer scanning cloned images rather than original evidence media.
- Keep sources mounted/read as read-only when possible.
- Keep output storage separate from source storage.
- Do not use this tool to write or modify source devices.

## Known Limitations

- File carving is heuristic and can produce false positives.
- Fragmented media may be partially recovered or missed.
- Some container/file end calculations are best-effort estimates.
- Dedup uses sampled fingerprints; collisions are unlikely but possible.
- Without Pillow, JPEG validation is reduced.

## Validation Checklist

- `python3 media_carver.py --help` succeeds.
- `--report` works on a populated output directory.
- Small range scan produces expected logs/state files.
- `--reset` clears state and restarts counters.
- `python3 -m unittest discover -s tests/media_carver -p "test_*.py"` passes.

## Maintenance Notes

When updating this script, keep docs in sync for:

- new/changed flags,
- format support additions/removals,
- output naming/state behavior changes,
- safety-related behavior changes.
