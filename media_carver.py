#!/usr/bin/env python3
"""
media_carver.py — Production-ready media file carver for raw disk images and devices.
 
Recovers photos and videos from raw disk images, SD cards, USB drives, or any
block device by scanning for known file signatures (file carving). Handles
fragmented scans with persistent deduplication state so large images can be
processed in chunks without duplicating output.

Default profile prefers **aggressive recovery** (maximize extracted candidates):
post-video frame routing and burst clustering are off unless you opt in; 720p /
1080p JPEGs after a recovered video still go to frames/ when dimensions match.
 
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
 
  # Tune likely video-frame JPEG resolutions (defaults: 720p + 1080p):
  python3 media_carver.py image.img -o /out --skip-video-frame-res 1280x720,1920x1080
 
  # Custom min file size:
  python3 media_carver.py image.img -o /out --min-size 50000
 
  # Reset state (re-scan from scratch):
  python3 media_carver.py image.img -o /out --reset

  # Stricter photo vs frame separation (optional):
  python3 media_carver.py image.img -o /out --skip-jpeg-after-video --burst-frame-clustering
"""
 
from __future__ import annotations
 
import argparse
import contextlib
import hashlib
import io
from collections import deque
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
    from PIL import ImageFile as PILImageFile
    PILImageFile.LOAD_TRUNCATED_IMAGES = False
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Optional Pillow HEIF/HEIC plugin (registers decoders with Pillow if present)
try:
    import pillow_heif  # type: ignore  # noqa: F401
    HAS_PILLOW_HEIF = True
except ImportError:
    HAS_PILLOW_HEIF = False

try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import av  # type: ignore
    HAS_PYAV = True
except ImportError:
    HAS_PYAV = False

try:
    from pymediainfo import MediaInfo  # type: ignore
    HAS_MEDIAINFO = True
except ImportError:
    HAS_MEDIAINFO = False

try:
    import imagecodecs  # type: ignore
    HAS_IMAGECODECS = True
except ImportError:
    HAS_IMAGECODECS = False

try:
    import rawpy  # type: ignore
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False


def log_optional_library_status():
    """Log optional-library availability and actionable install hints."""
    optional_libs = [
        (
            "pillow",
            HAS_PIL,
            "Better JPEG and common image validation",
            "python -m pip install pillow",
        ),
        (
            "pillow-heif",
            HAS_PILLOW_HEIF,
            "HEIF/HEIC support via Pillow plugin",
            "python -m pip install pillow-heif",
        ),
        (
            "opencv-python",
            HAS_CV2,
            "Additional image decode validation (PNG/JPEG/WebP/TIFF/BMP)",
            "python -m pip install opencv-python",
        ),
        (
            "av (PyAV)",
            HAS_PYAV,
            "Video stream/container probing",
            "python -m pip install av",
        ),
        (
            "pymediainfo",
            HAS_MEDIAINFO,
            "Media metadata/track probing",
            "python -m pip install pymediainfo",
        ),
        (
            "imagecodecs",
            HAS_IMAGECODECS,
            "Extra codec validation for image formats",
            "python -m pip install imagecodecs",
        ),
        (
            "rawpy",
            HAS_RAWPY,
            "RAW photo validation (CR2/NEF/ARW/DNG/etc.)",
            "python -m pip install rawpy",
        ),
    ]

    available = [name for (name, ok, _, _) in optional_libs if ok]
    logging.info(
        "Optional validator libraries available: %s",
        ", ".join(available) if available else "none",
    )
    for name, ok, benefit, install_cmd in optional_libs:
        if not ok:
            logging.warning(
                "Optional library '%s' not found. Benefit: %s. Install: %s",
                name,
                benefit,
                install_cmd,
            )


@contextlib.contextmanager
def suppress_native_stderr():
    """
    Suppress noisy native-library stderr output during best-effort validation.

    Some decoders (libjpeg/OpenCV bindings) print directly to process stderr
    for malformed files. This keeps console output focused on scan progress.
    """
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        # Fallback: no-op if stderr fd is unavailable.
        yield
        return

    saved_fd = os.dup(stderr_fd)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
            yield
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(saved_fd)
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
RECOVERY_MANIFEST_VERSION = 2
 
SCAN_BUFFER       = 32 * 1024 * 1024   # 32 MB read buffer per pass
EXTRACT_BUFFER    = 4 * 1024 * 1024    # 4 MB streaming write buffer
HASH_SAMPLE_BYTES = 64 * 1024          # First 64 KB for fingerprint
OVERLAP_BYTES     = 64                  # Overlap between scan buffers
DEFAULT_CHUNK_MB  = 768                 # Default chunk size for auto mode
 
# Valid JPEG marker bytes after FFD8FF
VALID_JPEG_MARKS  = {0xe0, 0xe1, 0xe2, 0xe3, 0xdb, 0xc0, 0xc2, 0xc4, 0xee, 0xed, 0xfe}
 
MAX_PHOTO_SIZE    = 80 * 1024 * 1024   # 80 MB ceiling per photo

