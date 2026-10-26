#!/usr/bin/env python3
"""Entry point for USBBaiduSync."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from usb_baidu_sync.menu_bar import USBBaiduSyncApp


def main():
    parser = argparse.ArgumentParser(description="USBBaiduSync - macOS USB to Baidu Netdisk Incremental Uploader")
    parser.add_argument("--dry-run", action="store_true", help="Run in test mode without actually uploading to Baidu")
    parser.add_argument("--config", type=Path, default=None, help="Custom path to config.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("🚀 启动 USBBaiduSync 菜单栏应用...")
    app = USBBaiduSyncApp(config_path=args.config, dry_run=args.dry_run)
    app.start_app()


if __name__ == "__main__":
    main()
