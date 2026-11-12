"""配置：dataclass + JSON，未知字段忽略，越界值回落默认。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
from pathlib import Path
from typing import Any

VALID_FORMATS = ("png", "jpg")


@dataclass
class Settings:
    # 热键：F1 为默认；macOS 上 F1 被当作亮度键时注册会失败，自动改用 fallback
    hotkey: str = "F1"
    hotkey_fallback: str = "Ctrl+Alt+A"
    hotkey_enabled: bool = True

    # 延时截图（秒），0 表示不延时
    delay_seconds: int = 3

    # 保存
    save_dir: str = ""          # 空表示用系统图片目录
    image_format: str = "png"
    jpeg_quality: int = 92

    # 行为
    auto_copy: bool = True
    auto_save: bool = True
    play_sound: bool = False
    start_at_login: bool = False

    # 贴图
    pin_limit: int = 20          # 贴图不跨重启恢复（v1 有意不做持久化）

    # 标注默认样式
    annotation_color: str = "#ff3b30"
    annotation_width: float = 3.0
    font_size: int = 16

    extra: dict[str, Any] = field(default_factory=dict)

    # ---------- 校验 ----------

    def normalized(self) -> "Settings":
        if self.image_format not in VALID_FORMATS:
            self.image_format = "png"
        self.jpeg_quality = max(1, min(100, int(self.jpeg_quality)))
        self.delay_seconds = max(0, min(30, int(self.delay_seconds)))
        self.pin_limit = max(1, min(100, int(self.pin_limit)))
        self.annotation_width = max(0.5, min(20.0, float(self.annotation_width)))
        self.font_size = max(8, min(96, int(self.font_size)))
        if not self.hotkey.strip():
            self.hotkey = "F1"
        return self

    # ---------- 序列化 ----------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("extra", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        known = {f.name for f in fields(cls)} - {"extra"}
        values = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        settings = cls(**values, extra=extra)
        return settings.normalized()


def load_settings(path: Path) -> Settings:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings().normalized()
    except OSError:
        return Settings().normalized()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 配置损坏时不要清空用户设置文件，只回退默认值
        return Settings().normalized()
    if not isinstance(data, dict):
        return Settings().normalized()
    return Settings.from_dict(data)


def save_settings(path: Path, settings: Settings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
