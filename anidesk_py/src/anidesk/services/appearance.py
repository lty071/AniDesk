from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from anidesk.platform.paths import app_data_dir


THEMES = {
    "sakura": dict(name="樱花日常", description="奶白与樱粉，收藏每一份心动。", dark=False,
                   base="#fff6f8", surface="#ffffff", text="#382d3b", muted="#786778",
                   primary="#b44069", secondary="#ad8dcc", soft="#f9e3ec", border="#ead8e2",
                   sidebar="#fffafd", alternate="#fff5f8"),
    "starlight": dict(name="星空放映室", description="深蓝夜空，让今晚的故事慢慢展开。", dark=True,
                      base="#131829", surface="#20283f", text="#edf0ff", muted="#acb6d1",
                      primary="#b8a4ff", secondary="#799ce9", soft="#353957", border="#404969",
                      sidebar="#192037", alternate="#252e48"),
    "soda": dict(name="夏日汽水", description="晴空、薄荷与一整个夏天的期待。", dark=False,
                 base="#f0f7fd", surface="#ffffff", text="#193450", muted="#65788e",
                 primary="#007b84", secondary="#88bcea", soft="#e0f1f8", border="#cddfeb",
                 sidebar="#eaf4fc", alternate="#f5faff"),
}

SIDEBAR_IMAGES = {"sea": "海风来信", "stars": "静夜星河", "sakura": "樱花小径"}


@dataclass(frozen=True)
class Appearance:
    theme: str = "soda"
    font_size: int = 14
    accent: str = ""
    background: str = ""
    brightness: int = 85
    softness: int = 0
    panel_opacity: int = 94
    decorations: bool = True
    sidebar_source: str = "builtin"
    sidebar_builtin: str = "sea"
    sidebar_custom: str = ""
    sidebar_position: str = "bottom"
    sidebar_zoom: int = 100
    sidebar_fade: bool = True

    @classmethod
    def from_dict(cls, value: object) -> Appearance:
        if not isinstance(value, dict):
            return cls()

        def number(key: str, default: int, low: int, high: int) -> int:
            raw = value.get(key)
            return max(low, min(high, raw)) if type(raw) is int else default

        theme = value.get("theme")
        accent = value.get("accent")
        font = value.get("font_size")
        def choice(key: str, allowed, default: str) -> str:
            item = value.get(key)
            return item if isinstance(item, str) and item in allowed else default
        return cls(
            theme=theme if isinstance(theme, str) and theme in THEMES else "soda",
            font_size=font if type(font) is int and font in (12, 14, 16) else 14,
            accent=accent.lower() if isinstance(accent, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", accent) else "",
            background=value.get("background") if isinstance(value.get("background"), str) else "",
            brightness=number("brightness", 85, 20, 100),
            softness=number("softness", 0, 0, 24),
            panel_opacity=number("panel_opacity", 94, 65, 100),
            decorations=value.get("decorations") if type(value.get("decorations")) is bool else True,
            sidebar_source=choice("sidebar_source", ("builtin", "custom", "none"), "builtin"),
            sidebar_builtin=choice("sidebar_builtin", SIDEBAR_IMAGES, "sea"),
            sidebar_custom=value.get("sidebar_custom") if isinstance(value.get("sidebar_custom"), str) else "",
            sidebar_position=choice("sidebar_position", ("top", "center", "bottom"), "bottom"),
            sidebar_zoom=number("sidebar_zoom", 100, 100, 180),
            sidebar_fade=value.get("sidebar_fade") if type(value.get("sidebar_fade")) is bool else True,
        )


class AppearanceStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else app_data_dir(create=False)
        self.path = self.directory / "appearance.json"
        self.warning = ""

    def background_path(self, relative: str) -> Path | None:
        if not relative or Path(relative).is_absolute():
            return None
        try:
            candidate = (self.directory / relative).resolve()
            root = (self.directory / "themes" / "backgrounds").resolve()
            return candidate if candidate.is_relative_to(root) and candidate.is_file() else None
        except (OSError, ValueError):
            return None

    def load(self) -> Appearance:
        self.warning = ""
        if not self.path.exists():
            return Appearance()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Appearance must be an object")
            result = Appearance.from_dict(raw)
        except (ValueError, OSError):
            self.warning = "外观设置无法读取，已使用默认主题；原文件会在应用新外观后替换。"
            return Appearance()
        if result.background and self.background_path(result.background) is None:
            self.warning = "背景文件已丢失，暂时显示主题底色。可以重新选择图片。"
        if result.sidebar_source == "custom" and self.background_path(result.sidebar_custom) is None:
            self.warning = "侧栏图片已丢失，暂时使用系统内置插画。请重新添加图片。"
        return result

    def save(self, settings: Appearance) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix="appearance-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"schema_version": 1, **asdict(settings)}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            temporary.replace(self.path)
            self.warning = ""
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
