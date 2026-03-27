# Media Recovery Guide

Complete walkthrough for recovering photos and videos from a raw disk image
or block device using the four CLI tools in this repository.

This guide is written for a new operator. It covers everything from creating
the disk image through final verification that nothing was missed. Every
command is copy-pasteable; variables at the top of each section let you adapt
to your own paths and devices.

## Before you start

You need Python 3.10+ and read access to the source. No third-party packages
are required, though Pillow (`pip install pillow`) significantly improves JPEG
validation accuracy. You also need enough free disk space for recovered output;
plan for up to 50 % of the source image size.

Check your environment:

```bash
python3 --version          # must be 3.10+
python3 -c "import PIL; print('Pillow:', PIL.__version__)" 2>/dev/null \
  || echo "Pillow not installed (optional)"
```

If you want Pillow:

```bash
pip install pillow
```

## Step 0 — Acquire the source

Recovery works against a raw disk image file or a block device. If you already
have an image (`.img`, `.dd`, `.raw`), skip ahead to Step 1.

### Create an image from a device (macOS)

Identify the disk:

```bash
diskutil list external
```

Find your device (e.g. `/dev/disk4`). Unmount it without ejecting:

```bash
diskutil unmountDisk /dev/disk4
```

Create a byte-for-byte image (use the raw device `rdisk` for speed):

```bash
sudo dd if=/dev/rdisk4 of=./card.img bs=4m status=progress
```

Verify the image size matches the device:

```bash
ls -lh card.img
```

### Create an image from a device (Linux)

```bash
# Identify the device
lsblk

# Create the image (example: /dev/sdb)
sudo dd if=/dev/sdb of=./card.img bs=4M status=progress conv=fsync
```

### Verify image integrity (optional)

```bash
sha256sum card.img > card.img.sha256
```

Store this hash. If you ever need to prove the image was not modified during
recovery, you can recompute and compare.

From this point forward, all tools operate read-only against the image. The
original device can be safely removed.

## Step 1 — Carve: `media_carver.py`

The carver scans the image byte-by-byte looking for known file signatures
(JPEG, PNG, AVI, MP4, MKV, GIF, BMP, and many more), estimates file
boundaries using format-specific parsers, deduplicates by SHA-256, and writes
recovered files to an output directory.

### Set your paths

```bash
IMAGE=./card.img            # path to your disk image or block device
OUT=./recovery              # output directory (will be created)
```

### Run a full scan

```bash
python3 media_carver.py "$IMAGE" -o "$OUT"
```

The carver auto-chunks large images internally (default 768 MB chunks). State
is persisted in `$OUT/.scan_state/` so the scan is resumable — if it's
interrupted, re-run the same command and it picks up where it left off.

### Manual chunking (optional)

For very large images, constrained environments, or if you want more control:

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --start 0    --end 2000
python3 media_carver.py "$IMAGE" -o "$OUT" --start 2000 --end 4000
python3 media_carver.py "$IMAGE" -o "$OUT" --start 4000 --end 8000
```

Offsets are in megabytes. Each chunk resumes from the shared state, including
SHA-256 dedup.

### Scan a raw block device directly

```bash
sudo python3 media_carver.py /dev/sdb -o "$OUT"
```

No image file needed. The device is read, never written.

### Tuning

If your camera records video at a resolution other than 720p or 1080p
(e.g. 4K), tell the carver so it can classify those frames correctly:

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" \
  --skip-video-frame-res 1280x720,1920x1080,3840x2160
```

### What it produces

```
$OUT/
  photos/                           # recovered stills (JPEG, PNG, BMP, etc.)
  frames/                           # JPEGs the carver identified as video frames
  videos/                           # recovered video containers (AVI, MP4, etc.)
  .scan_state/
    seen_sha256.txt                 # persistent SHA-256 dedup hashes
    counters.json                   # running counters (photo/video IDs)
    scan_log.txt                    # timestamped progress + per-file skip log
    recovery_manifest.jsonl         # per-file metadata (used by all later stages)
```

### Check the results

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --report
```

This prints a summary of everything recovered without re-scanning. The image
does not need to exist for report mode.

### Review the skip log

Any JPEG that the carver found but could not validate is now logged with its
disk offset, estimated size, resolution, and failure reason:

```bash
grep "SKIP JPEG" "$OUT/.scan_state/scan_log.txt"
```

These are also recorded in the recovery manifest with `"status": "skipped"` so
downstream tools can audit them.

### Start over

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --reset
```

