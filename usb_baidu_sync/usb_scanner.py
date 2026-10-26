"""USB directory traversal and candidate file extractor."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from usb_baidu_sync.ignore_rules import is_ignored


@dataclass
class FileInfo:
    rel_path: str
    abs_path: Path
    size: int
    mtime: float


def scan_volume(
    mount_path: Path | str,
    ignore_patterns: Sequence[str] | None = None,
) -> list[FileInfo]:
    """Recursively scan a mounted volume and return valid candidate files."""
    root = Path(mount_path)
    if not root.is_dir():
        return []

    results: list[FileInfo] = []

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            # If current directory itself is ignored, prune its subdirectories
            if is_ignored(rel_dir, ignore_patterns):
                dirnames.clear()
                continue

        # Prune subdirectories that match ignore rules
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(os.path.join(rel_dir, d) if rel_dir != "." else d, ignore_patterns)
        ]

        for fname in filenames:
            rel_file = os.path.join(rel_dir, fname) if rel_dir != "." else fname
            if is_ignored(rel_file, ignore_patterns):
                continue

            full_p = Path(dirpath) / fname
            if not full_p.is_file():
                continue

            try:
                # Resolve potential symlinks safely
                stat = full_p.stat()
                results.append(
                    FileInfo(
                        rel_path=rel_file,
                        abs_path=full_p,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                    )
                )
            except (OSError, PermissionError):
                continue

    results.sort(key=lambda x: x.rel_path)
    return results
