# SD Card Recovery Workflow

End-to-end media recovery from a raw SD card image using a four-stage
pipeline: carve, classify, cross-verify, and entropy-scan.

## Prerequisites

- Python 3.10+
- No required third-party packages (Pillow recommended for JPEG validation)
- Enough free disk space for recovered media (expect up to 50% of image size)
- Read access to the source image or block device

## Pipeline Overview

```text
┌──────────────┐     ┌───────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│ media_carver │ ──▶ │ media_classifier   │ ──▶ │ cross_verify_frames │ ──▶ │ entropy_scanner  │
│              │     │                    │     │                     │     │                  │
│ Carve files  │     │ Sort frames from   │     │ SHA-256 match       │     │ Verify no high-  │
│ from raw     │     │ stills using       │     │ carved JPEGs to     │     │ entropy regions  │
│ disk image   │     │ manifest heuristic │     │ AVI video frames    │     │ were missed      │
└──────────────┘     └───────────────────┘     └─────────────────────┘     └──────────────────┘
```

Stages 1–3 share the same `-o` output directory. Stage 4 reads the raw
image and the manifest to verify coverage.

## Stage 1: Carve — `media_carver.py`

### What it does

Scans the raw image byte-by-byte for known file signatures (JPEG SOI, RIFF
AVI, MP4 ftyp, etc.), estimates file boundaries with format-specific parsers,
deduplicates by SHA-256, and writes recovered files into `photos/`, `frames/`,
and `videos/` subdirectories.

### Command

```bash
# Full auto-chunked scan:
python3 media_carver.py /path/to/photo-8g.img -o /path/to/recovery

# Manual chunking for large images (useful for timeout-prone environments):
python3 media_carver.py /path/to/photo-8g.img -o /path/to/recovery --start 0 --end 2000
python3 media_carver.py /path/to/photo-8g.img -o /path/to/recovery --start 2000 --end 4000
python3 media_carver.py /path/to/photo-8g.img -o /path/to/recovery --start 4000 --end 8000
```

The carver is resumable. State is tracked in `.scan_state/` so subsequent
chunks pick up where the last one left off. SHA-256 dedup spans all runs.

### Output

```text
recovery/
  photos/            # stills and unclassified JPEGs
  frames/            # JPEGs the carver identified as video frames (by AVI span)
  videos/            # recovered video containers (AVI, MP4, etc.)
  .scan_state/
    seen_sha256.txt          # persistent dedup hashes
    counters.json            # running photo/video counters
    scan_log.txt             # timestamped scan progress
    recovery_manifest.jsonl  # per-file metadata (used by stages 2 and 3)
```

### Benchmark results (7.5 GB SD card image)

| Metric | Value |
|--------|-------|
| Image size | 7.5 GB |
| Scan time (3 chunks) | ~17 minutes |
| Photos recovered | 2,536 unique (361 duplicates filtered) |
| Videos recovered | 45 AVI files |
| Total recovered size | 3.1 GB (397 MB photos + 2.8 GB videos) |
| Errors | 0 |

### Key flags

| Flag | Purpose |
|------|---------|
| `--start N --end M` | Scan only MB range [N, M) — required together |
| `--reset` | Clear state and restart counters |
| `--report` | Print summary of existing output without scanning |
| `--skip-video-frame-res WxH` | Resolution(s) treated as video frames (default: 1280x720,1920x1080) |
| `--recovery-manifest` | Write per-file manifest (default on; `--no-recovery-manifest` to disable) |
| `-v` | Verbose logging |

## Stage 2: Classify — `media_classifier.py`

### What it does

Reads `recovery_manifest.jsonl` and scores each JPEG as `likely_still`,
`likely_frame`, or `uncertain` using a weighted heuristic model. Scoring
signals include resolution match against known video frame sizes, EXIF
presence, bits-per-pixel compression ratio, progressive JPEG encoding, and
carver bucket hints. Optionally reorganizes files between `photos/` and
`frames/` directories.

### Command

```bash
# Classify and report only (dry run):
python3 media_classifier.py -o /path/to/recovery --reorganize-buckets

# Classify and move files:
python3 media_classifier.py -o /path/to/recovery --reorganize-buckets --apply-bucket-moves
```

### Scoring model (simplified)

Frame-favoring signals (increase `score_frame`):

- `matches_skip_frame_resolution` = True → **+4** (strongest signal)
- `inside_mjpeg_avi` = True → +2
- Progressive JPEG encoding → +1
- Low bits-per-pixel (≤0.50) → +1

Still-favoring signals (increase `score_still`):

- Carver bucket was `photos` → +1
- EXIF data present → +2
- Higher bits-per-pixel (>0.72, suppressed when resolution matches frames) → +1
- Matches common still camera resolution → +1