This clears `.scan_state/` (hashes, counters, manifest, log) but does **not**
delete already-recovered files in `photos/`, `frames/`, or `videos/`. Remove
those manually if you want a fully clean slate.

## Step 2 — Classify: `media_classifier.py`

The carver dumps all JPEGs into `photos/` (or `frames/` when detected inside
an AVI span). Many video frames end up in `photos/` because they weren't
inside a carved AVI. The classifier rescores every JPEG using the recovery
manifest and optional EXIF data, then moves misplaced files between `photos/`
and `frames/`.

### Dry run (see what would move)

```bash
python3 media_classifier.py -o "$OUT" --reorganize-buckets
```

This writes a JSON report at `$OUT/.scan_state/classification_report.json`
with every planned move listed under `bucket_moves`. No files are renamed.

### Apply the moves

```bash
python3 media_classifier.py -o "$OUT" --reorganize-buckets --apply-bucket-moves
```

After this, `photos/` contains verified stills and `frames/` contains video
frames.

### Without EXIF (faster, manifest-only scoring)

```bash
python3 media_classifier.py -o "$OUT" --no-exif --reorganize-buckets --apply-bucket-moves
```

### Export a CSV summary

```bash
python3 media_classifier.py -o "$OUT" --csv "$OUT/classification.csv"
```

### How classification works

Each JPEG gets two counters: `score_still` and `score_frame`. Signals that
push toward frame include matching a known video resolution (+4), being inside
an MJPEG AVI span (+2), progressive encoding (+1), and low bits-per-pixel
(+1). Signals toward still include EXIF presence (+2), higher bits-per-pixel
(+1), matching a common camera resolution (+1), and original carver bucket
being `photos` (+1).

The file is classified as `likely_frame` when frame ≥ still + 2,
`likely_still` when still ≥ frame + 2, and `uncertain` otherwise. Uncertain
files stay in their current directory.

### What it produces

Adds to `.scan_state/`:

```
classification_report.json    # full per-JPEG scoring, move log, skip diagnostics
```

## Step 3 — Cross-verify: `cross_verify_frames.py`

This step opens every AVI video, walks the RIFF container to extract each
MJPEG frame chunk, trims trailing padding to the JPEG end marker, and compares
SHA-256 hashes against all carved JPEGs. It answers three questions: which
carved frames already exist inside a recovered video (redundant), which are
orphaned (from deleted videos), and how many AVI frames were not individually
carved (embedded only in the video file).

### Run with full analysis

```bash
python3 cross_verify_frames.py -o "$OUT" --manifest --include-photos -v
```

`--manifest` enables disk-offset overlap analysis, grouping orphaned frames
into contiguous regions that indicate deleted videos. `--include-photos`
also checks `photos/` for any video frames that the classifier missed.

### Basic run (no manifest, frames only)

```bash
python3 cross_verify_frames.py -o "$OUT"
```

### Quiet mode (machine-readable only)

```bash
python3 cross_verify_frames.py -o "$OUT" --manifest -q
```

Suppresses per-video progress lines. The JSON report is still written.

### Understanding the output

The report prints a per-video table showing how many AVI frames were matched
to carved JPEGs. A low match rate is expected and normal — the carver scans
linearly, and when it finds a complete AVI header, it extracts the whole video
and jumps past it. Individual frames inside that AVI are not separately carved
unless a chunk boundary happened to fall mid-video. All those frames are
safely inside the recovered video file.

The orphaned frames section is more interesting: these are JPEGs that don't
match any video, usually because they came from videos that were deleted before
the card was re-used. The manifest overlap analysis groups them into
contiguous disk regions, each representing remnants of a lost video.

### What it produces

Adds to `.scan_state/`:

```
cross_verification_report.json    # per-video stats, frame-to-video map,
                                  # orphan regions, manifest overlap analysis
```

## Step 4 — Entropy scan: `entropy_scanner.py`

The final validation pass. This scans the entire raw image, computes Shannon
entropy for sampled blocks, and identifies any high-entropy regions (possible
compressed media) that were not covered by recovered files. If the carver
missed something, it shows up here.

