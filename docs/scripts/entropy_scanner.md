# entropy_scanner.py

## Purpose

`entropy_scanner.py` scans a raw disk image for regions of high Shannon
entropy that may contain unrecovered compressed media. It provides a
statistical map of the image to identify gaps the carver may have missed
and cross-references recovery manifests to separate already-recovered
high-entropy data from potentially missed content.

Use this as a post-carve validation step to gain confidence that no
recoverable data was left behind.

## Requirements

- Python 3.10+
- No third-party packages (standard library only)
- Read access to the source disk image

## Quick Start

```bash
python3 entropy_scanner.py /path/to/image.img
```

## Common Usage Patterns

### Full scan with manifest cross-reference

```bash
python3 entropy_scanner.py image.img \
  --manifest recovery/.scan_state/recovery_manifest.jsonl
```

### Scan a specific range

```bash
python3 entropy_scanner.py image.img --start 0 --end 500
```

### Fine-grained scan (slower, higher resolution)

```bash
python3 entropy_scanner.py image.img --stride-kb 4 --block-size 4096
```

### Save JSON report

```bash
python3 entropy_scanner.py image.img \
  --manifest recovery/.scan_state/recovery_manifest.jsonl \
  --report-json recovery/.scan_state/entropy_report.json
```

## Arguments and Options

### Required

- `image`: path to raw disk image or block device

### Optional

- `--manifest PATH`: path to `recovery_manifest.jsonl` for cross-referencing
  recovered file spans against entropy data
- `--start MB`: start offset in MB (default: `0`)
- `--end MB`: end offset in MB (default: end of image)
- `--block-size BYTES`: sample block size in bytes (default: `4096`)
- `--stride-kb N`: sample every N KB (default: `64`; lower = slower but higher
  resolution)
- `--report-json PATH`: write JSON report to this path
- `-v`, `--verbose`: verbose output
- `-q`, `--quiet`: suppress progress bar
- `--version`: print version

## Output Structure

### Console report

The report shows block classification counts across four entropy bands:

- **Empty/pattern** (entropy < 1.0): zeroed, wiped, or simple pattern data
- **Structured** (entropy < 5.0): FAT tables, directory entries, metadata
- **Compressed** (entropy < 7.0): compressed media, archives, documents
- **Near-random** (entropy ≥ 7.0): heavily compressed media, encrypted data

When `--manifest` is provided, the report also shows how many high-entropy
blocks fall inside vs outside recovered file spans.

### High-entropy regions

Nearby unrecovered high-entropy blocks are merged into contiguous regions
(2 MB gap threshold). Each region shows disk offset range, size, average
entropy, and any known file signatures detected at the region start.

### JSON report

The `--report-json` output includes all console data plus the full region
list with signature probing results.

## Internal Behavior Summary

1. Opens the image and samples blocks at regular stride intervals.
2. Computes Shannon entropy (0.0–8.0 bits) for each block.
3. Classifies blocks into entropy bands.
4. If manifest is provided, checks each high-entropy block against recovered
   file spans to determine if it's already accounted for.
5. Merges adjacent unrecovered high-entropy blocks into regions.
6. Probes each region start for known file signatures (JPEG, PNG, RIFF, MP4,
   MKV, GIF, BMP, FLV, ASF, MPEG-PS/TS, ZIP, PDF).
7. Prints console report and optionally writes JSON.

## Safety Notes

- Read-only: the scanner never modifies the source image.
- Performance: at default settings (64 KB stride, 4 KB block), a 7.5 GB image
  scans in ~60 seconds. Lower stride values increase resolution but also scan
  time proportionally.

## Known Limitations

- Entropy is statistical, not structural: a high-entropy region may be
  encrypted data, compressed non-media content, or random noise — not
  necessarily recoverable media.
- Signature probing only checks the first bytes of each region. Files that
  start mid-region (after garbage bytes) won't be detected by probing.
- The 2 MB merge threshold may merge unrelated nearby regions or split a
  single large region if it has low-entropy gaps within it.
- MPEG-TS detection (0x47 sync byte) is very prone to false positives as
  a single-byte signature.

## Validation Checklist

- `python3 entropy_scanner.py --help` succeeds.
- Full scan of a known image produces expected entropy distribution.
- `--manifest` cross-reference correctly flags recovered vs unrecovered blocks.
- `--report-json` produces valid JSON.

## Maintenance Notes

When updating this script, keep docs in sync for:

- changes to entropy thresholds or band classification,
- new signature additions,
- changes to region merging logic,
- output format changes.
