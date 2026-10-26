"""Configuration manager and data models for USBBaiduSync."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_IGNORE_PATTERNS = [
    ".DS_Store",
    "._*",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    "__MACOSX",
    "Thumbs.db",
    "desktop.ini",
    "$RECYCLE.BIN",
    "System Volume Information",
    ".TemporaryItems",
]


@dataclass
class AppConfig:
    remote_base_dir: str = "/我的备份/U盘自动备份"
    bduss: str = ""
    ignore_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS))
    dry_run: bool = False
    auto_start: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        patterns = data.get("ignore_patterns", DEFAULT_IGNORE_PATTERNS)
        return cls(
            remote_base_dir=data.get("remote_base_dir", "/我的备份/U盘自动备份"),
            bduss=data.get("bduss", ""),
            ignore_patterns=list(patterns),
            dry_run=bool(data.get("dry_run", False)),
            auto_start=bool(data.get("auto_start", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConfigManager:
    """Manages application configuration stored in JSON."""

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            base_dir = Path.home() / "Library" / "Application Support" / "USBBaiduSync"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = base_dir / "config.json"
        else:
            self.config_path = Path(config_path)
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self._config: AppConfig | None = None

    def load(self) -> AppConfig:
        """Load configuration from file or create defaults if not present."""
        if not self.config_path.exists():
            cfg = AppConfig()
            self.save(cfg)
            self._config = cfg
            return cfg

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._config = AppConfig.from_dict(data)
        except Exception:
            self._config = AppConfig()
            self.save(self._config)

        return self._config

    def save(self, config: AppConfig) -> None:
        """Save configuration to JSON file."""
        self._config = config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    def update(self, fields: dict[str, Any]) -> AppConfig:
        """Update specific configuration fields and persist."""
        cfg = self.load()
        for key, value in fields.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        self.save(cfg)
        return cfg

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            return self.load()
        return self._config