### Run with manifest cross-reference

```bash
python3 entropy_scanner.py "$IMAGE" \
  --manifest "$OUT/.scan_state/recovery_manifest.jsonl" \
  --report-json "$OUT/.scan_state/entropy_report.json"
```

### Quick scan (no manifest)

```bash
python3 entropy_scanner.py "$IMAGE"
```

### Higher-resolution scan

Lower stride samples more blocks for a finer-grained picture, at the cost of
longer runtime:

```bash
python3 entropy_scanner.py "$IMAGE" --stride-kb 4
```

### Interpreting the output

The report classifies every sampled block into one of four entropy bands:
empty/pattern (< 1.0 bits), structured (< 5.0), compressed (< 7.0), and
near-random (≥ 7.0). High-entropy blocks that fall outside any recovered
file span are merged into regions and probed for known file signatures.

What to look for:

- **0 unrecovered regions with signatures**: the carver found everything it
  could. Recovery is complete.
- **Regions with signatures (JPEG, RIFF, etc.)**: indicates files the carver
  missed. Re-run the carver on that specific range:
  ```bash
  python3 media_carver.py "$IMAGE" -o "$OUT" --start 150 --end 160
  ```
- **Regions with no signatures but high entropy**: these are typically
  compressed data fragments from overwritten files, encrypted content, or
  non-media data. Not recoverable by signature-based carving.

### What it produces

Adds to `.scan_state/`:

```
entropy_report.json    # block classification, unrecovered regions,
                       # signature probe results
```

## Complete pipeline

Everything in one block for easy copy-paste:

```bash
IMAGE=./card.img
OUT=./recovery

# 1. Carve files from the raw image
python3 media_carver.py "$IMAGE" -o "$OUT"

# 2. Classify stills vs video frames, move misplaced files
python3 media_classifier.py -o "$OUT" --reorganize-buckets --apply-bucket-moves

# 3. Cross-verify frames against videos, find orphaned frame regions
python3 cross_verify_frames.py -o "$OUT" --manifest --include-photos -v

# 4. Entropy scan — verify nothing was missed
python3 entropy_scanner.py "$IMAGE" \
  --manifest "$OUT/.scan_state/recovery_manifest.jsonl" \
  --report-json "$OUT/.scan_state/entropy_report.json"
```

## Complete pipeline for a raw device

Same workflow, but reading a block device directly instead of an image file.
The device is never written to.

```bash
DEVICE=/dev/sdb            # Linux
# DEVICE=/dev/rdisk4       # macOS (raw device for speed)
OUT=./recovery

# 1. Carve (requires read access — use sudo if needed)
sudo python3 media_carver.py "$DEVICE" -o "$OUT"

# 2. Classify (no sudo needed — reads the output directory)
python3 media_classifier.py -o "$OUT" --reorganize-buckets --apply-bucket-moves

# 3. Cross-verify
python3 cross_verify_frames.py -o "$OUT" --manifest --include-photos -v

# 4. Entropy scan (requires read access to the device again)
sudo python3 entropy_scanner.py "$DEVICE" \
  --manifest "$OUT/.scan_state/recovery_manifest.jsonl" \
  --report-json "$OUT/.scan_state/entropy_report.json"
```

## Final output layout

After all four stages:

```
$OUT/
  photos/                           # verified stills
  frames/                           # video frames (individually carved)
  videos/                           # complete video containers
  .scan_state/
    seen_sha256.txt                 # SHA-256 dedup state
    counters.json                   # carver ID counters
    scan_log.txt                    # scan progress + skip log
    recovery_manifest.jsonl         # per-file metadata (all stages read this)
    classification_report.json      # classifier scoring + move log
    cross_verification_report.json  # frame-to-video map + orphan analysis
    entropy_report.json             # entropy coverage verification
```

## Reading the reports

All JSON reports are designed to be filtered with `jq` or loaded in Python.