Classification rule: `likely_frame` if frame ≥ still + 2; `likely_still` if
still ≥ frame + 2; otherwise `uncertain`.

### Benchmark results

| Metric | Value |
|--------|-------|
| JPEGs classified | 2,536 |
| Classified as likely_still | 610 |
| Classified as likely_frame | 1,796 |
| Uncertain | 130 |
| Files moved (photos/ → frames/) | 1,796 |
| Errors | 0 |

The 130 uncertain files are real stills at 4032×2880 and 2560×1440 that don't
carry EXIF — they remain in `photos/` where they belong.

### Post-classification layout

```text
recovery/
  photos/   740 files  (289 MB)  — 709 at 4032×2880, 31 at 2560×1440
  frames/  1796 files  (109 MB)  — all 1280×720
  videos/    45 files  (2.8 GB)  — MJPEG AVI containers
```

### Key flags

| Flag | Purpose |
|------|---------|
| `-o` | Same output directory from stage 1 |
| `--reorganize-buckets` | List planned file moves in the JSON report |
| `--apply-bucket-moves` | Execute the moves (requires `--reorganize-buckets`) |
| `--no-exif` | Skip Pillow EXIF reads (manifest-only scoring) |
| `--csv PATH` | Write CSV summary |
| `--no-report-json` | Suppress JSON report |

## Stage 3: Cross-Verify — `cross_verify_frames.py`

### What it does

Opens each carved AVI video, walks the RIFF/movi structure to extract
individual MJPEG frame chunks, trims trailing padding to the JPEG FFD9 end
marker, computes SHA-256 hashes, and compares them against the hashes of
carved JPEG files. This answers: "which carved frames are redundant copies of
frames already inside a recovered video?"

With `--manifest`, it also uses disk-offset data from the recovery manifest to
classify orphaned frames (those not matching any video) into contiguous disk
regions — remnants of deleted videos that were overwritten before recovery.

### Command

```bash
# Basic cross-verification:
python3 cross_verify_frames.py -o /path/to/recovery

# Full analysis with manifest overlap and photo checking:
python3 cross_verify_frames.py -o /path/to/recovery --manifest --include-photos -v
```

### Benchmark results

| Metric | Value |
|--------|-------|
| JPEGs checked | 2,536 |
| AVI videos analyzed | 45 |
| Total frames inside AVIs | 40,516 |
| Matched to a video | 866 |
| Orphaned (no video match) | 1,670 |
| Match rate (carved JPEGs) | 34.15% |
| Elapsed | 3.2 seconds |
| Deleted-video regions found | 5 |

### Understanding match rates

The match rate depends on how many individually-carved JPEG frames happen to
overlap with carved video file spans on disk. The carver scans linearly: when
it hits an AVI RIFF header, it extracts the entire video and jumps past it.
Frames are only individually carved when a scan chunk boundary falls mid-video.

In this run, 866 of 1,796 frames matched video_00025 (whose scan chunk
boundary fell inside it). The remaining 930 orphaned frames from `frames/`
plus 740 stills checked via `--include-photos` account for the 1,670 orphaned
total — the stills correctly don't match any video.

The 927 frames outside all video disk spans cluster into regions from deleted
videos:

| Region | Disk range | Frames | Interpretation |
|--------|-----------|--------|----------------|
| 1 | 1.7–39.2 MB | 442 | Deleted video remnant |
| 2 | 45.5–80.1 MB | 485 | Deleted video remnant |
| 3 | 2008.4 MB | 1 | Scattered fragment |
| 4 | 2030.9–2031.0 MB | 1 | Scattered fragment |
| 5 | 2047.7–2047.8 MB | 1 | Scattered fragment |

These are frames from videos that existed on the SD card before the camera
formatted it. The videos themselves were overwritten, but individual frames
survived in disk regions that weren't reused.

### Key flags

| Flag | Purpose |
|------|---------|
| `-o` | Same output directory from stages 1–2 |
| `--manifest` | Use recovery_manifest.jsonl for disk-offset overlap analysis |
| `--include-photos` | Also check photos/ for misclassified video frames |
| `--report-json PATH` | Custom path for JSON report |
| `--no-report-json` | Suppress JSON report |
| `-v` | Verbose per-video breakdown |
| `-q` | Quiet mode (totals only) |

## Stage 4: Entropy Scan — `entropy_scanner.py`

### What it does

Reads the raw image in sampled blocks, computes Shannon entropy per block
(0.0–8.0 bits), and classifies each block as empty/pattern, structured,
compressed, or near-random. Cross-references the recovery manifest to
separate already-recovered regions from potentially missed content. Merges
nearby unrecovered high-entropy blocks into regions and probes each for
known file signatures.

