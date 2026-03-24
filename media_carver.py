#!/usr/bin/env python3
"""
media_carver.py — Production-ready media file carver for raw disk images and devices.
 
Recovers photos and videos from raw disk images, SD cards, USB drives, or any
block device by scanning for known file signatures (file carving). Handles
fragmented scans with persistent deduplication state so large images can be
processed in chunks without duplicating output.
 
Supported image formats:
  JPEG (.jpg)       PNG (.png)        TIFF (.tif)       BMP (.bmp)
  GIF (.gif)        WebP (.webp)      HEIF/HEIC (.heif) AVIF (.avif)
  Canon CR2 (.cr2)  Canon CR3 (.cr3)  Nikon NEF (.nef)  Sony ARW (.arw)
  Adobe DNG (.dng)  Olympus ORF (.orf) Fuji RAF (.raf)
  Panasonic RW2 (.rw2)  Samsung SRW (.srw)  Pentax PEF (.pef)
 
Supported video formats:
  AVI (.avi)        MP4/MOV (.mp4)    Matroska/WebM (.mkv)
  MPEG-TS (.mts)    MPEG-PS (.mpg)    FLV (.flv)
  ASF/WMV (.wmv)    3GP (.3gp)
 
Usage:
  # Full scan (auto-chunks internally):
  python3 media_carver.py /path/to/image.img -o /path/to/output
 
  # Scan a specific byte range (for manual chunking):
  python3 media_carver.py /path/to/image.img -o /out --start 0 --end 1024
 
  # Scan a raw device:
  sudo python3 media_carver.py /dev/sdb -o /recovery
 
  # Skip video frames embedded in AVI containers:
  python3 media_carver.py image.img -o /out --skip-video-frame-res 1280x720
 
  # Custom min file size:
  python3 media_carver.py image.img -o /out --min-size 50000
 
  # Reset state (re-scan from scratch):
  python3 media_carver.py image.img -o /out --reset
"""
 
from __future__ import annotations
 
import argparse
import hashlib
import io
import json
import logging
import os
import plistlib
import stat
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Optional
 
# ---------------------------------------------------------------------------
# Optional PIL — gracefully degrade if unavailable
# ---------------------------------------------------------------------------
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
 
SCAN_BUFFER       = 32 * 1024 * 1024   # 32 MB read buffer per pass
EXTRACT_BUFFER    = 4 * 1024 * 1024    # 4 MB streaming write buffer
HASH_SAMPLE_BYTES = 64 * 1024          # First 64 KB for fingerprint
OVERLAP_BYTES     = 64                  # Overlap between scan buffers
DEFAULT_CHUNK_MB  = 768                 # Default chunk size for auto mode
 
# Valid JPEG marker bytes after FFD8FF
VALID_JPEG_MARKS  = {0xe0, 0xe1, 0xe2, 0xe3, 0xdb, 0xc0, 0xc2, 0xc4, 0xee, 0xed, 0xfe}
 
MAX_PHOTO_SIZE    = 80 * 1024 * 1024   # 80 MB ceiling per photo
MAX_VIDEO_SIZE    = 8 * 1024 * 1024 * 1024  # 8 GB ceiling per video
MIN_PHOTO_SIZE    = 4 * 1024           # 4 KB floor for photos
MIN_VIDEO_SIZE    = 50 * 1024          # 50 KB floor for videos
MIN_DIMENSION     = 32                 # Minimum pixel dimension
 
 
class MediaType(Enum):
    PHOTO = "photo"
    VIDEO = "video"
 
 
# ---------------------------------------------------------------------------
# Format signature definitions
# ---------------------------------------------------------------------------
@dataclass
class FormatSignature:
    """Defines how to detect and extract a particular file format."""
    name: str
    media_type: MediaType
    extension: str
    # Signature bytes and the offset within the file where they appear
    magic: bytes
    magic_offset: int = 0
    # Optional secondary validation bytes (e.g., "AVI " at offset 8 in RIFF)
    magic2: Optional[bytes] = None
    magic2_offset: Optional[int] = None
    # How to determine the file's end
    end_strategy: str = "marker"   # "marker", "header_size", "atom_walk", "mpeg_ts"
    end_marker: Optional[bytes] = None
    max_size: int = MAX_PHOTO_SIZE
    min_size: int = MIN_PHOTO_SIZE
 
 
