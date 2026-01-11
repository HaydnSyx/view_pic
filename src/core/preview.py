"""预览与缩略图轮播核心模块。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import flet as ft
from loguru import logger

from src.services import image_service


def show_preview(
    images: List[Path],
    current_index: int,
    preview_image: ft.Image,
    position_indicator: ft.Container,
    thumbnail_row: ft.Row,
    preview_dialog: ft.AlertDialog,
    page: ft.Page,
    on_thumbnail_click: Callable[[int], None],
) -> None:
    """显示大图预览并更新缩略图轮播。"""

    if not (0 <= current_index < len(images)):
        return

    image_path = images[current_index]

    try:
        # 加载图片并转换为 data URI
        preview_image.src = image_service.load_image_data_uri(image_path)

        # 更新位置指示器
        assert isinstance(position_indicator.content, ft.Text)
        position_indicator.content.value = f"{current_index + 1} / {len(images)}"

        # 更新底部缩略图轮播
        update_thumbnail_carousel(images, current_index, thumbnail_row, on_thumbnail_click)

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