### Command

```bash
python3 entropy_scanner.py /path/to/photo-8g.img \
  --manifest /path/to/recovery/.scan_state/recovery_manifest.jsonl \
  --report-json /path/to/recovery/.scan_state/entropy_report.json
```

### Benchmark results

| Metric | Value |
|--------|-------|
| Image size | 7,680 MB |
| Blocks sampled | 122,880 |
| Elapsed | ~62 seconds |
| Empty/pattern blocks | 115 |
| Structured blocks | 74,343 |
| Compressed blocks | 1,165 |
| Near-random blocks | 47,257 |
| High-entropy blocks in recovered files | 48,124 |
| High-entropy blocks NOT recovered | 298 |
| Unrecovered high-entropy regions | 15 |

### Interpreting results

The 298 unrecovered high-entropy blocks cluster into 15 regions. The largest
(73.5 MB at 6–80 MB) overlaps with the deleted-video frame region identified
by the cross-verifier — these are MJPEG frame data from overwritten videos,
individually carved as frames. The remaining 14 regions are small (< 1.5 MB
each) and contain no recognized file signatures, indicating compressed
remnants or noise rather than missed files.

A result of **0 unrecovered high-entropy regions with signatures** means the
carver found everything it could.

### Key flags

| Flag | Purpose |
|------|---------|
| `--manifest PATH` | Cross-reference recovered file spans |
| `--start MB` / `--end MB` | Scan a specific range |
| `--stride-kb N` | Sample resolution (default 64; lower = finer) |
| `--report-json PATH` | Write JSON report |
| `-q` | Quiet mode |

## Full Pipeline (Copy-Paste)

```bash
IMAGE=/path/to/photo-8g.img
OUT=/path/to/recovery

# Stage 1: Carve
python3 media_carver.py "$IMAGE" -o "$OUT"

# Stage 2: Classify and reorganize
python3 media_classifier.py -o "$OUT" --reorganize-buckets --apply-bucket-moves

# Stage 3: Cross-verify
python3 cross_verify_frames.py -o "$OUT" --manifest --include-photos -v

# Stage 4: Entropy scan (optional — verify no missed regions)
python3 entropy_scanner.py "$IMAGE" \
  --manifest "$OUT/.scan_state/recovery_manifest.jsonl" \
  --report-json "$OUT/.scan_state/entropy_report.json"
```

## Final Output Structure

```text
recovery/
  photos/            # verified stills (real camera photos)
  frames/            # video frames (individually carved JPEGs at video resolution)
  videos/            # complete video containers
  .scan_state/
    seen_sha256.txt                   # dedup state
    counters.json                     # carver counters
    scan_log.txt                      # scan progress log
    recovery_manifest.jsonl           # per-file metadata
    classification_report.json        # classifier output
    cross_verification_report.json    # cross-verify output
    entropy_report.json               # entropy scan output
```

## Recovery Summary (photo-8g.img)

| Category | Count | Size | Details |
|----------|-------|------|---------|
| Real stills | 746 | 290 MB | 709 at 4032×2880, 37 at 2560×1440 |
| Video frames | 1,797 | 109 MB | All 1280×720; confirmed in videos or orphaned from deleted videos |
| Videos | 45 | 2.8 GB | MJPEG AVI containers, 40,516 total internal frames |
| SHA-256 duplicates filtered | 363 | — | Deduped during carve |
| Skipped (validation failure) | 22 | — | False JPEG SOI markers, logged with offsets and reasons |
| Deleted-video frame regions | 5 | — | ~927 frames from ≥2 overwritten videos |
| Unrecovered high-entropy regions | 0 | — | No missed regions with recognized signatures |

Total unique files recovered: **2,588** (746 stills + 1,797 frames + 45 videos).

## Troubleshooting

### Scan times out or runs too long

Use manual chunking with `--start` and `--end` to break the image into
smaller ranges. Each chunk is resumable — the carver picks up from prior state.

### Disk space exhaustion

Write output to a volume with at least 50% of the image size free. The
recovered media can approach 40% of image size for a densely populated card.

### Too many "uncertain" classifications

Check that `matches_skip_frame_resolution` covers your camera's video
resolution. The default is 1280×720 and 1920×1080. If your camera shoots 4K
or another resolution, add it via `--skip-video-frame-res` on the carver.

### Low cross-verify match rate

This is expected and normal. Match rate depends on how many scan chunk
boundaries fall inside video files. A low match doesn't indicate missing
data — the frames are already inside the recovered video files. Orphaned
frames that fall outside all video disk spans are remnants of deleted videos.
