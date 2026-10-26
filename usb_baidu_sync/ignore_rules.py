"""File and directory ignore rule matcher for macOS and general rubbish files."""
from __future__ import annotations

import fnmatch
from pathlib import PurePath
from typing import Sequence

from usb_baidu_sync.config import DEFAULT_IGNORE_PATTERNS


def is_ignored(rel_path: str, patterns: Sequence[str] | None = None) -> bool:
    """Determine whether a relative path should be ignored.

    Checks each path segment and the full relative path against patterns.
    """
    if patterns is None:
        patterns = DEFAULT_IGNORE_PATTERNS

    path_obj = PurePath(rel_path)
    parts = path_obj.parts

    for pattern in patterns:
        clean_pat = pattern.strip("/")
        # Check against full path
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, clean_pat):
            return True

        # Check against each path component (e.g., subfolder/._image.png, .Spotlight-V100/Store.db)
        for part in parts:
            if fnmatch.fnmatch(part, clean_pat):
                return True
            # Handle macOS resource fork files: starts with "._"
            if clean_pat == "._*" and part.startswith("._"):
                return True

    return False
