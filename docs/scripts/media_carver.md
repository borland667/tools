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
- No required third-party Python packages (standard library only)
- Optional validator libraries are listed in `Install Libraries`
- Read permission for source image/device
- Enough free disk space in output path

## Install Libraries

`media_carver.py` runs with standard-library Python only. Optional libraries can
improve validation quality.

### Minimal install (required runtime only)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Recommended optional install (JPEG validation)

```bash
python -m pip install pillow
```

### Extended optional validators (use if available)

```bash
python -m pip install pillow-heif opencv-python av pymediainfo imagecodecs rawpy
```

When installed, the script automatically uses available validators after
extraction:

- photos: Pillow / OpenCV / imagecodecs / rawpy
- videos: PyAV / pymediainfo

Optional validators are non-blocking: validation failures are logged as
warnings, but recovered files are still kept.

At startup, the script logs which optional libraries are available and warns
for missing ones, including the benefit and install command for each.

### Verify environment

```bash
python - <<'PY'
import sys
print("Python:", sys.version.split()[0])
try:
    import PIL
    print("Pillow: installed")
except Exception:
    print("Pillow: not installed (fallback mode)")
PY
```

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

### 3) (Optional) Virtual environment + libraries

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# Then install optional libraries from "Install Libraries"
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
# Defaults already include 720p + 1080p; override only if you need more/different:
python3 media_carver.py image.img -o /recovery \
  --skip-video-frame-res 1280x720,1920x1080
```

Multiple values are supported (repeat the flag or use commas):

```bash
python3 media_carver.py image.img -o /recovery \
  --skip-video-frame-res 1280x720,1920x1080 \
  --skip-video-frame-res 3840x2160
```

### Typical video vs still JPEG sizes

- **Likely video frame sizes (defaults):** `1280x720`, `1920x1080`. Some devices
  use other sizes (e.g. `2560x1440`); add them explicitly if you see unmatched
  frame strips.
- **Still photos** often land near common megapixel classes (~12 / 8 / 5 / 3 / 1 MP).
  With **`--burst-frame-clustering`**, a small built-in list of typical still
  dimensions prevents **near-video burst** hints from relabeling those as frames.
  That does **not** override MJPEG-in-AVI detection or an explicit
  `--skip-video-frame-res` match.

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
- `--min-dim <px>`: minimum JPEG dimensions when Pillow is available (default `16`;
  lower = more small recoveries, more noise)
- `--skip-video-frame-res WxH`: treat JPEGs at exact resolution as likely video
  frames (repeatable and comma-separated). Default active pair is **`1280x720` and
  `1920x1080`** (720p and 1080p).
- `--reset`: clear `.scan_state` before scan
- `--report` (alias `--report-only`): print recovered-file summary without scanning
- default dedup mode: extract first, then deduplicate by full-file SHA-256
- `--fast-dedup`: use sampled-hash dedup instead of full SHA-256
- **Default recovery profile (aggressive):** maximize extracted files. JPEGs
  that match `--skip-video-frame-res` (**720p / 1080p** by default) after a
  recovered video still go to `frames/`; JPEGs **inside** a carved MJPEG AVI
  span also go to `frames/`. Everything else stays in `photos/` unless you add
  stricter flags.
- `--skip-jpeg-after-video`: optional **stricter** mode — within
  `--skip-jpeg-after-video-window-mb` after a video, also route unknown-dimension
  JPEGs or configured frame sizes to `frames/` (similar to older defaults).
- `--burst-frame-clustering`: optional extra frame hint from tight same-`WxH`
  bursts near video / MJPEG (off by default).
- `--skip-jpeg-after-video-window-mb <N>`: proximity window in MB for the two
  options above (default `256`)
- `--recovery-manifest` / `--no-recovery-manifest`: whether to append
  `.scan_state/recovery_manifest.jsonl` (**default:** `--recovery-manifest`;
  use `--no-recovery-manifest` to disable and skip [`media_classifier.py`](./media_classifier.md))
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
  frames/
  .scan_state/
    seen_hashes.txt
    seen_sha256.txt
    counters.json
    scan_log.txt
    recovery_manifest.jsonl
```

Recovered files are named as:

```text
{media_type}_{id}_{format}_{dimensions?}_{size}.{ext}
```

Examples:

- `photo_00001_JPEG_4032x3024_2611KB.jpg`
- `video_00001_MP4_81MB.mp4`

## Recovery manifest (for classification)

Each successfully recovered file appends **one JSON line** to
`.scan_state/recovery_manifest.jsonl` (default; disable with `--no-recovery-manifest`).
Fields include relative `path`, output `bucket` (`photos` / `frames` /
`videos`), source offsets, `format`, and for JPEGs a `jpeg` object with
dimensions and carver hints (`inside_mjpeg_avi`, `matches_skip_frame_resolution`,
video proximity, etc.).

Use [`media_classifier.py`](./media_classifier.md) on the same
`-o` directory for suggested **still vs frame** labels and optional EXIF checks.

Final report also includes timing stats:

- start timestamp,
- finish timestamp,
- elapsed runtime in seconds.

Hash stats are mode-specific and mutually exclusive in output:

- default strict mode shows only `Unique SHA-256`,
- `--fast-dedup` mode shows only `Unique hashes`.

## Internal Behavior Summary

1. Reads source in fixed-size buffers plus overlap.
2. Detects candidate starts from signature bytes and specialized patterns.
3. Detects source size with file/device-aware fallbacks before scanning.
4. Uses per-format end-finders (marker walk, size headers, container traversal).
5. Applies min-size checks and JPEG validation (if Pillow is present), including
   full JPEG decode to reject truncated/corrupt payloads and bounded retry with
   later JPEG end markers when the first boundary looks invalid.
6. Detects MJPEG-in-AVI via `strh` stream headers when an AVI is carved and
   routes other JPEGs whose offsets fall inside that AVI span to `frames/`.
7. Optional `--burst-frame-clustering`: same-dimension JPEG runs (same gate as
   before: MJPEG span, frame resolution list, or near-video window). Off by
   default for aggressive recovery.
8. Deduplicates by full-file SHA-256 by default (`seen_sha256.txt`).
   `--fast-dedup` switches to sampled-hash mode (`seen_hashes.txt`).
9. Extracts recovered payloads into media-specific directories.

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
- In `--fast-dedup` mode, sampled-hash dedup can theoretically collide.
- Without Pillow, JPEG validation is reduced.
- Strict JPEG integrity checks can reject partially recoverable JPEGs.
- With `--skip-jpeg-after-video`, stricter post-video routing may send some real
  stills to `frames/` if dimensions are unknown or match the frame list; tune
  `--skip-jpeg-after-video-window-mb` and use [`media_classifier.py`](./media_classifier.md)
  for a second pass.

## Parser Hardening Notes

Recent parser hardening aligns closer to PhotoRec-style structural validation:

- MKV/WebM: EBML walk can locate Segment after pre-segment elements.
- MP4/MOV family: stricter box-type and structure validation.
- MPEG-PS: packet-structure based boundary detection.
- GIF: block-structure parsing instead of trailer-byte scan only.
- PNG: IHDR semantic checks and stricter chunk-sequence validation.
- ASF/WMV: GUID/object-size parsing for header and data objects.

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
