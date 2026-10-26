"""Fast fingerprint and hash calculation for incremental sync."""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_SIZE = 64 * 1024  # 64 KB
THRESHOLD_SIZE = 10 * 1024 * 1024  # 10 MB


def calculate_fast_hash(file_path: Path, file_size: int) -> str:
    """Calculate a fast fingerprint hash for a file.

    For files < 10MB, computes full MD5.
    For files >= 10MB, reads header, middle, and tail 64KB slices with size prefix.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    md5 = hashlib.md5()

    if file_size < THRESHOLD_SIZE:
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE * 4):
                md5.update(chunk)
        return md5.hexdigest()

    # Large file: header + middle + tail
    md5.update(f"size:{file_size}:".encode("ascii"))
    with open(path, "rb") as f:
        # Header 64KB
        f.seek(0)
        md5.update(f.read(CHUNK_SIZE))

        # Middle 64KB
        mid_offset = max(0, (file_size // 2) - (CHUNK_SIZE // 2))
        f.seek(mid_offset)
        md5.update(f.read(CHUNK_SIZE))

        # Tail 64KB
        tail_offset = max(0, file_size - CHUNK_SIZE)
        f.seek(tail_offset)
        md5.update(f.read(CHUNK_SIZE))

    return md5.hexdigest()
