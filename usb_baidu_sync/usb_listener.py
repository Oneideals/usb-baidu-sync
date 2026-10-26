"""macOS NSWorkspace volume mount and unmount notification listener."""
from __future__ import annotations

import logging
import plistlib
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MountCallback = Callable[[str, str, str], None]  # (mount_path, volume_name, volume_uuid)
UnmountCallback = Callable[[str], None]  # (mount_path)


def get_volume_metadata(mount_path: str | Path) -> tuple[str, str, bool]:
    """Retrieve volume name, volume UUID, and whether it's a removable external drive using diskutil.

    Returns (volume_name, volume_uuid, is_removable).
    """
    path = str(mount_path)
    try:
        res = subprocess.run(
            ["diskutil", "info", "-plist", path],
            capture_output=True,
            check=True,
            timeout=5,
        )
        info = plistlib.loads(res.stdout)
        name = info.get("VolumeName") or Path(path).name
        uuid = (
            info.get("VolumeUUID")
            or info.get("DiskUUID")
            or info.get("MediaUUID")
            or info.get("VolumeSerialNumber")
            or info.get("DeviceIdentifier")
            or f"NO_UUID_{name}_{info.get('TotalSize', 0)}"
        )
        removable = bool(info.get("RemovableMedia", False) or info.get("Ejectable", False))
        is_internal = bool(info.get("Internal", False))

        # Accept if explicitly ejectable/removable, or if located in /Volumes/ and not the root filesystem
        is_external = (removable or not is_internal) and path != "/" and path.startswith("/Volumes/")
        return name, str(uuid), is_external
    except Exception as e:
        logger.debug("diskutil info failed for %s: %s", path, e)
        name = Path(path).name
        # Fallback heuristic
        is_external = path.startswith("/Volumes/") and path != "/"
        return name, f"FALLBACK_{name}", is_external


class USBListener:
    """Listens for macOS volume mount and unmount events via PyObjC Cocoa notifications."""

    def __init__(
        self,
        on_mount: MountCallback | None = None,
        on_unmount: UnmountCallback | None = None,
    ) -> None:
        self.on_mount = on_mount
        self.on_unmount = on_unmount
        self._observer = None

    def start(self) -> None:
        """Register observers with NSWorkspace."""
        try:
            from AppKit import NSWorkspace
            from Foundation import NSObject

            outer = self

            class MountObserver(NSObject):
                def volumeMounted_(self, notification):
                    try:
                        user_info = notification.userInfo()
                        url = user_info.get("NSWorkspaceVolumeURLKey")
                        path = url.path() if url else None
                        if not path:
                            return

                        name, uuid, is_external = get_volume_metadata(path)
                        if is_external and outer.on_mount:
                            logger.info("External USB volume detected: %s (%s)", name, path)
                            outer.on_mount(path, name, uuid)
                    except Exception as err:
                        logger.error("Error processing mount notification: %s", err)

                def volumeUnmounted_(self, notification):
                    try:
                        user_info = notification.userInfo()
                        url = user_info.get("NSWorkspaceVolumeURLKey")
                        path = url.path() if url else None
                        if path and outer.on_unmount:
                            logger.info("Volume unmounted: %s", path)
                            outer.on_unmount(path)
                    except Exception as err:
                        logger.error("Error processing unmount notification: %s", err)

            self._observer = MountObserver.alloc().init()
            center = NSWorkspace.sharedWorkspace().notificationCenter()
            center.addObserver_selector_name_object_(
                self._observer,
                "volumeMounted:",
                "NSWorkspaceDidMountNotification",
                None,
            )
            center.addObserver_selector_name_object_(
                self._observer,
                "volumeUnmounted:",
                "NSWorkspaceDidUnmountNotification",
                None,
            )
            logger.info("USBListener registered NSWorkspace notifications successfully.")
        except ImportError:
            logger.warning("PyObjC Cocoa not available in current environment; running in fallback mode.")
        except Exception as e:
            logger.error("Failed to register NSWorkspace observer: %s", e)

    def stop(self) -> None:
        """Remove observers from NSWorkspace."""
        if self._observer:
            try:
                from AppKit import NSWorkspace
                center = NSWorkspace.sharedWorkspace().notificationCenter()
                center.removeObserver_(self._observer)
            except Exception as e:
                logger.debug("Failed removing observer: %s", e)
            self._observer = None