# MJPEG-in-AVI header scan limit (avoid walking multi-GB movi payloads)
AVI_MJPEG_HEADER_SCAN_BYTES = 262144

# Burst JPEG clustering: many same-resolution JPEGs packed tightly often indicate frames.
JPEG_BURST_WINDOW_BYTES = 3 * 1024 * 1024
JPEG_BURST_MIN_FRAMES = 3
JPEG_BURST_MAX_STEP_GAP_BYTES = 1024 * 1024

# Known MJPEG / motion-JPEG fourCCs in AVI strh.fccHandler (case-insensitive)
AVI_MJPEG_HANDLERS = frozenset({
    b"mjpg", b"jpeg", b"ijpg", b"avi1", b"dmb1", b"jfif", b"acdv", b"qpeg", b"slmj",
})
MAX_VIDEO_SIZE    = 8 * 1024 * 1024 * 1024  # 8 GB ceiling per video
MIN_PHOTO_SIZE    = 4 * 1024           # 4 KB floor for photos
MIN_VIDEO_SIZE    = 50 * 1024          # 50 KB floor for videos
MIN_DIMENSION     = 16                 # Default minimum JPEG dimension (aggressive recovery)
# Default: HD / FHD video frame sizes (not still-camera megapixel sizes).
DEFAULT_SKIP_VIDEO_FRAME_RES = "1280x720,1920x1080"

# Typical compact-camera / phone still JPEG dimensions by megapixel class (~12–1 MP).
# Used only to suppress burst clustering near video (reduces false "frame" labels);
# does not override MJPEG-in-AVI span detection or an explicit WxH in
# --skip-video-frame-res.
COMMON_STILL_PHOTO_RESOLUTIONS: frozenset[tuple[int, int]] = frozenset({
    # ~12 MP
    (4032, 3024),
    (3024, 4032),
    (4032, 2880),
    (2880, 4032),
    (4000, 3000),
    (3000, 4000),
    (4608, 3456),
    (3456, 4608),
    # ~8 MP
    (3264, 2448),
    (2448, 3264),
    (3456, 2304),
    (2304, 3456),
    # ~5 MP
    (2592, 1944),
    (1944, 2592),
    (2560, 1920),
    (1920, 2560),
    # ~3 MP
    (2048, 1536),
    (1536, 2048),
    # ~1 MP (exclude 1280x720 — that is default video frame size)
    (1280, 960),
    (960, 1280),
    (1024, 768),
    (768, 1024),
})
 
 
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
        self._manifest_path = state_dir / "recovery_manifest.jsonl"
 
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
        for p in (
            self._hash_path,
            self._sha256_path,
            self._counter_path,
            self._log_path,
            self._manifest_path,
        ):
            p.unlink(missing_ok=True)

    def append_manifest_record(self, record: dict):
        """Append one JSON object line for downstream media_classifier.py."""
        with open(self._manifest_path, "a", encoding="utf-8") as mf:
            mf.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
 
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
 
 
def _find_next_jpeg_eoi(f: BinaryIO, search_from: int, search_to: int) -> Optional[int]:
    """Find next JPEG EOI marker between absolute offsets [search_from, search_to)."""
    if search_to <= search_from:
        return None
    f.seek(search_from)
    buf = b""
    read = 0
    span = search_to - search_from
    while read < span:
        chunk = f.read(min(256 * 1024, span - read))
        if not chunk:
            break
        buf += chunk
        read += len(chunk)
        idx = buf.find(b"\xff\xd9", max(0, len(buf) - len(chunk) - 1))
        if idx != -1:
            return search_from + idx + 2
        buf = buf[-1:]
    return None


