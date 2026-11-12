"""路径与文件命名：配置、数据、保存目录、文件名模板。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .settings import Settings, load_settings, save_settings


def _standard_dir(kind: QStandardPaths.StandardLocation, fallback: Path) -> Path:
    location = QStandardPaths.writableLocation(kind)
    return Path(location) if location else fallback


def config_dir() -> Path:
    return _standard_dir(
        QStandardPaths.StandardLocation.AppConfigLocation,
        Path.home() / ".config" / "snipdraw",
    )


def data_dir() -> Path:
    return _standard_dir(
        QStandardPaths.StandardLocation.AppDataLocation,
        Path.home() / ".local" / "share" / "snipdraw",
    )


def picture_dir() -> Path:
    return _standard_dir(
        QStandardPaths.StandardLocation.PicturesLocation,
        Path.home() / "Pictures",
    )


def config_file() -> Path:
    return config_dir() / "config.json"


def load() -> Settings:
    return load_settings(config_file())


def save(settings: Settings) -> None:
    save_settings(config_file(), settings.normalized())


def resolve_save_dir(settings: Settings) -> Path:
    """用户填了目录就用它，否则落到系统图片目录下的 Snipdraw 子目录。"""
    if settings.save_dir.strip():
        return Path(settings.save_dir).expanduser()
    return picture_dir() / "Snipdraw"


def build_filename(fmt: str, prefix: str = "Snipdraw") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}.{fmt}"


def unique_path(directory: Path, filename: str) -> Path:
    """同一秒内多次截图不要互相覆盖。"""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for index in range(1, 1000):
        alt = directory / f"{stem}_{index}{suffix}"
        if not alt.exists():
            return alt
    return directory / f"{stem}_{datetime.now().strftime('%f')}{suffix}"