### How many files were recovered?

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --report
```

### Which JPEGs were skipped and why?

```bash
grep "SKIP JPEG" "$OUT/.scan_state/scan_log.txt"
```

Or from the manifest:

```bash
python3 -c "
import json
with open('$OUT/.scan_state/recovery_manifest.jsonl') as f:
    for line in f:
        rec = json.loads(line.strip())
        if rec.get('status') == 'skipped':
            mb = rec['source_offset'] / 1048576
            sz = rec['size'] / 1024
            jp = rec.get('jpeg', {})
            dim = f\"{jp.get('width','?')}x{jp.get('height','?')}\" if jp else 'unknown'
            print(f'{mb:.1f} MB  {sz:.0f} KB  {dim}  {rec.get(\"skip_reason\",\"\")}')
"
```

### How many frames belong to which video?

```bash
python3 -c "
import json
with open('$OUT/.scan_state/cross_verification_report.json') as f:
    r = json.load(f)
for v in r['per_video']:
    name = v['video'].rsplit('/',1)[-1]
    print(f\"{name}: {v['matched_carved']}/{v['total_frames']} matched\")
"
```

### Were any high-entropy regions missed?

```bash
python3 -c "
import json
with open('$OUT/.scan_state/entropy_report.json') as f:
    r = json.load(f)
regions = r.get('high_entropy_regions', [])
print(f'Unrecovered high-entropy regions: {len(regions)}')
for i, reg in enumerate(regions, 1):
    sigs = ', '.join(reg['signatures_at_start']) or 'none'
    print(f'  {i}. {reg[\"start_mb\"]:.1f}-{reg[\"end_mb\"]:.1f} MB  '
          f'{reg[\"size_readable\"]}  sigs: {sigs}')
"
```

## Troubleshooting

### Carver times out or crashes on a large image

Break it into manual chunks with `--start` and `--end`. State is shared across
runs, so you can do as many chunks as you want. Each chunk is independently
resumable.

### Disk space runs out during carve

Write output to a volume with ample free space. Recovered media can approach
40 % of the source image size for densely populated cards. The carver aborts
on write errors but does not corrupt already-recovered files.

### Carver finds files but they're all corrupt

Make sure Pillow is installed (`pip install pillow`). Without it, the carver
cannot validate JPEG integrity and will accept truncated or corrupt files. With
Pillow, damaged files are skipped and logged.

### Too many JPEGs classified as "uncertain"

The classifier relies on `matches_skip_frame_resolution` from the manifest. If
your camera's video resolution is not in the default list (1280×720 and
1920×1080), add it to the carver via `--skip-video-frame-res` and re-run from
Step 1.

### Cross-verify shows a low match rate

This is normal. The match rate reflects how many carved JPEG files happen to
be individually extracted copies of frames that also exist inside recovered AVI
files. Most frames are only inside the AVI (not separately carved) because the
carver jumps past each AVI it finds. A low match rate means the videos were
recovered intact.

### Entropy scan shows unrecovered regions with signatures

Re-run the carver targeting that specific range:

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --start 150 --end 160
```

Then re-run the classifier and cross-verifier to incorporate any new files.

### Want to start completely fresh

```bash
python3 media_carver.py "$IMAGE" -o "$OUT" --reset
rm -rf "$OUT/photos" "$OUT/frames" "$OUT/videos"
```

Then re-run the full pipeline from Step 1.

## Supported formats

### Photos

JPEG, PNG, TIFF, BMP, GIF, WebP, HEIF/HEIC, AVIF, and RAW formats: Canon
CR2/CR3, Nikon NEF, Sony ARW, Adobe DNG, Olympus ORF, Fuji RAF, Panasonic
RW2, Samsung SRW, Pentax PEF.

### Videos

AVI (MJPEG and other codecs), MP4/MOV/3GP (ISOBMFF family), Matroska/WebM
(EBML), MPEG-TS, MPEG-PS, FLV, ASF/WMV.

## Per-tool reference

Each tool has its own detailed documentation:

- [`docs/scripts/media_carver.md`](./scripts/media_carver.md) — full flag
  reference, format coverage, parser notes, validation checklist.
- [`docs/scripts/media_classifier.md`](./scripts/media_classifier.md) —
  scoring model, manifest input, reorganize workflow, report schema.
- [`docs/scripts/cross_verify_frames.md`](./scripts/cross_verify_frames.md) —
  AVI parser internals, JSON report schema, known limitations.
- [`docs/scripts/entropy_scanner.md`](./scripts/entropy_scanner.md) — entropy
  thresholds, signature probing, region merging.
