"""坐标系换算：纯 Python，不依赖 Qt，便于单测与后续迁 C++。

三层坐标：
1. 全局逻辑坐标：Qt 的 global 坐标（多屏并集，原点左上）
2. 屏幕内逻辑坐标：相对该屏左上角
3. 图像物理像素：屏幕内逻辑坐标 × 该屏的缩放（dpr）

约定：图形项、选区宽高一律用物理像素；跨屏换算只允许调用本模块。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenGeometry:
    """一块屏幕的几何信息，坐标与尺寸都是逻辑像素。"""

    name: str
    x: int
    y: int
    width: int
    height: int
    dpr: float = 1.0

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, gx: float, gy: float) -> bool:
        return self.x <= gx < self.right and self.y <= gy < self.bottom

    def contains_rect(self, gx: int, gy: int, gw: int, gh: int) -> bool:
        return (
            self.x <= gx
            and self.y <= gy
            and gx + gw <= self.right
            and gy + gh <= self.bottom
        )

    @property
    def physical_size(self) -> tuple[int, int]:
        return (
            round(self.width * self.dpr),
            round(self.height * self.dpr),
        )


def containing(screens: list[ScreenGeometry], gx: float, gy: float) -> ScreenGeometry | None:
    """返回包含该全局点的屏幕；落在空隙时返回最近的一块。"""
    for screen in screens:
        if screen.contains(gx, gy):
            return screen
    if not screens:
        return None

    def distance(s: ScreenGeometry) -> float:
        dx = max(s.x - gx, 0, gx - s.right)
        dy = max(s.y - gy, 0, gy - s.bottom)
        return dx * dx + dy * dy

    return min(screens, key=distance)


def local_to_global(screen: ScreenGeometry, lx: float, ly: float) -> tuple[float, float]:
    return screen.x + lx, screen.y + ly


def global_to_local(screen: ScreenGeometry, gx: float, gy: float) -> tuple[float, float]:
    return gx - screen.x, gy - screen.y


def local_to_physical(screen: ScreenGeometry, lx: float, ly: float) -> tuple[float, float]:
    return lx * screen.dpr, ly * screen.dpr


def physical_to_local(screen: ScreenGeometry, px: float, py: float) -> tuple[float, float]:
    if screen.dpr <= 0:
        return px, py
    return px / screen.dpr, py / screen.dpr


def global_to_physical(gx: float, gy: float, screen: ScreenGeometry) -> tuple[float, float]:
    lx, ly = global_to_local(screen, gx, gy)
    return local_to_physical(screen, lx, ly)


def axis_scale(logical_length: float, physical_length: float) -> float:
    """截图像素与逻辑尺寸未必正好等于 dpr，按实际图像反推每轴缩放。"""
    if logical_length <= 0:
        return 1.0
    return physical_length / logical_length


def virtual_bounds(screens: list[ScreenGeometry]) -> tuple[int, int, int, int]:
    """所有屏幕并集的外接矩形（逻辑像素）：(x, y, w, h)。"""
    if not screens:
        return 0, 0, 0, 0
    left = min(s.x for s in screens)
    top = min(s.y for s in screens)
    right = max(s.right for s in screens)
    bottom = max(s.bottom for s in screens)
    return left, top, right - left, bottom - top


def need_scan(screens: list[ScreenGeometry], gx: float, gy: float) -> bool:
    """坐标是否落在屏幕之外（用于判定选区越界）。"""
    return any(s.contains(gx, gy) for s in screens) is False


def rect_union(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = min(ax, bx)
    top = min(ay, by)
    right = max(ax + aw, bx + bw)
    bottom = max(ay + ah, by + bh)
    return left, top, right - left, bottom - top