def _find_png_iend(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk PNG chunks with IHDR semantic checks and stop at IEND."""
    f.seek(start + 8)  # skip signature
    pos = 8
    saw_ihdr = False
    saw_idat = False

    def _valid_ihdr(ihdr: bytes) -> bool:
        if len(ihdr) != 13:
            return False
        width = struct.unpack(">I", ihdr[0:4])[0]
        height = struct.unpack(">I", ihdr[4:8])[0]
        bit_depth = ihdr[8]
        color_type = ihdr[9]
        compression = ihdr[10]
        filter_method = ihdr[11]
        interlace = ihdr[12]

        if width == 0 or height == 0:
            return False
        if color_type == 0 and bit_depth not in (1, 2, 4, 8, 16):
            return False
        if color_type == 3 and bit_depth not in (1, 2, 4, 8):
            return False
        if color_type in (2, 4, 6) and bit_depth not in (8, 16):
            return False
        if color_type not in (0, 2, 3, 4, 6):
            return False
        if compression != 0 or filter_method != 0:
            return False
        if interlace not in (0, 1):
            return False
        return True

    while pos < max_size:
        hdr = f.read(8)
        if len(hdr) < 8:
            return None
        length = struct.unpack(">I", hdr[:4])[0]
        chunk_type = hdr[4:8]

        if any(not (65 <= b <= 90 or 97 <= b <= 122) for b in chunk_type):
            return None

        if length > max_size - pos - 12:
            return None
        data = f.read(length)
        crc = f.read(4)
        if len(data) != length or len(crc) != 4:
            return None
        pos += 12 + length

        if chunk_type == b"IHDR":
            if saw_ihdr or pos != 8 + 12 + length:
                return None
            if length != 13 or not _valid_ihdr(data):
                return None
            saw_ihdr = True
        elif chunk_type == b"IDAT":
            if not saw_ihdr:
                return None
            saw_idat = True
        elif chunk_type == b"IEND":
            if not saw_ihdr:
                return None
            return start + pos
        elif not saw_ihdr and chunk_type != b"IHDR":
            return None

    return None
 
 
def _find_gif_trailer(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk GIF structure and stop at trailer (0x3B)."""
    f.seek(start)
    data = f.read(min(max_size, 32 * 1024 * 1024))
    if len(data) < 13:
        return None
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None

    pos = 6  # header
    # Logical Screen Descriptor
    packed = data[pos + 4]
    pos += 7
    # Global Color Table
    if packed & 0x80:
        gct_size = 3 * (2 ** ((packed & 0x07) + 1))
        pos += gct_size
    if pos >= len(data):
        return None

    while pos < len(data):
        b = data[pos]
        if b == 0x3B:  # Trailer
            return start + pos + 1
        elif b == 0x21:  # Extension
            pos += 1
            if pos >= len(data):
                return None
            _label = data[pos]
            pos += 1
            # Data sub-block chain
            while pos < len(data):
                block_len = data[pos]
                pos += 1
                if block_len == 0:
                    break
                pos += block_len
            else:
                return None
        elif b == 0x2C:  # Image Descriptor
            if pos + 10 > len(data):
                return None
            packed_img = data[pos + 9]
            pos += 10
            # Local Color Table
            if packed_img & 0x80:
                lct_size = 3 * (2 ** ((packed_img & 0x07) + 1))
                pos += lct_size
            if pos >= len(data):
                return None
            # LZW minimum code size
            pos += 1
            # Image data sub-block chain
            while pos < len(data):
                block_len = data[pos]
                pos += 1
                if block_len == 0:
                    break
                pos += block_len
            else:
                return None
        else:
            return None

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


def _avi_chunks_scan_for_mjpeg_handler(
    f: BinaryIO, pos: int, scan_limit: int, file_end: int,
) -> bool:
    """
    Walk AVI LIST/chunk structure between absolute offsets [pos, scan_limit)
    looking for strh with vids + MJPEG-style handler. Does not descend into
    LIST 'movi' (payload skipped).
    """
    scan_limit = min(scan_limit, file_end)
    while pos + 8 <= scan_limit:
        f.seek(pos)
        tag = f.read(4)
        sz_b = f.read(4)
        if len(tag) < 4 or len(sz_b) < 4:
            return False
        chunk_sz = struct.unpack("<I", sz_b)[0]
        if chunk_sz > scan_limit - pos - 8 or chunk_sz > file_end - pos - 8:
            return False
        chunk_abs_end = pos + 8 + chunk_sz
        pad = chunk_sz % 2
        next_pos = chunk_abs_end + pad
        if next_pos > file_end or chunk_abs_end > file_end:
            return False
        if tag == b"LIST":
            if pos + 12 > chunk_abs_end:
                return False
            list_type = f.read(4)
            inner_start = pos + 12
            inner_end = min(chunk_abs_end, file_end)
            child_limit = min(inner_end, scan_limit)
            if list_type == b"movi":
                pass
            elif inner_start < child_limit:
                if _avi_chunks_scan_for_mjpeg_handler(f, inner_start, child_limit, file_end):
                    return True
        elif tag == b"strh" and chunk_sz >= 8:
            body = f.read(min(chunk_sz, 64))
            if len(body) >= 8:
                fcc_type = body[0:4]
                fcc_handler = body[4:8]
                if fcc_type == b"vids" and fcc_handler.lower() in AVI_MJPEG_HANDLERS:
                    return True
        pos = next_pos
    return False


def avi_file_contains_mjpeg_video_stream(f: BinaryIO, avi_start: int, avi_abs_end: int) -> bool:
    """
    Return True if an AVI (RIFF ... AVI ) declares an MJPEG-compressed video stream
    in the header (hdrl/strl/strh). Used to classify loose JPEGs inside the file
    span as likely video frames.
    """
    if avi_abs_end - avi_start < 32:
        return False
    f.seek(avi_start)
    hdr = f.read(12)
    if len(hdr) < 12 or hdr[0:4] != b"RIFF" or hdr[8:12] != b"AVI ":
        return False
    header_lim = min(avi_start + AVI_MJPEG_HEADER_SCAN_BYTES, avi_abs_end)
    return _avi_chunks_scan_for_mjpeg_handler(f, avi_start + 12, header_lim, avi_abs_end)
 
 
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
    known_boxes = {
        b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"uuid", b"meta",
        b"trak", b"mdia", b"minf", b"stbl", b"mvhd", b"tkhd", b"mdhd", b"hdlr",
        b"stsd", b"stts", b"stsc", b"stsz", b"stco", b"co64", b"udta", b"edts",
        b"dinf", b"vmhd", b"smhd", b"nmhd", b"elst", b"cmov", b"cmvd", b"dcom",
        b"jp2h", b"pnot", b"pict",
    }
    f.seek(start)
    pos = 0
    n_boxes = 0
    saw_ftyp = False
    saw_media_or_structure = False

    while pos < max_size:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        size = struct.unpack(">I", hdr[:4])[0]
        box_type = hdr[4:8]

        if box_type == b"ftyp":
            saw_ftyp = True
 
        if size == 1:
            # 64-bit extended size
            ext = f.read(8)
            if len(ext) < 8:
                break
            size = struct.unpack(">Q", ext)[0]
            header_size = 16
        elif size == 0:
            # Box extends to end of file — use remaining max_size
            return start + max_size
        else:
            header_size = 8
 
        if size < header_size:
            break
        if size > max_size - pos:
            break
        # Treat mostly-nonprintable box names as invalid.
        if any(b < 0x20 or b > 0x7E for b in box_type):
            break
 
        if box_type in known_boxes or box_type.startswith(b"\xa9"):
            saw_media_or_structure = True
        elif n_boxes > 0:
            # Unknown box after start is tolerated once we already have structure;
            # otherwise reject early to avoid many false positives.
            if not saw_media_or_structure:
                break
 
        pos += size
        n_boxes += 1
        f.seek(start + pos)

        # Require container structure: ftyp plus at least one more meaningful box.
        if saw_ftyp and saw_media_or_structure and n_boxes >= 2:
            if box_type == b"mdat":
                return start + pos
 
    if saw_ftyp and saw_media_or_structure and pos > 100:
        return start + pos
    return None
 
 
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
    pos = 4 + ebml_vint_len + ebml_size

    # Search for Segment element (0x18538067). It may not be immediately after
    # the EBML header (e.g., Void elements can appear before it).
    search_limit = min(max_size, 8 * 1024 * 1024)  # keep search bounded
    seg_found = False
    while pos + 8 <= search_limit:
        f.seek(start + pos)
        head = f.read(4)
        if len(head) < 4:
            break
        if head == b"\x18\x53\x80\x67":
            seg_found = True
            break

        # Skip current EBML element (ID + size + payload)
        f.seek(start + pos)
        id_vint = _read_vint(f)
        if not id_vint:
            break
        _id_val, id_len = id_vint
        size_vint = _read_vint(f)
        if not size_vint:
            break
        elem_size, elem_vint_len = size_vint
        unknown_elem_marker = (1 << (7 * elem_vint_len)) - 1
        if elem_size == unknown_elem_marker:
            # Unknown-size element before Segment prevents safe skipping.
            break

        advance = id_len + elem_vint_len + elem_size
        if advance <= 0:
            break
        pos += advance

    if not seg_found:
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
    """Parse ASF object headers using GUID + object-size validation."""
    # ASF Header Object GUID
    asf_header_guid = (
        b"\x30\x26\xb2\x75\x8e\x66\xcf\x11"
        b"\xa6\xd9\x00\xaa\x00\x62\xce\x6c"
    )
    # ASF Data Object GUID
    asf_data_guid = (
        b"\x36\x26\xb2\x75\x8e\x66\xcf\x11"
        b"\xa6\xd9\x00\xaa\x00\x62\xce\x6c"
    )

    f.seek(start)
    header_guid = f.read(16)
    if header_guid != asf_header_guid:
        return None

    header_size_raw = f.read(8)
    if len(header_size_raw) < 8:
        return None
    header_size = struct.unpack("<Q", header_size_raw)[0]
    if header_size < 30 or header_size > max_size:
        return None

    # Header Object includes:
    # - Number of Header Objects (4 bytes)
    # - Reserved1 (1 byte, should be 1)
    # - Reserved2 (1 byte, should be 2)
    hdr_meta = f.read(6)
    if len(hdr_meta) < 6:
        return None
    n_header_objects = struct.unpack("<I", hdr_meta[:4])[0]
    reserved1 = hdr_meta[4]
    reserved2 = hdr_meta[5]
    if n_header_objects < 1 or reserved1 != 1 or reserved2 != 2:
        return None

    # Validate object walk within header bounds.
    pos = 30  # bytes consumed from ASF start
    obj_count = 0
    while pos + 24 <= header_size and obj_count < n_header_objects:
        f.seek(start + pos)
        obj_guid = f.read(16)
        obj_size_raw = f.read(8)
        if len(obj_guid) < 16 or len(obj_size_raw) < 8:
            return None
        obj_size = struct.unpack("<Q", obj_size_raw)[0]
        if obj_size < 24 or obj_size > max_size:
            return None
        pos += obj_size
        obj_count += 1
        if pos > header_size:
            return None

    if pos != header_size:
        return None

    # Data Object should follow header object.
    f.seek(start + header_size)
    data_guid = f.read(16)
    if data_guid != asf_data_guid:
        return None
    data_size_raw = f.read(8)
    if len(data_size_raw) < 8:
        return None
    data_size = struct.unpack("<Q", data_size_raw)[0]
    if data_size < 50:
        return None

    total = header_size + data_size
    if total <= 1000 or total > max_size:
        return None
    return start + total
 
 
def _find_mpeg_ps_end(f: BinaryIO, start: int, max_size: int) -> Optional[int]:
    """Walk MPEG Program Stream packets to estimate valid stream boundary."""
    f.seek(start)
    data = f.read(min(max_size, 500 * 1024 * 1024))  # keep bounded for speed
    if len(data) < 16:
        return None

    def _packet_size(buf: bytes, i: int) -> int:
        if i + 14 > len(buf):
            return 0
        if not (buf[i] == 0x00 and buf[i + 1] == 0x00 and buf[i + 2] == 0x01):
            return 0
        code = buf[i + 3]

        # Pack header
        if code == 0xBA:
            b4, b6, b8, b9 = buf[i + 4], buf[i + 6], buf[i + 8], buf[i + 9]
            # MPEG-2
            if (b4 & 0xC4) == 0x44 and (b6 & 0x04) == 0x04 and (b8 & 0x04) == 0x04 and (b9 & 0x01) == 0x01 and (buf[i + 12] & 0x03) == 0x03:
                return (buf[i + 13] & 0x07) + 14
            # MPEG-1
            if (b4 & 0xF1) == 0x21 and (b6 & 0x01) == 0x01 and (b8 & 0x01) == 0x01 and (b9 & 0x80) == 0x80 and (buf[i + 11] & 0x01) == 0x01:
                return 12
            return 0

        # End code
        if code == 0xB9:
            return 4

        # Sequence, extension, GOP
        if code == 0xB3:
            return 12 if (buf[i + 10] & 0x20) == 0x20 else 0
        if code == 0xB5:
            return 10
        if code == 0xB8:
            return 8 if (buf[i + 5] & 0x40) == 0x40 else 0

        # PES and system/padding/private streams
        if code in (0xBB, 0xBE, 0xBF) or 0xBD <= code <= 0xEF:
            if i + 6 > len(buf):
                return 0
            return (buf[i + 4] << 8) + buf[i + 5] + 6

        return 0

    pos = 0
    last_valid_end = 0
    while pos + 14 <= len(data):
        sz = _packet_size(data, pos)
        if sz <= 0:
            break
        if pos + sz > len(data):
            break
        pos += sz
        last_valid_end = pos
        # Explicit end code
        if sz == 4 and data[pos - 1] == 0xB9:
            return start + pos

    return start + last_valid_end if last_valid_end > MIN_VIDEO_SIZE else None
 
 
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
def validate_jpeg(data: bytes, min_dim: int) -> Optional[tuple[int, int]]:
    """Validate JPEG data, returning (width, height) or None."""
    if not HAS_PIL:
        return (0, 0)  # Can't validate without PIL, accept everything

    try:
        with suppress_native_stderr():
            img = PILImage.open(io.BytesIO(data))
            w, h = img.size
            if w < min_dim or h < min_dim:
                return None
            # Force full decode so truncated/corrupt JPEGs are rejected.
            img.load()
            return (w, h)
    except Exception:
        return None


# SOF markers (start of frame); progressive DCT uses C2,C6,CA,CE.
_JPEG_SOF_MARKERS = frozenset({
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
})
_JPEG_SOF_PROGRESSIVE = frozenset({0xC2, 0xC6, 0xCA, 0xCE})


def jpeg_marker_sof_info(data: bytes) -> tuple[Optional[int], Optional[int], bool]:
    """
    Scan JPEG markers for the first SOF: (width, height, progressive).
    Pure bytes; no Pillow. Width/height None if no SOF found.
    """
    n = len(data)
    i = 0
    progressive = False
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xD8:  # SOI
            i += 2
            continue
        if marker == 0xD9:  # EOI
            break
        if marker in (0x01, 0xFF) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:  # SOS — start of entropy-coded data
            break
        if i + 4 > n:
            break
        seglen = (data[i + 2] << 8) | data[i + 3]
        if seglen < 2 or i + 2 + seglen > n:
            break
        if marker in _JPEG_SOF_MARKERS:
            if marker in _JPEG_SOF_PROGRESSIVE:
                progressive = True
            off = i + 4
            # P, Y_hi, Y_lo, X_hi, X_lo
            if off + 5 <= n:
                h = (data[off + 1] << 8) | data[off + 2]
                w = (data[off + 3] << 8) | data[off + 4]
                if w > 0 and h > 0:
                    return w, h, progressive
        i += 2 + seglen
    return None, None, progressive


def jpeg_compression_manifest_hints(
    jpeg_data: bytes, byte_size: int, width: int, height: int
) -> dict:
    """
    Extra recovery-manifest fields for media_classifier (no Pillow required).
    """
    sof_w, sof_h, progressive = jpeg_marker_sof_info(jpeg_data)
    ew = width if width > 0 else (sof_w or 0)
    eh = height if height > 0 else (sof_h or 0)
    bpp: Optional[float] = None
    if ew > 0 and eh > 0 and byte_size > 0:
        bpp = round((8.0 * byte_size) / float(ew * eh), 5)
    matches_still = ew > 0 and eh > 0 and (ew, eh) in COMMON_STILL_PHOTO_RESOLUTIONS
    return {
        "bits_per_pixel": bpp,
        "progressive_jpeg": progressive,
        "matches_common_still_resolution": matches_still,
    }
 
 
def validate_extracted_media(path: Path, media_type: MediaType, ext: str) -> tuple[int, int]:
    """
    Optional post-extraction validation using available third-party libraries.

    Returns (attempted, succeeded) counts for optional validators.
    """
    attempted = 0
    succeeded = 0
    ext_l = ext.lower()

    def _attempt(fn) -> bool:
        nonlocal attempted, succeeded
        attempted += 1
        try:
            with suppress_native_stderr():
                ok = fn()
            if ok:
                succeeded += 1
            return ok
        except Exception:
            return False

    if media_type == MediaType.PHOTO:
        # Pillow decode/verify for common raster + HEIF via pillow-heif plugin.
        if HAS_PIL and ext_l in {"jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp", "heif", "heic", "avif"}:
            def _pil_ok() -> bool:
                img = PILImage.open(path)
                img.verify()
                return True
            _attempt(_pil_ok)

        # OpenCV image decode check.
        if HAS_CV2 and ext_l in {"jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp"}:
            def _cv2_ok() -> bool:
                img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                return img is not None and getattr(img, "size", 0) > 0
            _attempt(_cv2_ok)

        # imagecodecs decode check.
        if HAS_IMAGECODECS and ext_l in {"jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp", "avif"}:
            def _imagecodecs_ok() -> bool:
                arr = imagecodecs.imread(str(path))
                return arr is not None
            _attempt(_imagecodecs_ok)

        # RAW decode probe.
        if HAS_RAWPY and ext_l in {"cr2", "nef", "arw", "dng", "orf", "raf", "rw2", "srw", "pef", "cr3"}:
            def _raw_ok() -> bool:
                with rawpy.imread(str(path)):
                    return True
            _attempt(_raw_ok)

    else:  # VIDEO
        # PyAV stream probe.
        if HAS_PYAV and ext_l in {"avi", "mp4", "mov", "mkv", "webm", "mts", "mpg", "mpeg", "flv", "wmv", "asf", "3gp", "3g2", "m4v"}:
            def _pyav_ok() -> bool:
                with av.open(str(path)) as container:
                    return len(container.streams) > 0
            _attempt(_pyav_ok)

        # MediaInfo metadata probe.
        if HAS_MEDIAINFO and ext_l in {"avi", "mp4", "mov", "mkv", "webm", "mts", "mpg", "mpeg", "flv", "wmv", "asf", "3gp", "3g2", "m4v"}:
            def _mediainfo_ok() -> bool:
                mi = MediaInfo.parse(str(path))
                return bool(getattr(mi, "tracks", []))
            _attempt(_mediainfo_ok)

    return attempted, succeeded


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
        skip_jpeg_after_video: bool = False,
        skip_jpeg_after_video_window_mb: int = 256,
        burst_frame_clustering: bool = False,
        write_recovery_manifest: bool = True,
    ):
        self.image_path = image_path
        self.image_size = detect_input_size(image_path)
        self.output_root = Path(output_dir).resolve()
        self.write_recovery_manifest = write_recovery_manifest
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
        self.skip_jpeg_after_video_window_bytes = skip_jpeg_after_video_window_mb * 1024 * 1024
        self.burst_frame_clustering = burst_frame_clustering
        self.video_found = False
        self.video_found_offset: Optional[int] = None
        # Byte spans of recovered AVI files that declare MJPEG video (strh handler).
        self._mjpeg_avi_spans: list[tuple[int, int]] = []
        # Recent JPEGs (offset, width, height) for burst / cluster heuristics.
        self._jpeg_burst_recent: deque[tuple[int, int, int]] = deque(maxlen=64)
 
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

    def _jpeg_inside_declared_mjpeg_avi(self, offset: int) -> bool:
        for a, b in self._mjpeg_avi_spans:
            if a <= offset < b:
                return True
        return False

    def _jpeg_burst_cluster_gated(self, start: int, w: int, h: int) -> bool:
        """
        True when several same-dimension JPEGs appear close on disk (typical of
        frame strips). Caller must combine with context (MJPEG AVI span, near
        video, or configured frame resolution) to reduce still-photo burst FPs.
        """
        while (
            self._jpeg_burst_recent
            and start - self._jpeg_burst_recent[0][0] > JPEG_BURST_WINDOW_BYTES
        ):
            self._jpeg_burst_recent.popleft()
        peers = [e for e in self._jpeg_burst_recent if e[1] == w and e[2] == h]
        group = peers + [(start, w, h)]
        if len(group) < JPEG_BURST_MIN_FRAMES:
            self._jpeg_burst_recent.append((start, w, h))
            return False
        group.sort(key=lambda t: t[0])
        if group[-1][0] - group[0][0] > JPEG_BURST_WINDOW_BYTES:
            self._jpeg_burst_recent.append((start, w, h))
            return False
        for i in range(1, len(group)):
            if group[i][0] - group[i - 1][0] > JPEG_BURST_MAX_STEP_GAP_BYTES:
                self._jpeg_burst_recent.append((start, w, h))
                return False
        self._jpeg_burst_recent.append((start, w, h))
        return True
 
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

        jpeg_carver_meta: Optional[dict] = None
 
        # Clamp to image boundary
        actual_end = min(end, self.image_size)
        actual_size = actual_end - start

        if fmt_name == "AVI" and actual_size >= self.min_video_size:
            avi_abs_end = start + actual_size
            if avi_file_contains_mjpeg_video_stream(f, start, avi_abs_end):
                self._mjpeg_avi_spans.append((start, avi_abs_end))
 
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
                self.video_found_offset = start
            return True  # Still "handled" — skip past it
 
        w, h = 0, 0
        force_frame_mode = False
        # JPEG-specific validation
        if fmt_name == "JPEG":
            f.seek(start)
            jpeg_data = f.read(actual_size)
            dims = validate_jpeg(jpeg_data, self.min_dimension)
            if dims is None and HAS_PIL:
                # Try larger boundaries: false early EOI markers can truncate JPEGs.
                max_jpeg_end = min(start + MAX_PHOTO_SIZE, self.image_size)
                retry_from = actual_end
                retries = 0
                max_retries = 8
                while retries < max_retries and retry_from < max_jpeg_end:
                    next_end = _find_next_jpeg_eoi(f, retry_from, max_jpeg_end)
                    if next_end is None:
                        break
                    new_size = next_end - start
                    if new_size <= actual_size:
                        retry_from = next_end
                        retries += 1
                        continue
                    f.seek(start)
                    candidate = f.read(new_size)
                    candidate_dims = validate_jpeg(candidate, self.min_dimension)
                    if candidate_dims is not None:
                        jpeg_data = candidate
                        dims = candidate_dims
                        actual_end = next_end
                        actual_size = new_size
                        break
                    retry_from = next_end
                    retries += 1
            if dims is None:
                stats.skipped_frames += 1
                return True  # Skip but don't save
            if dims == (0, 0):
                # PIL not available, accept anyway
                dims = None
            w, h = dims if dims else (0, 0)
            is_frame_resolution = w > 0 and h > 0 and (w, h) in self.skip_resolutions
            inside_mjpeg_avi = self._jpeg_inside_declared_mjpeg_avi(start)
            if inside_mjpeg_avi:
                force_frame_mode = True
            if self.skip_jpeg_after_video and self.video_found and self.video_found_offset is not None:
                # Skip likely embedded video-frame JPEGs near recently recovered videos.
                if start >= self.video_found_offset:
                    dist = start - self.video_found_offset
                    if dist <= self.skip_jpeg_after_video_window_bytes:
                        # If dimensions are known, route configured frame resolutions to frames/.
                        # If dimensions are unknown (e.g., no Pillow), keep conservative behavior.
                        if (dims is None) or is_frame_resolution:
                            force_frame_mode = True
            if (
                self.burst_frame_clustering
                and HAS_PIL
                and w > 0
                and h > 0
                and self._jpeg_burst_cluster_gated(start, w, h)
            ):
                near_video = (
                    self.video_found
                    and self.video_found_offset is not None
                    and start >= self.video_found_offset
                    and (start - self.video_found_offset)
                    <= self.skip_jpeg_after_video_window_bytes
                )
                if inside_mjpeg_avi or is_frame_resolution:
                    force_frame_mode = True
                elif near_video and (w, h) not in COMMON_STILL_PHOTO_RESOLUTIONS:
                    force_frame_mode = True
            near_video_dist = None
            if self.video_found and self.video_found_offset is not None and start >= self.video_found_offset:
                near_video_dist = start - self.video_found_offset
            jpeg_carver_meta = {
                "width": w if w > 0 else None,
                "height": h if h > 0 else None,
                "inside_mjpeg_avi": inside_mjpeg_avi,
                "matches_skip_frame_resolution": is_frame_resolution,
                "near_video_offset_bytes": near_video_dist,
                "video_proximity_window_bytes": self.skip_jpeg_after_video_window_bytes,
            }
            jpeg_carver_meta.update(
                jpeg_compression_manifest_hints(jpeg_data, actual_size, w, h)
            )
            dim_str = f"_{w}x{h}" if w > 0 else ""
        else:
            dim_str = ""
 
        # Generate output path
        file_id = self.state.next_id(media_type)
        frame_mode = (
            (fmt_name == "JPEG" and media_type == MediaType.PHOTO and force_frame_mode)
            or (
                fmt_name == "JPEG"
                and media_type == MediaType.PHOTO
                and self.video_found
                and not self.skip_jpeg_after_video
                and w > 0 and h > 0
                and (w, h) in self.skip_resolutions
            )
        )
        out_dir = self.photo_dir if media_type == MediaType.PHOTO else self.video_dir
        if frame_mode:
            out_dir = self.video_frame_dir
        bucket = (
            "videos"
            if media_type == MediaType.VIDEO
            else ("frames" if frame_mode else "photos")
        )
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

        # Optional validator stack: use-if-available, non-blocking.
        attempted, succeeded = validate_extracted_media(out_path, media_type, ext)
        if attempted > 0 and succeeded == 0:
            self.state.log(
                f"    WARN {fmt_name} @ {start/1e6:.1f}MB: optional validators failed ({attempted} tried)"
            )
 
        saved_sha256: Optional[str] = None
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
                    self.video_found_offset = start
                return True

            self.state.record_sha256(full_digest)
            saved_sha256 = full_digest
        else:
            self.state.record(fp)
 
        if media_type == MediaType.PHOTO:
            stats.new_photos += 1
        else:
            stats.new_videos += 1
            self.video_found = True
            self.video_found_offset = start
 
        self.state.log(
            f"    {fmt_name} #{file_id}: {actual_size/1024:.0f}KB "
            f"@ {start/1e6:.1f}MB -> {filename}"
        )

        if self.write_recovery_manifest:
            rec: dict = {
                "v": RECOVERY_MANIFEST_VERSION,
                "path": f"{bucket}/{filename}",
                "bucket": bucket,
                "format": fmt_name,
                "extension": ext,
                "source_offset": start,
                "source_end": start + actual_size,
                "size_bytes": actual_size,
            }
            if jpeg_carver_meta is not None:
                rec["jpeg"] = jpeg_carver_meta
            if saved_sha256:
                rec["sha256"] = saved_sha256
            self.state.append_manifest_record(rec)
 
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
    parser.add_argument(
        "--skip-video-frame-res",
        type=str,
        action="append",
        default=None,
        help=(
            "Skip JPEG frames at one or more resolutions (repeat flag or comma-separated, "
            f"default: {DEFAULT_SKIP_VIDEO_FRAME_RES})"
        ),
    )
    parser.add_argument("--reset", action="store_true",
                        help="Reset scan state and start fresh")
    parser.add_argument("--report", "--report-only", dest="report_only", action="store_true",
                        help="Print a report of existing recovered files without scanning")
    parser.add_argument("--fast-dedup", action="store_false", dest="strict_dedup",
                        help="Use sampled-hash dedup instead of full SHA-256")
    parser.add_argument(
        "--skip-jpeg-after-video",
        action="store_true",
        dest="skip_jpeg_after_video",
        help=(
            "Stricter separation: within --skip-jpeg-after-video-window-mb after a "
            "recovered video, route unknown-size or configured frame-size JPEGs to frames/"
        ),
    )
    parser.add_argument(
        "--burst-frame-clustering",
        action="store_true",
        dest="burst_frame_clustering",
        help=(
            "Enable burst clustering (tight runs of same WxH) as an extra frame hint "
            "near video / in MJPEG spans (off by default for maximum recovery)"
        ),
    )
    parser.add_argument("--skip-jpeg-after-video-window-mb", type=int, default=256,
                        help="Window for --skip-jpeg-after-video / burst proximity in MB (default: 256)")
    parser.add_argument(
        "--recovery-manifest",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Write .scan_state/recovery_manifest.jsonl for media_classifier "
            "(default: --recovery-manifest)"
        ),
    )
    parser.set_defaults(
        skip_jpeg_after_video=False,
        burst_frame_clustering=False,
    )
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
    # Keep third-party library chatter from polluting scan logs in verbose mode.
    logging.getLogger("PIL").setLevel(logging.WARNING)
    log_optional_library_status()
 
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
    if args.skip_jpeg_after_video_window_mb < 0:
        parser.error("--skip-jpeg-after-video-window-mb must be >= 0")
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
    res_inputs = args.skip_video_frame_res if args.skip_video_frame_res else [DEFAULT_SKIP_VIDEO_FRAME_RES]
    for item in res_inputs:
        for token in item.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                w, h = token.lower().split("x")
                skip_res.add((int(w), int(h)))
            except ValueError:
                parser.error(
                    "--skip-video-frame-res must be WxH values, "
                    "repeatable or comma-separated (e.g., 1280x720,1920x1080)"
                )
 
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
        skip_jpeg_after_video_window_mb=args.skip_jpeg_after_video_window_mb,
        burst_frame_clustering=args.burst_frame_clustering,
        write_recovery_manifest=args.recovery_manifest,
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
