"""图片浏览核心模块：构建右侧图片网格/列表视图。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import flet as ft
from loguru import logger

from src.config import settings
from src.services import image_service
from src.utils.fs_utils import format_file_size


def build_image_views(
    images: List[Path],
    view_mode: str,
    current_folder: Path | None,
    window_width: float,
    on_preview: Callable[[int], None],
) -> List[ft.Control]:
    """根据当前视图模式构建图片区域控件列表。"""

    controls: List[ft.Control] = []

    if not images:
        controls.append(_build_empty_placeholder(current_folder))
        return controls

    if view_mode == "grid":
        controls.append(_build_grid_view(images, window_width, on_preview))
    else:
        controls.extend(_build_list_view(images, on_preview))

    return controls


def _build_empty_placeholder(current_folder: Path | None) -> ft.Control:
    """构建空文件夹时的占位视图。"""

    folder_name = current_folder.name if current_folder else ""

    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.icons.Icons.IMAGE_NOT_SUPPORTED,
                    size=100,
                    color="#CCCCCC",
                ),
                ft.Text(
                    "此文件夹中没有图片",
                    color="#999999",
                    size=16,
                ),
                ft.Text(
                    f"当前文件夹: {folder_name}",
                    color="#CCCCCC",
                    size=12,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.Alignment(0, 0),
        expand=True,
    )


def _build_grid_view(
    images: List[Path],
    window_width: float,
    on_preview: Callable[[int], None],
) -> ft.GridView:
    """构建网格视图。"""

    container_width = (
        window_width - settings.LEFT_PANEL_WIDTH - settings.GRID_PADDING
    )
    thumbnail_size = settings.GRID_THUMBNAIL_SIZE
    cols = max(2, int(container_width // (thumbnail_size + 20)))

    grid = ft.GridView(
        expand=True,
        runs_count=cols,
        max_extent=thumbnail_size + 20,
        child_aspect_ratio=0.8,
        spacing=15,
        run_spacing=15,
    )

    for idx, image_path in enumerate(images[:100]):  # 虚拟滚动：先只加载前100张
        try:
            thumbnail = image_service.create_thumbnail_data_uri(
                image_path, thumbnail_size
            )
            if not thumbnail:
                continue

            img_container = ft.Container(
                content=ft.Column(
                    [
                        ft.Image(
                            src=thumbnail,
                            width=thumbnail_size,
                            height=thumbnail_size,
                            fit=ft.BoxFit.COVER
                            if hasattr(ft, "BoxFit")
                            else "cover",
                            border_radius=8,
                        ),
                        ft.Text(
                            image_path.name,
                            size=12,
                            max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            width=thumbnail_size,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=5,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                on_click=lambda e, i=idx: on_preview(i),
                ink=True,
                border_radius=8,
                padding=5,
                bgcolor="transparent",
                on_hover=_on_image_hover,
            )
            grid.controls.append(img_container)
        except Exception as exc:
            # 缩略图生成失败时略过当前图片，避免打断整体渲染
            logger.error("缩略图渲染失败，文件: {}，错误: {}", image_path, exc)
            continue

    return grid


def _build_list_view(
    images: List[Path], on_preview: Callable[[int], None]
) -> List[ft.Control]:
    """构建列表视图。"""

    items: List[ft.Control] = []

    for idx, image_path in enumerate(images[:100]):  # 虚拟滚动
        try:
            stat = image_path.stat()
            size_text = format_file_size(stat.st_size)

            item = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.icons.Icons.IMAGE,
                            size=30,
                            color="#1976D2",
                        ),
                        ft.Column(
                            [
                                ft.Text(
                                    image_path.name,
                                    size=14,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    size_text,
                                    size=12,
                                    color="#666666",
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=15,
                ),
                padding=15,
                border=ft.Border(
                    bottom=ft.BorderSide(1, "#E0E0E0"),
                ),
                ink=True,
                on_click=lambda e, i=idx: on_preview(i),
                bgcolor="transparent",
                on_hover=_on_image_hover,
            )
            items.append(item)
        except Exception as exc:
            # 单个文件读取异常时跳过，避免影响整体列表
            logger.error("读取图片信息失败: {}，错误: {}", image_path, exc)
            continue

    return items


def _on_image_hover(e: ft.HoverEvent) -> None:
    """图片悬停效果。"""

    e.control.bgcolor = "#F5F5F5" if e.data == "true" else "transparent"
    e.control.update()