# ── Image signatures ──────────────────────────────────────────────────
JPEG_SIG = FormatSignature(
    name="JPEG", media_type=MediaType.PHOTO, extension="jpg",
    magic=b"\xff\xd8\xff", end_strategy="jpeg_eoi",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
PNG_SIG = FormatSignature(
    name="PNG", media_type=MediaType.PHOTO, extension="png",
    magic=b"\x89PNG\r\n\x1a\n", end_strategy="png_iend",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
BMP_SIG = FormatSignature(
    name="BMP", media_type=MediaType.PHOTO, extension="bmp",
    magic=b"BM", end_strategy="bmp_header",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
GIF87_SIG = FormatSignature(
    name="GIF87a", media_type=MediaType.PHOTO, extension="gif",
    magic=b"GIF87a", end_strategy="gif_trailer",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
GIF89_SIG = FormatSignature(
    name="GIF89a", media_type=MediaType.PHOTO, extension="gif",
    magic=b"GIF89a", end_strategy="gif_trailer",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
TIFF_LE_SIG = FormatSignature(
    name="TIFF-LE", media_type=MediaType.PHOTO, extension="tif",
    magic=b"II\x2a\x00", end_strategy="tiff_ifd",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
TIFF_BE_SIG = FormatSignature(
    name="TIFF-BE", media_type=MediaType.PHOTO, extension="tif",
    magic=b"MM\x00\x2a", end_strategy="tiff_ifd",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
WEBP_SIG = FormatSignature(
    name="WebP", media_type=MediaType.PHOTO, extension="webp",
    magic=b"RIFF", magic2=b"WEBP", magic2_offset=8,
    end_strategy="riff_size",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
# HEIF/HEIC (ftyp box with heic/heix/mif1 brand)
HEIF_SIG = FormatSignature(
    name="HEIF", media_type=MediaType.PHOTO, extension="heif",
    magic=b"ftyp", magic_offset=4, end_strategy="isobmff_walk",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
# AVIF (ftyp box with avif/avis brand)
AVIF_SIG = FormatSignature(
    name="AVIF", media_type=MediaType.PHOTO, extension="avif",
    magic=b"ftyp", magic_offset=4, end_strategy="isobmff_walk",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
# Canon CR3 is ISOBMFF-based (ftyp crx)
CR3_SIG = FormatSignature(
    name="CR3", media_type=MediaType.PHOTO, extension="cr3",
    magic=b"ftyp", magic_offset=4, end_strategy="isobmff_walk",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
# Fuji RAF
RAF_SIG = FormatSignature(
    name="RAF", media_type=MediaType.PHOTO, extension="raf",
    magic=b"FUJIFILMCCD-RAW", end_strategy="raf_header",
    max_size=MAX_PHOTO_SIZE, min_size=MIN_PHOTO_SIZE,
)
 
# Panasonic RW2 (TIFF-based, same magic as TIFF-LE but with specific IFD tag)
# Olympus ORF, Sony ARW, Nikon NEF, Adobe DNG, Pentax PEF, Samsung SRW
# are all TIFF-based — handled by the TIFF detector with brand sniffing.
 
# ── Video signatures ──────────────────────────────────────────────────
AVI_SIG = FormatSignature(
    name="AVI", media_type=MediaType.VIDEO, extension="avi",
    magic=b"RIFF", magic2=b"AVI ", magic2_offset=8,
    end_strategy="riff_size",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
# MP4/MOV/3GP — all ISO Base Media File Format (ISOBMFF)
MP4_SIG = FormatSignature(
    name="MP4/MOV", media_type=MediaType.VIDEO, extension="mp4",
    magic=b"ftyp", magic_offset=4, end_strategy="isobmff_walk",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
MKV_SIG = FormatSignature(
    name="Matroska", media_type=MediaType.VIDEO, extension="mkv",
    magic=b"\x1a\x45\xdf\xa3", end_strategy="ebml_walk",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
FLV_SIG = FormatSignature(
    name="FLV", media_type=MediaType.VIDEO, extension="flv",
    magic=b"FLV\x01", end_strategy="flv_tags",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
ASF_SIG = FormatSignature(
    name="ASF/WMV", media_type=MediaType.VIDEO, extension="wmv",
    magic=b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"
          b"\xa6\xd9\x00\xaa\x00\x62\xce\x6c",
    end_strategy="asf_header",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
MPEG_PS_SIG = FormatSignature(
    name="MPEG-PS", media_type=MediaType.VIDEO, extension="mpg",
    magic=b"\x00\x00\x01\xba", end_strategy="mpeg_ps_scan",
    max_size=MAX_VIDEO_SIZE, min_size=MIN_VIDEO_SIZE,
)
 
# MPEG-TS is detected specially (sync byte pattern, not a simple magic)
 
# Ordered by detection priority — more specific first
ALL_SIGNATURES: list[FormatSignature] = [
    JPEG_SIG, PNG_SIG, GIF87_SIG, GIF89_SIG, BMP_SIG,
    RAF_SIG,           # Fuji (unique 15-byte magic)
    WEBP_SIG, AVI_SIG, # RIFF-based (disambiguated by magic2)
    TIFF_LE_SIG, TIFF_BE_SIG,  # TIFF-based (also CR2, NEF, ARW, DNG, etc.)
    MKV_SIG, FLV_SIG, ASF_SIG, MPEG_PS_SIG,
    # ISOBMFF-based (ftyp): MP4, MOV, HEIF, AVIF, CR3, 3GP — handled together
    MP4_SIG,
]
 
# ftyp brand -> (format_name, extension, media_type)
FTYP_BRANDS: dict[str, tuple[str, str, MediaType]] = {
    # Video
    "isom": ("MP4",   "mp4",  MediaType.VIDEO),
    "iso2": ("MP4",   "mp4",  MediaType.VIDEO),
    "iso5": ("MP4",   "mp4",  MediaType.VIDEO),
    "iso6": ("MP4",   "mp4",  MediaType.VIDEO),
    "mp41": ("MP4",   "mp4",  MediaType.VIDEO),
    "mp42": ("MP4",   "mp4",  MediaType.VIDEO),
    "M4V ": ("M4V",   "m4v",  MediaType.VIDEO),
    "M4A ": ("M4A",   "m4a",  MediaType.VIDEO),
    "qt  ": ("MOV",   "mov",  MediaType.VIDEO),
    "3gp4": ("3GP",   "3gp",  MediaType.VIDEO),
    "3gp5": ("3GP",   "3gp",  MediaType.VIDEO),
    "3gp6": ("3GP",   "3gp",  MediaType.VIDEO),
    "3g2a": ("3G2",   "3g2",  MediaType.VIDEO),
    "dash": ("DASH",  "mp4",  MediaType.VIDEO),
    "avc1": ("MP4",   "mp4",  MediaType.VIDEO),
    # Photo
    "heic": ("HEIC",  "heic", MediaType.PHOTO),
    "heix": ("HEIC",  "heic", MediaType.PHOTO),
    "mif1": ("HEIF",  "heif", MediaType.PHOTO),
    "msf1": ("HEIF",  "heif", MediaType.PHOTO),
    "avif": ("AVIF",  "avif", MediaType.PHOTO),
    "avis": ("AVIF",  "avif", MediaType.PHOTO),
    "crx ": ("CR3",   "cr3",  MediaType.PHOTO),
}
 
# TIFF-based RAW brand detection: check Make tag (0x010F) in IFD
TIFF_RAW_MAKES: dict[str, tuple[str, str]] = {
    "NIKON":         ("NEF",  "nef"),
    "SONY":          ("ARW",  "arw"),
    "Canon":         ("CR2",  "cr2"),
    "OLYMPUS":       ("ORF",  "orf"),
    "Panasonic":     ("RW2",  "rw2"),
    "SAMSUNG":       ("SRW",  "srw"),
    "PENTAX":        ("PEF",  "pef"),
    "RICOH":         ("DNG",  "dng"),
    "DNG":           ("DNG",  "dng"),
    "Adobe":         ("DNG",  "dng"),
    "FUJIFILM":      ("RAF",  "raf"),
    "Phase One":     ("IIQ",  "iiq"),
    "Leica":         ("DNG",  "dng"),
    "Hasselblad":    ("3FR",  "3fr"),
}
 
 
# ---------------------------------------------------------------------------
# Persistent state manager
# ---------------------------------------------------------------------------
class ScanState:
    """Tracks seen file hashes and sequential counters across scan sessions."""
 
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
 
        self._hash_path = state_dir / "seen_hashes.txt"
        self._sha256_path = state_dir / "seen_sha256.txt"
        self._counter_path = state_dir / "counters.json"
        self._log_path = state_dir / "scan_log.txt"
 
        self._seen: set[str] = set()
        self._seen_sha256: set[str] = set()
        self._counters: dict[str, int] = {"photo": 0, "video": 0}
        self._load()
 
    # ── persistence ───────────────────────────────────────────────────
    def _load(self):
        if self._hash_path.exists():
            with open(self._hash_path) as f:
                self._seen = {l.strip() for l in f if l.strip()}
        if self._sha256_path.exists():
            with open(self._sha256_path) as f:
                self._seen_sha256 = {l.strip() for l in f if l.strip()}
        if self._counter_path.exists():
            with open(self._counter_path) as f:
                self._counters = json.load(f)
 
    def _flush_counters(self):
        with open(self._counter_path, "w") as f:
            json.dump(self._counters, f)
 
    def reset(self):
        self._seen.clear()
        self._seen_sha256.clear()
        self._counters = {"photo": 0, "video": 0}
        for p in (self._hash_path, self._sha256_path, self._counter_path, self._log_path):
            p.unlink(missing_ok=True)
 
    # ── dedup ─────────────────────────────────────────────────────────
    @staticmethod
    def fingerprint(data: bytes) -> str:
        return hashlib.md5(data[:HASH_SAMPLE_BYTES]).hexdigest()
 
    def is_seen(self, fp: str) -> bool:
        return fp in self._seen
 
    def record(self, fp: str):
        self._seen.add(fp)
        with open(self._hash_path, "a") as f:
            f.write(fp + "\n")

    def is_sha256_seen(self, digest: str) -> bool:
        return digest in self._seen_sha256

    def record_sha256(self, digest: str):
        self._seen_sha256.add(digest)
        with open(self._sha256_path, "a") as f:
            f.write(digest + "\n")
 
    # ── counters ──────────────────────────────────────────────────────
    def next_id(self, media_type: MediaType) -> int:
        key = media_type.value
        self._counters[key] = self._counters.get(key, 0) + 1
        self._flush_counters()
        return self._counters[key]
 
    # ── log ───────────────────────────────────────────────────────────
    def log(self, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        logging.info(msg)
        with open(self._log_path, "a") as f:
            f.write(line + "\n")
 
    @property
    def hash_count(self) -> int:
        return len(self._seen)

    @property
    def sha256_count(self) -> int:
        return len(self._seen_sha256)
 
 
# ---------------------------------------------------------------------------
# End-of-file detection strategies
# ---------------------------------------------------------------------------
def _find_jpeg_eoi(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Find JPEG End-Of-Image marker (0xFFD9)."""
    f.seek(start)
    buf = b""
    read = 0
    while read < max_size:
        chunk = f.read(min(256 * 1024, max_size - read))
        if not chunk:
            break
        buf += chunk
        read += len(chunk)
        idx = buf.find(b"\xff\xd9", max(0, len(buf) - len(chunk) - 1))
        if idx != -1:
            return start + idx + 2
        buf = buf[-1:]
    return None
 
 
def _find_png_iend(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk PNG chunks to find IEND."""
    f.seek(start + 8)  # skip signature
    pos = 8
    while pos < max_size:
        hdr = f.read(8)
        if len(hdr) < 8:
            return None
        length = struct.unpack(">I", hdr[:4])[0]
        chunk_type = hdr[4:8]
        # Skip data + CRC (4 bytes)
        f.seek(length + 4, os.SEEK_CUR)
        pos += 12 + length
        if chunk_type == b"IEND":
            return start + pos
    return None
 
 
def _find_gif_trailer(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Scan for GIF trailer byte (0x3B)."""
    f.seek(start)
    data = f.read(min(max_size, 20 * 1024 * 1024))
    # GIF trailer is 0x3B after all blocks
    idx = len(data) - 1
    # Search backward for trailer
    while idx > 13:
        if data[idx] == 0x3B:
            return start + idx + 1
        idx -= 1
    # Forward search fallback
    for i in range(13, len(data)):
        if data[i] == 0x3B:
            return start + i + 1
    return None
 
 
def _find_riff_size(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """RIFF container size is in the header (bytes 4-8, LE uint32)."""
    f.seek(start + 4)
    raw = f.read(4)
    if len(raw) < 4:
        return None
    size = struct.unpack("<I", raw)[0] + 8  # +8 for RIFF header
    if size < 100 or size > max_size:
        return None
    return start + size
 
 
def _find_bmp_size(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """BMP size detection with basic header sanity checks."""
    f.seek(start)
    hdr = f.read(54)
    if len(hdr) < 30 or hdr[:2] != b"BM":
        return None

    size = struct.unpack("<I", hdr[2:6])[0]
    pixel_offset = struct.unpack("<I", hdr[10:14])[0]
    dib_size = struct.unpack("<I", hdr[14:18])[0]

    if size < 100 or size > max_size:
        return None
    if pixel_offset < 14 or pixel_offset >= size:
        return None
    if dib_size not in (12, 40, 52, 56, 108, 124):
        return None

    # DIB header v3+ fields (most common modern BMP variants).
    if dib_size >= 40 and len(hdr) >= 38:
        width = struct.unpack("<i", hdr[18:22])[0]
        height = struct.unpack("<i", hdr[22:26])[0]
        planes = struct.unpack("<H", hdr[26:28])[0]
        bpp = struct.unpack("<H", hdr[28:30])[0]

        if width == 0 or height == 0 or planes != 1:
            return None
        if bpp not in (1, 4, 8, 16, 24, 32):
            return None

        # For uncompressed RGB bitmaps, estimate expected payload size.
        if len(hdr) >= 38:
            compression = struct.unpack("<I", hdr[30:34])[0]
            image_size = struct.unpack("<I", hdr[34:38])[0]
            if compression == 0:  # BI_RGB
                w = abs(width)
                h = abs(height)
                row_bytes = ((w * bpp + 31) // 32) * 4
                estimated_payload = row_bytes * h
                estimated_total = pixel_offset + estimated_payload
                # Accept reasonable variance; reject obviously inflated size fields.
                if estimated_total > 0 and size > max(estimated_total * 3, estimated_total + 2 * 1024 * 1024):
                    return None
            elif compression not in (3, 6):  # allow BI_BITFIELDS / BI_ALPHABITFIELDS
                return None
            if image_size > 0 and image_size > max_size:
                return None

    return start + size
 
 
def _walk_isobmff(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk ISO Base Media File Format boxes (MP4, MOV, HEIF, AVIF, CR3, 3GP)."""
    f.seek(start)
    pos = 0
    while pos < max_size:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        size = struct.unpack(">I", hdr[:4])[0]
        box_type = hdr[4:8]
 
        if size == 1:
            # 64-bit extended size
            ext = f.read(8)
            if len(ext) < 8:
                break
            size = struct.unpack(">Q", ext)[0]
        elif size == 0:
            # Box extends to end of file — use remaining max_size
            return start + max_size
 
        if size < 8:
            break
 
        pos += size
        f.seek(start + pos)
 
        # If we've seen at least ftyp + one more box, this is valid
        if box_type == b"mdat" or pos > max_size:
            return start + pos
 
    return start + pos if pos > 100 else None
 
 
def _walk_ebml(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Estimate Matroska/WebM file size from EBML header + Segment element."""
    def _read_vint(stream: BinaryIO) -> Optional[tuple[int, int]]:
        """Read EBML variable-length integer. Returns (value, length)."""
        first = stream.read(1)
        if not first:
            return None
        b0 = first[0]
        mask = 0x80
        length = 1
        while length <= 8 and (b0 & mask) == 0:
            mask >>= 1
            length += 1
        if length > 8:
            return None
        value = b0 & (mask - 1)
        if length > 1:
            rest = stream.read(length - 1)
            if len(rest) != length - 1:
                return None
            for x in rest:
                value = (value << 8) | x
        return value, length

    f.seek(start)
    # Read EBML header
    hdr = f.read(4)
    if hdr != b"\x1a\x45\xdf\xa3":
        return None
 
    # Read EBML header size (variable-length)
    ebml_vint = _read_vint(f)
    if not ebml_vint:
        return None
    ebml_size, ebml_vint_len = ebml_vint
 
    # Skip EBML header content using true VINT length
    f.seek(start + 4 + ebml_vint_len + ebml_size)
 
    # Next should be Segment (0x18538067)
    seg_id = f.read(4)
    if seg_id != b"\x18\x53\x80\x67":
        # Try a generous estimate
        return None
 
    seg_vint = _read_vint(f)
    if not seg_vint:
        return None
    seg_size, seg_vint_len = seg_vint

    # Unknown-size Segment (all value bits set) is valid EBML;
    # return conservative cap for carving.
    unknown_marker = (1 << (7 * seg_vint_len)) - 1
    if seg_size == unknown_marker:
        return start + max_size
 
    if seg_size <= 0 or seg_size > max_size:
        return None
 
    end = f.tell() + seg_size
    return end if end - start > 1000 else None
 
 
def _find_flv_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk FLV tags to find file end."""
    f.seek(start)
    header = f.read(9)
    if len(header) < 9 or header[:3] != b"FLV":
        return None
 
    data_offset = struct.unpack(">I", header[5:9])[0]
    f.seek(start + data_offset)
    pos = data_offset
 
    # Read PreviousTagSize0 (always 0)
    pts = f.read(4)
    if len(pts) < 4:
        return None
    pos += 4
 
    while pos < max_size:
        tag_header = f.read(11)
        if len(tag_header) < 11:
            return start + pos
 
        tag_type = tag_header[0]
        tag_data_size = (tag_header[1] << 16) | (tag_header[2] << 8) | tag_header[3]
 
        if tag_type not in (8, 9, 18):  # audio, video, script
            return start + pos
 
        # Skip tag data + PreviousTagSize (4 bytes)
        skip = tag_data_size + 4
        f.seek(skip, os.SEEK_CUR)
        pos += 11 + skip
 
    return start + pos if pos > 100 else None
 
 
def _find_asf_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Read ASF/WMV header for file size."""
    f.seek(start + 16)  # skip ASF header GUID
    raw = f.read(8)
    if len(raw) < 8:
        return None
    # Object size is 64-bit LE at offset 16
    size = struct.unpack("<Q", raw)[0]
    if size < 100 or size > max_size:
        return None
    # This is just the header object size; real file could be bigger
    # Try reading Data Object size next
    f.seek(start + size)  # end of header object
    guid = f.read(16)
    data_size_raw = f.read(8)
    if len(data_size_raw) >= 8:
        data_size = struct.unpack("<Q", data_size_raw)[0]
        total = size + data_size
        if total > 1000:
            return start + total
    return None
 
 
def _find_mpeg_ps_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Scan forward for MPEG Program Stream end code (0x000001B9)."""
    f.seek(start)
    end_code = b"\x00\x00\x01\xb9"
    read = 0
    buf = b""
    while read < min(max_size, 500 * 1024 * 1024):  # cap at 500MB search
        chunk = f.read(1024 * 1024)
        if not chunk:
            break
        buf += chunk
        read += len(chunk)
        idx = buf.find(end_code, max(0, len(buf) - len(chunk) - 3))
        if idx != -1:
            return start + idx + 4
        buf = buf[-3:]
    # If no end code, estimate from last pack header
    return start + read if read > MIN_VIDEO_SIZE else None
 
 
def _find_tiff_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Estimate TIFF/RAW file size by walking IFDs and finding max offset+size."""
    f.seek(start)
    header = f.read(8)
    if len(header) < 8:
        return None
 
    endian = "<" if header[:2] == b"II" else ">"
    ifd_offset = struct.unpack(endian + "I", header[4:8])[0]
    max_end = ifd_offset
 
    visited_ifds = set()
 
    def walk_ifd(off: int):
        nonlocal max_end
        if off in visited_ifds or off > max_size or off < 8:
            return
        visited_ifds.add(off)
 
        try:
            f.seek(start + off)
            num_raw = f.read(2)
            if len(num_raw) < 2:
                return
            num_entries = struct.unpack(endian + "H", num_raw)[0]
            if num_entries > 2000:
                return
 
            for _ in range(num_entries):
                entry = f.read(12)
                if len(entry) < 12:
                    return
                tag, typ, count, value = struct.unpack(endian + "HHII", entry)
 
                # Track strip/tile offsets + byte counts
                if tag in (273, 324, 279, 325):
                    if count == 1:
                        if tag in (273, 324):
                            end = value
                        else:
                            end = value
                        if end > max_end:
                            max_end = end
                    elif count > 1 and value < max_size:
                        cur_pos = f.tell()
                        f.seek(start + value)
                        for _ in range(min(count, 5000)):
                            v_raw = f.read(4)
                            if len(v_raw) < 4:
                                break
                            v = struct.unpack(endian + "I", v_raw)[0]
                            if v > max_end:
                                max_end = v
                        f.seek(cur_pos)
 
                # SubIFD offsets
                if tag in (330, 34665, 34853):
                    if count == 1 and value > 0:
                        walk_ifd(value)
 
                # Track any offset values
                if typ in (3, 4) and count == 1 and value > max_end and value < max_size:
                    max_end = value
 
            # Next IFD
            next_raw = f.read(4)
            if len(next_raw) >= 4:
                next_ifd = struct.unpack(endian + "I", next_raw)[0]
                if next_ifd > 0:
                    walk_ifd(next_ifd)
 
        except Exception:
            pass
 
    walk_ifd(ifd_offset)
 
    # The max_end is likely a strip offset; add some padding for the last strip
    # A more accurate approach reads StripByteCounts for the last strip.
    # For safety, add 10% or 1MB, whichever is smaller
    padding = min(max_end // 10, 1024 * 1024)
    estimated = max_end + padding
 
    return start + estimated if estimated > 1000 else None
 
 
def _find_raf_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Fuji RAF: read JPEG and RAW data offsets from the RAF header."""
    f.seek(start + 84)  # RAF offset table at byte 84
    raw = f.read(12)
    if len(raw) < 12:
        return None
    # Byte 84: JPEG offset, 88: JPEG length, 92: RAW offset
    # Byte 100: RAW data offset, 104: RAW data length
    f.seek(start + 100)
    raw2 = f.read(8)
    if len(raw2) < 8:
        return start + 1024 * 1024  # guess 1MB
    raw_offset = struct.unpack(">I", raw2[:4])[0]
    raw_length = struct.unpack(">I", raw2[4:8])[0]
    end = raw_offset + raw_length
    return start + end if end > 1000 else None
 
 
# Strategy dispatcher
END_FINDERS = {
    "jpeg_eoi":     _find_jpeg_eoi,
    "png_iend":     _find_png_iend,
    "gif_trailer":  _find_gif_trailer,
    "riff_size":    _find_riff_size,
    "bmp_header":   _find_bmp_size,
    "isobmff_walk": _walk_isobmff,
    "ebml_walk":    _walk_ebml,
    "flv_tags":     _find_flv_end,
    "asf_header":   _find_asf_end,
    "mpeg_ps_scan": _find_mpeg_ps_end,
    "tiff_ifd":     _find_tiff_end,
    "raf_header":   _find_raf_end,
}
 
 
# ---------------------------------------------------------------------------
# TIFF sub-format detection
# ---------------------------------------------------------------------------
def detect_tiff_subformat(f: BinaryIO, start: int) -> tuple[str, str]:
    """Detect if a TIFF file is actually CR2, NEF, ARW, DNG, etc."""
    f.seek(start)
    header = f.read(8)
    if len(header) < 8:
        return "TIFF", "tif"
 
    endian = "<" if header[:2] == b"II" else ">"
 
    # CR2 check: bytes 8-9 == 0x2A 0x00 for TIFF, but CR2 has "CR" at offset 8
    f.seek(start + 8)
    extra = f.read(4)
    if len(extra) >= 2 and extra[:2] == b"CR":
        return "CR2", "cr2"
 
    # Walk IFD0 for Make tag (0x010F)
    ifd_offset = struct.unpack(endian + "I", header[4:8])[0]
    if ifd_offset > 10 * 1024 * 1024:
        return "TIFF", "tif"
 
    try:
        f.seek(start + ifd_offset)
        num_raw = f.read(2)
        if len(num_raw) < 2:
            return "TIFF", "tif"
        num_entries = struct.unpack(endian + "H", num_raw)[0]
        if num_entries > 1000:
            return "TIFF", "tif"
 
        for _ in range(num_entries):
            entry = f.read(12)
            if len(entry) < 12:
                break
            tag, typ, count, value = struct.unpack(endian + "HHII", entry)
            if tag == 0x010F:  # Make
                # Value is offset to string if count > 4
                if count <= 4:
                    make_str = entry[8:8+count].decode("ascii", errors="replace").strip("\x00")
                else:
                    cur = f.tell()
                    f.seek(start + value)
                    make_str = f.read(min(count, 64)).decode("ascii", errors="replace").strip("\x00")
                    f.seek(cur)
 
                for key, (fmt, ext) in TIFF_RAW_MAKES.items():
                    if key.lower() in make_str.lower():
                        return fmt, ext
                break
    except Exception:
        pass
 
    return "TIFF", "tif"
 
 
# ---------------------------------------------------------------------------
# ISOBMFF brand detection
# ---------------------------------------------------------------------------
def detect_ftyp_brand(f: BinaryIO, start: int) -> tuple[str, str, MediaType]:
    """Read the ftyp box major_brand to determine MP4 vs HEIF vs AVIF vs CR3."""
    f.seek(start)
    hdr = f.read(8)
    if len(hdr) < 8:
        return "MP4", "mp4", MediaType.VIDEO
 
    box_size = struct.unpack(">I", hdr[:4])[0]
    if hdr[4:8] != b"ftyp":
        return "MP4", "mp4", MediaType.VIDEO
 
    brand_raw = f.read(4)
    if len(brand_raw) < 4:
        return "MP4", "mp4", MediaType.VIDEO
 
    brand = brand_raw.decode("ascii", errors="replace").strip("\x00")
 
    if brand in FTYP_BRANDS:
        return FTYP_BRANDS[brand]
 
    # Check compatible brands in ftyp box
    remaining = box_size - 16  # size(4) + ftyp(4) + brand(4) + version(4)
    if remaining > 0:
        f.seek(4, os.SEEK_CUR)  # skip minor_version
        compat = f.read(min(remaining - 4, 64))
        for i in range(0, len(compat) - 3, 4):
            cb = compat[i:i+4].decode("ascii", errors="replace").strip("\x00")
            if cb in FTYP_BRANDS:
                return FTYP_BRANDS[cb]
 
    return "MP4", "mp4", MediaType.VIDEO
 
 
# ---------------------------------------------------------------------------
# JPEG validation helper
# ---------------------------------------------------------------------------
def validate_jpeg(data: bytes, min_dim: int, skip_resolutions: set) -> Optional[tuple[int, int]]:
    """Validate JPEG data, returning (width, height) or None."""
    if not HAS_PIL:
        return (0, 0)  # Can't validate without PIL, accept everything
 
    try:
        img = PILImage.open(io.BytesIO(data))
        w, h = img.size
        if w < min_dim or h < min_dim:
            return None
        if (w, h) in skip_resolutions:
            return None
        img.verify()
        return (w, h)
    except Exception:
        # Try a lenient check — just get dimensions
        try:
            img = PILImage.open(io.BytesIO(data))
            w, h = img.size
            if w < min_dim or h < min_dim:
                return None
            if (w, h) in skip_resolutions:
                return None
            return (w, h)
        except Exception:
            return None
 
 
# ---------------------------------------------------------------------------
# MPEG-TS detector (special — pattern-based, not magic-based)
# ---------------------------------------------------------------------------
def check_mpeg_ts(data: bytes, pos: int) -> Optional[tuple[int, int]]:
    """Check if position contains an MPEG-TS stream. Returns (packet_size, None) or None."""
    if pos + 192 * 8 > len(data):
        return None
 
    # Try 188-byte packets
    if all(data[pos + i * 188] == 0x47 for i in range(8)):
        return (188, 0)
    # Try 192-byte packets (with timestamp prefix)
    if all(data[pos + i * 192] == 0x47 for i in range(8)):
        return (192, 0)
    return None
 
 
# ---------------------------------------------------------------------------
# Input size detection
# ---------------------------------------------------------------------------
def detect_input_size(path: str) -> int:
    """
    Detect source size for regular files and block devices.

    Tries, in order:
    1) os.path.getsize (fast path)
    2) seek/tell to EOF
    3) Block-device specific fallbacks:
       - macOS: diskutil info -plist <device> (TotalSize)
       - Linux: blockdev --getsize64 <device>
    """
    # Fast path for regular files (and some devices)
    try:
        size = os.path.getsize(path)
        if size > 0:
            return size
    except OSError:
        pass

    # Generic fallback via seek/tell
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size > 0:
                return size
    except OSError:
        pass

    # Device-specific fallbacks
    try:
        mode = os.stat(path).st_mode
    except OSError as e:
        raise OSError(f"Unable to stat input: {path} ({e})") from e

    if stat.S_ISBLK(mode):
        # macOS fallback
        if sys.platform == "darwin":
            try:
                out = subprocess.check_output(
                    ["diskutil", "info", "-plist", path],
                    stderr=subprocess.DEVNULL,
                )
                info = plistlib.loads(out)
                total = int(info.get("TotalSize", 0))
                if total > 0:
                    return total
            except Exception:
                pass

        # Linux fallback
        if sys.platform.startswith("linux"):
            try:
                out = subprocess.check_output(
                    ["blockdev", "--getsize64", path],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
                total = int(out)
                if total > 0:
                    return total
            except Exception:
                pass

    raise OSError(f"Unable to determine input size for: {path}")


def file_sha256(path: Path) -> str:
    """Compute SHA-256 for a file path."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(EXTRACT_BUFFER)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------
@dataclass
class ScanStats:
    new_photos: int = 0
    new_videos: int = 0
    dup_photos: int = 0
    dup_videos: int = 0
    skipped_frames: int = 0
    errors: int = 0
 
 
class MediaCarver:
    """Main scanning engine."""
 
    def __init__(
        self,
        image_path: str,
        output_dir: str,
        state: ScanState,
        min_photo_size: int = MIN_PHOTO_SIZE,
        min_video_size: int = MIN_VIDEO_SIZE,
        min_dimension: int = MIN_DIMENSION,
        skip_resolutions: Optional[set[tuple[int, int]]] = None,
        strict_dedup: bool = True,
        skip_jpeg_after_video: bool = True,
    ):
        self.image_path = image_path
        self.image_size = detect_input_size(image_path)
        self.photo_dir = Path(output_dir) / "photos"
        self.video_dir = Path(output_dir) / "videos"
        self.video_frame_dir = Path(output_dir) / "frames"
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.video_frame_dir.mkdir(parents=True, exist_ok=True)
 
        self.state = state
        self.min_photo_size = min_photo_size
        self.min_video_size = min_video_size
        self.min_dimension = min_dimension
        self.skip_resolutions = skip_resolutions or set()
        self.strict_dedup = strict_dedup
        self.skip_jpeg_after_video = skip_jpeg_after_video
        self.video_found = False
 
        # Build quick-lookup: first byte -> list of signatures
        self._sig_by_first_byte: dict[int, list[FormatSignature]] = {}
        for sig in ALL_SIGNATURES:
            if sig.magic_offset == 0:
                fb = sig.magic[0]
                self._sig_by_first_byte.setdefault(fb, []).append(sig)
 
        # ftyp sigs are at offset 4 — we'll detect them separately
        self._ftyp_sigs = [s for s in ALL_SIGNATURES if s.magic_offset == 4]
 
    # ── extraction ────────────────────────────────────────────────────
    def _extract_file(self, f: BinaryIO, start: int, size: int, dest: str):
        """Stream-copy bytes from image to destination file."""
        f.seek(start)
        with open(dest, "wb") as out:
            remaining = size
            while remaining > 0:
                chunk = f.read(min(remaining, EXTRACT_BUFFER))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
 
    # ── main scan ─────────────────────────────────────────────────────
    def scan_range(self, start_byte: int, end_byte: int) -> ScanStats:
        end_byte = min(end_byte, self.image_size)
        stats = ScanStats()
        skip_until = start_byte
 
        hash_label = "known sha256" if self.strict_dedup else "known hashes"
        hash_value = self.state.sha256_count if self.strict_dedup else self.state.hash_count
        self.state.log(
            f"=== Scan {start_byte/1e6:.0f}–{end_byte/1e6:.0f} MB "
            f"({self.image_size/1e6:.0f} MB total, "
            f"{hash_value} {hash_label}) ==="
        )
 
        with open(self.image_path, "rb") as f:
            scan_pos = start_byte
 
            while scan_pos < end_byte:
                # Progress
                pct = (scan_pos - start_byte) * 100 // max(1, end_byte - start_byte)
                if (scan_pos - start_byte) % (100 * 1024 * 1024) < SCAN_BUFFER:
                    self.state.log(
                        f"  {pct}% @ {scan_pos/1e6:.0f}MB | "
                        f"+{stats.new_photos}p +{stats.new_videos}v "
                        f"dup={stats.dup_photos + stats.dup_videos} "
                        f"skip={stats.skipped_frames}"
                    )
 
                f.seek(scan_pos)
                data = f.read(SCAN_BUFFER)
                if not data:
                    break
 
                # Scan for all signatures in this buffer
                idx = 0
                scan_limit = len(data) if len(data) <= OVERLAP_BYTES else len(data) - OVERLAP_BYTES
                while idx < scan_limit:
                    abs_off = scan_pos + idx
                    if abs_off < skip_until:
                        idx += 1
                        continue
 
                    found = False
 
                    # ── Check ftyp at offset+4 (ISOBMFF) ─────────
                    if idx + 12 <= len(data) and data[idx+4:idx+8] == b"ftyp":
                        # Validate box size
                        box_size = struct.unpack(">I", data[idx:idx+4])[0]
                        if 8 < box_size < 200:
                            fmt_name, ext, media_type = detect_ftyp_brand(f, abs_off)
                            end = _walk_isobmff(f, abs_off,
                                               MAX_VIDEO_SIZE if media_type == MediaType.VIDEO
                                               else MAX_PHOTO_SIZE)
                            if end:
                                found = self._handle_found(
                                    f, abs_off, end, fmt_name, ext, media_type, stats
                                )
                                if found:
                                    skip_until = end
                                    idx = end - scan_pos
                                    continue
 
                    # ── Check MPEG-TS (sync byte pattern) ─────────
                    if data[idx] == 0x47:
                        ts_result = check_mpeg_ts(data, idx)
                        if ts_result:
                            pkt_size, _ = ts_result
                            # Find end of TS stream
                            ts_end = self._find_ts_end(f, abs_off, pkt_size)
                            if ts_end and ts_end - abs_off > self.min_video_size:
                                found = self._handle_found(
                                    f, abs_off, ts_end, "MPEG-TS", "mts",
                                    MediaType.VIDEO, stats
                                )
                                if found:
                                    skip_until = ts_end
                                    idx = ts_end - scan_pos
                                    continue
 
                    # ── Check magic-at-offset-0 signatures ────────
                    first_byte = data[idx]
                    if first_byte in self._sig_by_first_byte:
                        for sig in self._sig_by_first_byte[first_byte]:
                            magic_len = len(sig.magic)
                            if idx + magic_len > len(data):
                                continue
                            if data[idx:idx+magic_len] != sig.magic:
                                continue
 
                            # Secondary magic check
                            if sig.magic2 is not None and sig.magic2_offset is not None:
                                m2_start = idx + sig.magic2_offset
                                m2_end = m2_start + len(sig.magic2)
                                if m2_end > len(data) or data[m2_start:m2_end] != sig.magic2:
                                    continue
 
                            # JPEG: validate the marker byte after FFD8FF
                            if sig.name == "JPEG":
                                marker = data[idx + 3] if idx + 3 < len(data) else 0
                                if marker not in VALID_JPEG_MARKS:
                                    continue
 
                            # Find end
                            finder = END_FINDERS.get(sig.end_strategy)
                            if not finder:
                                continue
 
                            end = finder(f, abs_off, sig.max_size)
                            if not end:
                                continue
 
                            file_size = end - abs_off
                            min_sz = (self.min_photo_size if sig.media_type == MediaType.PHOTO
                                      else self.min_video_size)
                            if file_size < min_sz:
                                continue
 
                            # Format refinement for TIFF
                            fmt_name = sig.name
                            ext = sig.extension
                            media_type = sig.media_type
 
                            if sig.name in ("TIFF-LE", "TIFF-BE"):
                                fmt_name, ext = detect_tiff_subformat(f, abs_off)
                                # RAW files are photos
                                media_type = MediaType.PHOTO
 
                            found = self._handle_found(
                                f, abs_off, end, fmt_name, ext, media_type, stats
                            )
                            if found:
                                skip_until = end
                                idx = end - scan_pos
                                break
 
                    if not found:
                        idx += 1
 
                advance = len(data) - OVERLAP_BYTES
                if advance <= 0:
                    # Tail chunk shorter than overlap: processed once, then stop.
                    break
                scan_pos += advance
 
        self.state.log(
            f"=== Chunk done: +{stats.new_photos}p +{stats.new_videos}v "
            f"| dups: {stats.dup_photos}p {stats.dup_videos}v "
            f"| skipped: {stats.skipped_frames} | errors: {stats.errors} ===\n"
        )
 
        return stats
 
    def _handle_found(
        self,
        f: BinaryIO,
        start: int,
        end: int,
        fmt_name: str,
        ext: str,
        media_type: MediaType,
        stats: ScanStats,
    ) -> bool:
        """Process a found file: validate, dedup, extract. Returns True if saved."""
        file_size = end - start
        if file_size <= 0:
            return False
 
        # Clamp to image boundary
        actual_end = min(end, self.image_size)
        actual_size = actual_end - start
 
        # Fast sample fingerprint dedup (non-strict mode only)
        f.seek(start)
        sample = f.read(min(actual_size, HASH_SAMPLE_BYTES))
        fp = self.state.fingerprint(sample)
 
        if not self.strict_dedup and self.state.is_seen(fp):
            if media_type == MediaType.PHOTO:
                stats.dup_photos += 1
            else:
                stats.dup_videos += 1
                self.video_found = True
            return True  # Still "handled" — skip past it
 
        # JPEG-specific validation
        if fmt_name == "JPEG":
            if self.skip_jpeg_after_video and self.video_found:
                stats.skipped_frames += 1
                return True
            f.seek(start)
            jpeg_data = f.read(actual_size)
            dims = validate_jpeg(jpeg_data, self.min_dimension, self.skip_resolutions)
            if dims is None:
                stats.skipped_frames += 1
                return True  # Skip but don't save
            if dims == (0, 0):
                # PIL not available, accept anyway
                dims = None
            w, h = dims if dims else (0, 0)
            dim_str = f"_{w}x{h}" if w > 0 else ""
        else:
            dim_str = ""
 
        # Generate output path
        file_id = self.state.next_id(media_type)
        frame_mode = (
            fmt_name == "JPEG"
            and media_type == MediaType.PHOTO
            and self.video_found
            and not self.skip_jpeg_after_video
        )
        out_dir = self.photo_dir if media_type == MediaType.PHOTO else self.video_dir
        if frame_mode:
            out_dir = self.video_frame_dir
        size_label = f"_{actual_size // 1024}KB" if actual_size < 10 * 1024 * 1024 else f"_{actual_size // (1024*1024)}MB"
        file_prefix = "video_frame" if frame_mode else media_type.value
        filename = f"{file_prefix}_{file_id:05d}_{fmt_name}{dim_str}{size_label}.{ext}"
        out_path = out_dir / filename
 
        # Extract
        try:
            if fmt_name == "JPEG" and 'jpeg_data' in dir():
                # Already read into memory
                with open(out_path, "wb") as out:
                    out.write(jpeg_data)
            else:
                self._extract_file(f, start, actual_size, str(out_path))
        except Exception as e:
            stats.errors += 1
            self.state.log(f"    ERROR extracting {fmt_name} @ {start/1e6:.1f}MB: {e}")
            return False
 
        if self.strict_dedup:
            try:
                full_digest = file_sha256(out_path)
            except Exception as e:
                stats.errors += 1
                out_path.unlink(missing_ok=True)
                self.state.log(f"    ERROR hashing {fmt_name} @ {start/1e6:.1f}MB: {e}")
                return False

            if self.state.is_sha256_seen(full_digest):
                out_path.unlink(missing_ok=True)
                if media_type == MediaType.PHOTO:
                    stats.dup_photos += 1
                else:
                    stats.dup_videos += 1
                    self.video_found = True
                return True

            self.state.record_sha256(full_digest)
        else:
            self.state.record(fp)
 
        if media_type == MediaType.PHOTO:
            stats.new_photos += 1
        else:
            stats.new_videos += 1
            self.video_found = True
 
        self.state.log(
            f"    {fmt_name} #{file_id}: {actual_size/1024:.0f}KB "
            f"@ {start/1e6:.1f}MB -> {filename}"
        )
 
        return True
 
    def _find_ts_end(self, f: BinaryIO, start: int, pkt_size: int) -> Optional[int]:
        """Find the end of an MPEG-TS stream by scanning for loss of sync."""
        f.seek(start)
        pos = 0
        max_search = min(MAX_VIDEO_SIZE, self.image_size - start)
        buf_size = 1024 * pkt_size  # ~188KB at a time
 
        while pos < max_search:
            f.seek(start + pos)
            buf = f.read(buf_size)
            if not buf:
                break
 
            for i in range(0, len(buf) - pkt_size, pkt_size):
                if buf[i] != 0x47:
                    end = start + pos + i
                    return end if end - start > self.min_video_size else None
            pos += len(buf)
 
        return start + pos if pos > self.min_video_size else None
 
    # ── convenience: full image scan ──────────────────────────────────
    def scan_full(self, chunk_mb: int = DEFAULT_CHUNK_MB) -> ScanStats:
        """Scan the entire image in chunks."""
        total = ScanStats()
        chunk_bytes = chunk_mb * 1024 * 1024
        overlap = 2 * 1024 * 1024  # 2 MB overlap between chunks
        n_chunks = max(1, (self.image_size + chunk_bytes - 1) // chunk_bytes)
 
        self.state.log(
            f"=== Full scan: {self.image_size/1e6:.0f} MB in "
            f"{n_chunks} chunks of {chunk_mb} MB ==="
        )
 
        for i in range(n_chunks):
            start = max(0, i * chunk_bytes - (overlap if i > 0 else 0))
            end = min((i + 1) * chunk_bytes, self.image_size)
 
            self.state.log(f"--- Chunk {i+1}/{n_chunks} ---")
            chunk_stats = self.scan_range(start, end)
 
            total.new_photos    += chunk_stats.new_photos
            total.new_videos    += chunk_stats.new_videos
            total.dup_photos    += chunk_stats.dup_photos
            total.dup_videos    += chunk_stats.dup_videos
            total.skipped_frames += chunk_stats.skipped_frames
            total.errors        += chunk_stats.errors
 
        self.state.log(
            f"=== FULL SCAN COMPLETE: "
            f"{total.new_photos} photos, {total.new_videos} videos "
            f"({total.dup_photos + total.dup_videos} dups, "
            f"{total.skipped_frames} skipped, {total.errors} errors) ===\n"
        )
 
        return total
 
 
# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------
def generate_report(
    output_dir: str,
    state: ScanState,
    started_at: Optional[float] = None,
    finished_at: Optional[float] = None,
    strict_dedup: bool = True,
):
    """Print a summary of all recovered files."""
    photo_dir = Path(output_dir) / "photos"
    video_dir = Path(output_dir) / "videos"
 
    print("\n" + "=" * 64)
    print("  RECOVERY REPORT")
    print("=" * 64)
 
    for label, d, media in [("PHOTOS", photo_dir, "photo"), ("VIDEOS", video_dir, "video")]:
        if not d.exists():
            continue
        files = sorted(d.iterdir())
        if not files:
            print(f"\n  {label}: none found")
            continue
 
        total_bytes = sum(f.stat().st_size for f in files)
        by_ext: dict[str, int] = {}
        for f in files:
            ext = f.suffix.lstrip(".")
            by_ext[ext] = by_ext.get(ext, 0) + 1
 
        print(f"\n  {label}: {len(files)} files ({total_bytes / (1024*1024):.1f} MB)")
        for ext, count in sorted(by_ext.items(), key=lambda x: -x[1]):
            print(f"    .{ext}: {count}")
 
    if strict_dedup:
        print(f"\n  Unique SHA-256: {state.sha256_count}")
    else:
        print(f"\n  Unique hashes: {state.hash_count}")
    if started_at is not None and finished_at is not None:
        elapsed = max(0.0, finished_at - started_at)
        start_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at))
        end_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished_at))
        print(f"  Started at: {start_str}")
        print(f"  Finished at: {end_str}")
        print(f"  Elapsed: {elapsed:.2f}s")
    print("=" * 64)
 
 
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    run_started_at = time.time()
    parser = argparse.ArgumentParser(
        prog="media_carver",
        description="Recover photos and videos from raw disk images or devices.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else "",
    )
    parser.add_argument("image", help="Path to disk image or block device")
    parser.add_argument("-o", "--output", required=True,
                        help="Output directory for recovered files")
    parser.add_argument("--start", type=float, default=None,
                        help="Start offset in MB (for manual chunking)")
    parser.add_argument("--end", type=float, default=None,
                        help="End offset in MB (for manual chunking)")
    parser.add_argument("--chunk-mb", type=int, default=DEFAULT_CHUNK_MB,
                        help=f"Chunk size in MB for auto mode (default: {DEFAULT_CHUNK_MB})")
    parser.add_argument("--min-size", type=int, default=MIN_PHOTO_SIZE,
                        help=f"Minimum file size in bytes (default: {MIN_PHOTO_SIZE})")
    parser.add_argument("--min-dim", type=int, default=MIN_DIMENSION,
                        help=f"Minimum image dimension in pixels (default: {MIN_DIMENSION})")
    parser.add_argument("--skip-video-frame-res", type=str, default=None,
                        help="Skip JPEG frames at this resolution (e.g., 1280x720)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset scan state and start fresh")
    parser.add_argument("--report", "--report-only", dest="report_only", action="store_true",
                        help="Print a report of existing recovered files without scanning")
    parser.add_argument("--fast-dedup", action="store_false", dest="strict_dedup",
                        help="Use sampled-hash dedup instead of full SHA-256")
    parser.add_argument("--keep-jpeg-after-video", action="store_false", dest="skip_jpeg_after_video",
                        help="Keep extracting JPEGs even after first recovered video")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
 
    args = parser.parse_args()
 
    # Logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )
 
    # Validate scalar args early
    if args.chunk_mb <= 0:
        parser.error("--chunk-mb must be > 0")
    if args.min_size <= 0:
        parser.error("--min-size must be > 0")
    if args.min_dim <= 0:
        parser.error("--min-dim must be > 0")
    if args.start is not None and args.start < 0:
        parser.error("--start must be >= 0")
    if args.end is not None and args.end <= 0:
        parser.error("--end must be > 0")
    if args.start is not None and args.end is not None and args.end <= args.start:
        parser.error("--end must be greater than --start")

    # Validate input unless report mode
    if not args.report_only and not os.path.exists(args.image):
        parser.error(f"Image not found: {args.image}")
 
    # State
    state_dir = Path(args.output) / ".scan_state"
    state = ScanState(state_dir)
 
    if args.reset:
        state.reset()
        logging.info("Scan state reset.")
 
    if args.report_only:
        generate_report(
            args.output,
            state,
            run_started_at,
            time.time(),
            strict_dedup=args.strict_dedup,
        )
        return
 
    # Skip resolutions
    skip_res: set[tuple[int, int]] = set()
    if args.skip_video_frame_res:
        try:
            w, h = args.skip_video_frame_res.split("x")
            skip_res.add((int(w), int(h)))
        except ValueError:
            parser.error("--skip-video-frame-res must be WxH (e.g., 1280x720)")
 
    # Create carver
    carver = MediaCarver(
        image_path=args.image,
        output_dir=args.output,
        state=state,
        min_photo_size=args.min_size,
        min_video_size=max(args.min_size, MIN_VIDEO_SIZE),
        min_dimension=args.min_dim,
        skip_resolutions=skip_res,
        strict_dedup=args.strict_dedup,
        skip_jpeg_after_video=args.skip_jpeg_after_video,
    )
 
    # Run
    if args.start is not None and args.end is not None:
        start_byte = int(args.start * 1024 * 1024)
        end_byte = int(args.end * 1024 * 1024)
        stats = carver.scan_range(start_byte, end_byte)
    elif args.start is not None or args.end is not None:
        parser.error("Both --start and --end must be specified for range mode")
    else:
        stats = carver.scan_full(chunk_mb=args.chunk_mb)
 
    # Report
    generate_report(
        args.output,
        state,
        run_started_at,
        time.time(),
        strict_dedup=args.strict_dedup,
    )
 
    # Exit code
    if stats.errors > 0:
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()
