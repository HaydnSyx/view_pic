"""预览与缩略图轮播核心模块。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import flet as ft
from loguru import logger

from collections import OrderedDict

from src.services import image_service

# 预览图片 data URI 简单缓存，提升大图和相邻图片加载性能
_PREVIEW_CACHE: "OrderedDict[Path, str]" = OrderedDict()
_MAX_CACHE_SIZE: int = 10


def _get_image_data_uri(image_path: Path) -> str:
    """获取图片 data URI，带内存缓存。"""

    if image_path in _PREVIEW_CACHE:
        # LRU：命中时移动到队尾
        _PREVIEW_CACHE.move_to_end(image_path)
        return _PREVIEW_CACHE[image_path]

    data_uri = image_service.load_image_data_uri(image_path)

    _PREVIEW_CACHE[image_path] = data_uri
    if len(_PREVIEW_CACHE) > _MAX_CACHE_SIZE:
        # 移除最早使用的条目
        _PREVIEW_CACHE.popitem(last=False)

    return data_uri


def _preload_neighbor_images(images: List[Path], current_index: int) -> None:
    """预加载当前图片的相邻图片，提升切换速度。"""

    for offset in (-1, 1):
        idx = current_index + offset
        if 0 <= idx < len(images):
            path = images[idx]
            try:
                _get_image_data_uri(path)
            except Exception as exc:  # 保底处理，不打断预览
                logger.error("预加载相邻图片失败: {}，错误: {}", path, exc)


def show_preview(
    images: List[Path],
    current_index: int,
    preview_image: ft.Image,
    position_indicator: ft.Container,
    thumbnail_row: ft.Row,
    preview_dialog: ft.AlertDialog,
    page: ft.Page,
    on_thumbnail_click: Callable[[int], None],
    loading_indicator: ft.Container | None = None,
) -> None:
    """显示大图预览并更新缩略图轮播。
    
    Args:
        images: 图片列表
        current_index: 当前索引
        preview_image: 预览图片控件
        position_indicator: 位置指示器
        thumbnail_row: 缩略图行
        preview_dialog: 预览对话框
        page: 页面对象
        on_thumbnail_click: 缩略图点击回调
        loading_indicator: 加载指示器（可选）
    """

    if not (0 <= current_index < len(images)):
        return

    image_path = images[current_index]

    try:
        # 显示loading指示器
        if loading_indicator:
            loading_indicator.visible = True
            preview_image.visible = False  # 隐藏图片
            page.update()
        
        # 当前图片：优先从缓存获取
        preview_image.src = _get_image_data_uri(image_path)
        
        # 隐藏loading，显示图片
        if loading_indicator:
            loading_indicator.visible = False
            preview_image.visible = True

        # 更新位置指示器
        assert isinstance(position_indicator.content, ft.Text)
        position_indicator.content.value = f"{current_index + 1} / {len(images)}"

        # 预加载相邻图片
        _preload_neighbor_images(images, current_index)

        # 更新底部缩略图轮播
        update_thumbnail_carousel(images, current_index, thumbnail_row, on_thumbnail_click)

        # 将预览对话框内容区域拉伸到当前窗口大小，实现“全屏”预览效果
        if isinstance(preview_dialog.content, ft.Container):
            preview_dialog.content.width = page.window.width
            preview_dialog.content.height = page.window.height

        preview_dialog.open = True
        page.update()
    except Exception as exc:  # 保底异常处理
        logger.exception("预览图片失败: {}", image_path)
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"无法预览图片: {exc}"),
            bgcolor=ft.Colors.RED_400,
        )
        page.snack_bar.open = True
        page.update()


def update_thumbnail_carousel(
    images: List[Path], current_index: int, thumbnail_row: ft.Row, on_thumbnail_click: Callable[[int], None]
) -> None:
    """更新底部缩略图轮播。"""

    thumbnail_row.controls.clear()

    total_images = len(images)
    visible_count = 7

    if total_images <= visible_count:
        start_idx = 0
        end_idx = total_images
    else:
        half_visible = visible_count // 2
        start_idx = max(0, current_index - half_visible)
        end_idx = min(total_images, start_idx + visible_count)

        if end_idx == total_images:
            start_idx = max(0, total_images - visible_count)

    for idx in range(start_idx, end_idx):
        image_path = images[idx]
        try:
            thumbnail = image_service.create_thumbnail_data_uri(image_path, 80)
        except Exception as exc:
            logger.error("生成预览缩略图失败: {}，错误: {}", image_path, exc)
            continue

        if not thumbnail:
            continue

        is_current = idx == current_index
        border = ft.Border(
            left=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
            right=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
            top=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
            bottom=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
        )

        thumb_container = ft.Container(
            content=ft.Image(
                src=thumbnail,
                width=80,
                height=80,
                fit=ft.BoxFit.COVER if hasattr(ft, "BoxFit") else "cover",
            ),
            border=border,
            border_radius=5,
            on_click=lambda e, i=idx: on_thumbnail_click(i),
            ink=True,
        )
        thumbnail_row.controls.append(thumb_container)


def handle_keyboard_event(
    key: str,
    preview_open: bool,
    show_previous: Callable[[], None],
    show_next: Callable[[], None],
    close: Callable[[], None],
    show_first: Callable[[], None],
    show_last: Callable[[], None],
) -> None:
    """处理预览相关的键盘事件。"""

    if not preview_open:
        return

    if key == "Arrow Left":
        show_previous()
    elif key == "Arrow Right":
        show_next()
    elif key == "Escape":
        close()
    elif key == "Home":
        show_first()
    elif key == "End":
        show_last()
    elif key == "Space":
        # 空格键等价于下一张
        show_next()