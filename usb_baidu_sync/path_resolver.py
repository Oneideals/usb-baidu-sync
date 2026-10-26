"""Remote path resolver for formatting Baidu Netdisk archive paths."""
from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath


def resolve_remote_path(
    base_dir: str,
    volume_name: str,
    rel_path: str,
    date_str: str | None = None,
) -> str:
    """Resolve target path on Baidu Netdisk for a file from a USB volume.

    Format: <base_dir>/<YYYY-MM-DD>_<volume_name>/<rel_path>
    """
    if date_str is None:
        date_str = date.today().isoformat()

    clean_base = "/" + base_dir.strip("/")
    clean_volume = volume_name.strip() or "USB_DRIVE"
    folder_name = f"{date_str}_{clean_volume}"

    clean_rel = rel_path.strip("/")
    full_path = PurePosixPath(clean_base) / folder_name / clean_rel
    return str(full_path)
