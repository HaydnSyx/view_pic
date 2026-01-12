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


def build_grid_with_placeholders(
    images: List[Path],
    window_width: float,
    on_preview: Callable[[int], None],
) -> ft.GridView:
    """构建带占位符的网格视图（用于异步加载）。
    
    初始渲染时显示占位符，后续通过外部调用更新为真实缩略图。
    
    Args:
        images: 图片路径列表
        window_width: 窗口宽度
        on_preview: 预览回调
        
    Returns:
        ft.GridView: 网格视图控件，每个单元格带有 data 字段存储索引
    """
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

    # 创建占位符容器（最多100个）
    for idx, image_path in enumerate(images[:100]):
        placeholder_container = _create_thumbnail_placeholder(
            index=idx,
            image_path=image_path,
            thumbnail_size=thumbnail_size,
            on_preview=on_preview,
        )
        grid.controls.append(placeholder_container)

    logger.debug(
        "创建带占位符的网格视图, 共 {} 个占位符",
        len(grid.controls)
    )

    return grid


def _create_thumbnail_placeholder(
    index: int,
    image_path: Path,
    thumbnail_size: int,
    on_preview: Callable[[int], None],
) -> ft.Container:
    """创建单个缩略图占位符。
    
    Args:
        index: 图片索引
        image_path: 图片路径
        thumbnail_size: 缩略图尺寸
        on_preview: 预览回调
        
    Returns:
        ft.Container: 占位符容器，带有 data 字段存储 {"index": idx}
    """
    return ft.Container(
        content=ft.Column(
            [
                # 占位图标
                ft.Container(
                    content=ft.Icon(
                        ft.icons.Icons.IMAGE,
                        size=60,
                        color="#CCCCCC",
                    ),
                    width=thumbnail_size,
                    height=thumbnail_size,
                    bgcolor="#F5F5F5",
                    border_radius=8,
                    alignment=ft.Alignment(0, 0),
                ),
                # 文件名
                ft.Text(
                    image_path.name,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    width=thumbnail_size,
                    text_align=ft.TextAlign.CENTER,
                    color="#999999",
                ),
            ],
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        on_click=lambda e, i=index: on_preview(i),
        ink=True,
        border_radius=8,
        padding=5,
        bgcolor="transparent",
        on_hover=_on_image_hover,
        data={"index": index, "image_path": str(image_path)},  # 存储索引信息
    )


def update_thumbnail_in_grid(
    grid: ft.GridView,
    index: int,
    data_uri: str,
    image_path: Path,
    thumbnail_size: int,
    on_preview: Callable[[int], None],
) -> bool:
    """更新网格中指定索引的缩略图。
    
    将占位符替换为真实缩略图。
    
    Args:
        grid: 网格视图控件
        index: 要更新的图片索引
        data_uri: 缩略图 base64 data URI
        image_path: 图片路径
        thumbnail_size: 缩略图尺寸
        on_preview: 预览回调
        
    Returns:
        bool: 是否成功更新
    """
    if index >= len(grid.controls):
        logger.warning(
            "索引超出范围: index={}, grid.controls.length={}",
            index,
            len(grid.controls)
        )
        return False

    container = grid.controls[index]
    
    # 验证是否为正确的容器
    if not isinstance(container, ft.Container):
        logger.error("索引 {} 的控件不是 Container", index)
        return False

    # 更新内容为真实缩略图
    container.content = ft.Column(
        [
            ft.Image(
                src=data_uri,
                width=thumbnail_size,
                height=thumbnail_size,
                fit=ft.BoxFit.COVER if hasattr(ft, "BoxFit") else "cover",
                border_radius=8,
            ),
            ft.Text(
                image_path.name,
                size=12,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                width=thumbnail_size,
                text_align=ft.TextAlign.CENTER,
                color="#333333",  # 恢复正常颜色
            ),
        ],
        spacing=5,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    return True


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
