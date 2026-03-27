#!/usr/bin/env python3
"""
entropy_scanner.py — Scan a raw disk image for regions with high Shannon
entropy that may contain unrecovered compressed media.

Reads the image in fixed-size sample blocks, computes per-block entropy,
and classifies each block as empty/pattern (low entropy), structured data
(medium), or compressed/encrypted (high). Optionally cross-references a
recovery manifest to highlight unrecovered high-entropy gaps.

Version: 1.0.0
"""

__version__ = "1.0.0"

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional, BinaryIO

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BLOCK_SIZE = 4096          # bytes per sample block
DEFAULT_STRIDE_KB = 64             # sample every N KB
ENTROPY_LOW = 1.0                  # below = empty/pattern
ENTROPY_MED = 5.0                  # below = structured (FAT, headers)
ENTROPY_HIGH = 7.0                 # above = compressed/encrypted
ENTROPY_RANDOM = 7.9               # near-random data threshold

GAP_MERGE_MB = 2.0                 # merge high-entropy blocks within N MB
MIN_REGION_KB = 32                 # ignore high-entropy regions smaller than this

# Known file signatures to probe in high-entropy regions
KNOWN_SIGS = [
    (b"\xff\xd8\xff",      "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"RIFF",              "RIFF (AVI/WAV/WebP)"),
    (b"\x00\x00\x00",      "ISOBMFF (MP4/MOV/HEIF)"),
    (b"\x1a\x45\xdf\xa3",  "Matroska/WebM"),
    (b"GIF8",              "GIF"),
    (b"BM",                "BMP"),
    (b"\x46\x4c\x56\x01",  "FLV"),
    (b"\x30\x26\xb2\x75",  "ASF/WMV"),
    (b"\x00\x00\x01\xba",  "MPEG-PS"),
    (b"\x47",              "MPEG-TS sync"),
    (b"PK\x03\x04",        "ZIP/DOCX/XLSX"),
    (b"\x25\x50\x44\x46",  "PDF"),
]


# ---------------------------------------------------------------------------
# Entropy computation
# ---------------------------------------------------------------------------
def shannon_entropy(data: bytes) -> float:
    """Compute Shannon entropy of a byte sequence (0.0–8.0 bits)."""
    if not data:
        return 0.0
    n = len(data)
    counts = Counter(data)
    entropy = 0.0
    for count in counts.values():
        p = count / n
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


# ---------------------------------------------------------------------------
# Signature probing
# ---------------------------------------------------------------------------
def probe_signatures(f: BinaryIO, offset: int, length: int = 16) -> list[str]:
    """Check the first bytes at offset for known file signatures."""
    f.seek(offset)
    header = f.read(max(length, 16))
    if not header:
        return []
    matches = []
    for sig, name in KNOWN_SIGS:
        if header[:len(sig)] == sig:
            matches.append(name)
    return matches


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------
def load_manifest_spans(
    manifest_path: Path,
) -> list[tuple[int, int, str]]:
    """Load (start, end, format) spans from recovery_manifest.jsonl."""
    spans = []
    with open(manifest_path, "r", encoding="utf-8") as mf:
        for line in mf:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            start = rec.get("source_offset")
            end = rec.get("source_end")
            fmt = rec.get("format", "unknown")
            status = rec.get("status", "recovered")
            if isinstance(start, int) and isinstance(end, int):
                spans.append((start, end, fmt, status))
    return spans


def offset_is_recovered(offset: int, block_size: int, spans) -> bool:
    """Check if an offset falls inside any recovered file span."""
    block_end = offset + block_size
    for start, end, fmt, status in spans:
        if status == "skipped":
            continue
        if offset < end and block_end > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------
def scan_entropy(
    image_path: Path,
    block_size: int,
    stride: int,
    start_mb: float,
    end_mb: Optional[float],
    manifest_spans: Optional[list],
    verbose: bool,
    quiet: bool,
) -> dict:
    """Scan image and return entropy analysis results."""
    image_size = image_path.stat().st_size
    start_offset = int(start_mb * 1024 * 1024)
    end_offset = int(end_mb * 1024 * 1024) if end_mb else image_size

    start_offset = max(0, min(start_offset, image_size))
    end_offset = max(start_offset, min(end_offset, image_size))

    blocks_total = 0
    blocks_empty = 0
    blocks_structured = 0
    blocks_compressed = 0
    blocks_random = 0
    blocks_recovered = 0
    blocks_unrecovered_high = 0

    # Track high-entropy regions for gap analysis
    high_entropy_blocks: list[tuple[int, float, bool]] = []  # (offset, entropy, recovered)

    t0 = time.time()
    with open(image_path, "rb") as f:
        offset = start_offset
        last_pct = -1
        while offset < end_offset:
            f.seek(offset)
            data = f.read(min(block_size, end_offset - offset))
            if not data:
                break

            ent = shannon_entropy(data)
            recovered = False
            if manifest_spans:
                recovered = offset_is_recovered(offset, len(data), manifest_spans)

            blocks_total += 1
            if ent < ENTROPY_LOW:
                blocks_empty += 1
            elif ent < ENTROPY_MED:
                blocks_structured += 1
            elif ent < ENTROPY_HIGH:
                blocks_compressed += 1
                if recovered:
                    blocks_recovered += 1
                else:
                    blocks_unrecovered_high += 1
                    high_entropy_blocks.append((offset, ent, False))
            else:
                blocks_random += 1
                if recovered:
                    blocks_recovered += 1
                else:
                    blocks_unrecovered_high += 1
                    high_entropy_blocks.append((offset, ent, False))

            if not quiet:
                pct = int((offset - start_offset) / max(1, end_offset - start_offset) * 100)
                if pct >= last_pct + 5:
                    last_pct = pct
                    sys.stderr.write(
                        f"\r  {pct}% @ {offset / 1e6:.0f}MB "
                        f"| empty={blocks_empty} struct={blocks_structured} "
                        f"compressed={blocks_compressed} random={blocks_random}"
                    )
                    sys.stderr.flush()

            offset += stride

    elapsed = time.time() - t0
    if not quiet:
        sys.stderr.write("\r" + " " * 80 + "\r")
        sys.stderr.flush()

    # Merge nearby high-entropy blocks into regions
    regions = _merge_high_entropy_regions(high_entropy_blocks, image_path)

    return {
        "image": str(image_path),
        "image_size_mb": round(image_size / (1024 * 1024), 1),
        "scan_range_mb": [round(start_offset / 1e6, 1), round(end_offset / 1e6, 1)],
        "block_size": block_size,
        "stride": stride,
        "blocks_total": blocks_total,
        "blocks_empty": blocks_empty,
        "blocks_structured": blocks_structured,
        "blocks_compressed": blocks_compressed,
        "blocks_random": blocks_random,
        "blocks_in_recovered_files": blocks_recovered,
        "blocks_unrecovered_high_entropy": blocks_unrecovered_high,
        "high_entropy_regions": regions,
        "elapsed_seconds": round(elapsed, 2),
    }


def _merge_high_entropy_regions(
    blocks: list[tuple[int, float, bool]],
    image_path: Path,
) -> list[dict]:
    """Merge nearby high-entropy blocks into contiguous regions."""
    if not blocks:
        return []

    merge_gap = int(GAP_MERGE_MB * 1024 * 1024)
    sorted_blocks = sorted(blocks, key=lambda b: b[0])

    regions = []
    region_start = sorted_blocks[0][0]
    region_end = sorted_blocks[0][0]
    region_entropies = [sorted_blocks[0][1]]

    for offset, ent, _ in sorted_blocks[1:]:
        if offset - region_end <= merge_gap:
            region_end = offset
            region_entropies.append(ent)
        else:
            regions.append(_finalize_region(
                region_start, region_end, region_entropies, image_path
            ))
            region_start = offset
            region_end = offset
            region_entropies = [ent]

    regions.append(_finalize_region(
        region_start, region_end, region_entropies, image_path
    ))

    # Filter tiny regions
    min_bytes = MIN_REGION_KB * 1024
    return [r for r in regions if r["size_bytes"] >= min_bytes]


def _finalize_region(
    start: int, end: int, entropies: list[float], image_path: Path
) -> dict:
    """Build region dict with signature probing."""
    size = end - start
    avg_ent = sum(entropies) / len(entropies) if entropies else 0

    # Probe for file signatures at region start
    sigs = []
    try:
        with open(image_path, "rb") as f:
            sigs = probe_signatures(f, start)
    except Exception:
        pass

    return {
        "start_mb": round(start / (1024 * 1024), 2),
        "end_mb": round(end / (1024 * 1024), 2),
        "size_bytes": size,
        "size_readable": _human_size(size),
        "sample_count": len(entropies),
        "avg_entropy": round(avg_ent, 3),
        "max_entropy": round(max(entropies), 3) if entropies else 0,
        "signatures_at_start": sigs,
    }


def _human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="entropy_scanner",
        description=(
            "Scan a raw disk image for unrecovered high-entropy regions "
            "that may contain compressed media missed by the carver."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Quick scan of full image:\n"
            "  python3 entropy_scanner.py image.img\n\n"
            "  # Detailed scan with manifest cross-reference:\n"
            "  python3 entropy_scanner.py image.img --manifest recovery/.scan_state/recovery_manifest.jsonl\n\n"
            "  # Scan specific range:\n"
            "  python3 entropy_scanner.py image.img --start 0 --end 500\n\n"
            "  # Fine-grained scan (slower, higher resolution):\n"
            "  python3 entropy_scanner.py image.img --stride-kb 4 --block-size 4096\n"
        ),
    )
    parser.add_argument("image", type=Path, help="Path to raw disk image or block device")
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="Path to recovery_manifest.jsonl for cross-referencing recovered file spans",
    )
    parser.add_argument(
        "--start", type=float, default=0,
        help="Start offset in MB (default: 0)",
    )
    parser.add_argument(
        "--end", type=float, default=None,
        help="End offset in MB (default: end of image)",
    )
    parser.add_argument(
        "--block-size", type=int, default=DEFAULT_BLOCK_SIZE,
        help=f"Sample block size in bytes (default: {DEFAULT_BLOCK_SIZE})",
    )
    parser.add_argument(
        "--stride-kb", type=int, default=DEFAULT_STRIDE_KB,
        help=f"Sample every N KB (default: {DEFAULT_STRIDE_KB}; lower = slower but higher resolution)",
    )
    parser.add_argument(
        "--report-json", type=Path, default=None,
        help="Write JSON report to this path",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress bar")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    if not args.image.exists():
        print(f"Error: image not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    manifest_spans = None
    if args.manifest:
        if not args.manifest.exists():
            print(f"Error: manifest not found: {args.manifest}", file=sys.stderr)
            sys.exit(1)
        manifest_spans = load_manifest_spans(args.manifest)
        if not args.quiet:
            print(f"Loaded {len(manifest_spans)} manifest records.", file=sys.stderr)

    stride_bytes = args.stride_kb * 1024

    if not args.quiet:
        image_mb = args.image.stat().st_size / (1024 * 1024)
        print(
            f"Scanning {args.image.name} ({image_mb:.0f} MB), "
            f"block={args.block_size}B, stride={args.stride_kb}KB",
            file=sys.stderr,
        )

    results = scan_entropy(
        image_path=args.image,
        block_size=args.block_size,
        stride=stride_bytes,
        start_mb=args.start,
        end_mb=args.end,
        manifest_spans=manifest_spans,
        verbose=args.verbose,
        quiet=args.quiet,
    )

    # Print report
    print()
    print("=" * 70)
    print("  ENTROPY SCAN REPORT")
    print("=" * 70)
    print()
    print(f"  Image:              {results['image']}")
    print(f"  Image size:         {results['image_size_mb']} MB")
    r = results['scan_range_mb']
    print(f"  Scan range:         {r[0]:.0f}–{r[1]:.0f} MB")
    print(f"  Blocks sampled:     {results['blocks_total']}")
    print(f"  Elapsed:            {results['elapsed_seconds']}s")
    print()
    print(f"  Block classification:")
    print(f"    Empty/pattern  (entropy <{ENTROPY_LOW}):  {results['blocks_empty']}")
    print(f"    Structured     (entropy <{ENTROPY_MED}):  {results['blocks_structured']}")
    print(f"    Compressed     (entropy <{ENTROPY_HIGH}):  {results['blocks_compressed']}")
    print(f"    Near-random    (entropy ≥{ENTROPY_HIGH}):  {results['blocks_random']}")
    print()

    if manifest_spans is not None:
        print(f"  Manifest cross-reference:")
        print(f"    High-entropy blocks inside recovered files:  {results['blocks_in_recovered_files']}")
        print(f"    High-entropy blocks NOT recovered:           {results['blocks_unrecovered_high_entropy']}")
        print()

    regions = results["high_entropy_regions"]
    if regions:
        print(f"  Unrecovered high-entropy regions: {len(regions)}")
        print()
        for i, r in enumerate(regions, 1):
            sigs = ", ".join(r["signatures_at_start"]) if r["signatures_at_start"] else "none"
            print(
                f"    Region {i}: {r['start_mb']:.2f}–{r['end_mb']:.2f} MB "
                f"({r['size_readable']}, avg entropy {r['avg_entropy']:.2f}, "
                f"sigs: {sigs})"
            )
    else:
        print("  No unrecovered high-entropy regions found.")

    print()
    print("=" * 70)

    # Write JSON report
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_json, "w", encoding="utf-8") as jf:
            json.dump(results, jf, indent=2)
        print(f"\nReport: {args.report_json}")


if __name__ == "__main__":
    main()
