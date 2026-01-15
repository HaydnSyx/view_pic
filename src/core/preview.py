"""预览与缩略图轮播核心模块。"""

from __future__ import annotations
import time
import threading

from pathlib import Path
from typing import Callable, List

import flet as ft
from loguru import logger

from collections import OrderedDict

from src.services import image_service
from src.services.thumbnail_cache import get_thumbnail_cache
from src.config import settings

# 预览图片 data URI 简单缓存，提升大图和相邻图片加载性能
_PREVIEW_CACHE: "OrderedDict[Path, str]" = OrderedDict()
_MAX_CACHE_SIZE: int = 10


def _get_image_data_uri(image_path: Path, use_jpeg: bool = True, max_size: tuple[int, int] | None = None) -> str:
    """获取图片 data URI，带内存缓存。
    
    Args:
        image_path: 图片路径
        use_jpeg: 是否使用JPEG格式（更快），默认True
        max_size: 最大尺寸，默认None不缩放
    """
    start_time = time.perf_counter()

    if image_path in _PREVIEW_CACHE:
        # LRU：命中时移动到队尾
        _PREVIEW_CACHE.move_to_end(image_path)
        elapsed = (time.perf_counter() - start_time) * 1000
        logger.debug("获取图片data URI (缓存命中): {} 耗时: {:.2f}ms", image_path.name, elapsed)
        return _PREVIEW_CACHE[image_path]

    cache_check_time = time.perf_counter()
    data_uri = image_service.load_image_data_uri(image_path, use_jpeg=use_jpeg, max_size=max_size)
    load_time = (time.perf_counter() - cache_check_time) * 1000

    _PREVIEW_CACHE[image_path] = data_uri
    if len(_PREVIEW_CACHE) > _MAX_CACHE_SIZE:
        # 移除最早使用的条目
        _PREVIEW_CACHE.popitem(last=False)

    total_elapsed = (time.perf_counter() - start_time) * 1000
    logger.info("获取图片data URI (加载): {} 耗时: {:.2f}ms (加载: {:.2f}ms)", 
                image_path.name, total_elapsed, load_time)
    return data_uri


def _preload_neighbor_images_async(images: List[Path], current_index: int) -> None:
    """异步预加载当前图片的相邻图片，不阻塞主流程。"""
    def _preload():
        start_time = time.perf_counter()
        preloaded_count = 0
        for offset in (-1, 1):
            idx = current_index + offset
            if 0 <= idx < len(images):
                path = images[idx]
                try:
                    _get_image_data_uri(
                        path,
                        use_jpeg=settings.PREVIEW_USE_JPEG,
                        max_size=settings.PREVIEW_MAX_SIZE
                    )
                    preloaded_count += 1
                except Exception as exc:
                    logger.error("预加载相邻图片失败: {}，错误: {}", path, exc)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        if preloaded_count > 0:
            logger.debug("异步预加载相邻图片完成: {} 张, 耗时: {:.2f}ms", preloaded_count, elapsed)
    
    # 在后台线程中执行预加载
    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()


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
    """显示大图预览并更新缩略图轮播（优化版：减少page.update调用）。
    
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
    total_start_time = time.perf_counter()

    if not (0 <= current_index < len(images)):
        return

    image_path = images[current_index]
    logger.info("开始预览图片: {} (索引: {})", image_path.name, current_index)

    try:
        # 1. 加载主图（这是关键路径，需要同步完成）
        step_start = time.perf_counter()
        preview_image.src = _get_image_data_uri(
            image_path, 
            use_jpeg=settings.PREVIEW_USE_JPEG,
            max_size=settings.PREVIEW_MAX_SIZE
        )
        preview_image.visible = True
        if loading_indicator:
            loading_indicator.visible = False
        elapsed = (time.perf_counter() - step_start) * 1000
        logger.debug("加载主图: {:.2f}ms", elapsed)

        # 2. 更新位置指示器
        step_start = time.perf_counter()
        assert isinstance(position_indicator.content, ft.Text)
        position_indicator.content.value = f"{current_index + 1} / {len(images)}"
        elapsed = (time.perf_counter() - step_start) * 1000
        logger.debug("更新位置指示器: {:.2f}ms", elapsed)

        # 3. 更新底部缩略图轮播（使用缓存优化）
        step_start = time.perf_counter()
        update_thumbnail_carousel_fast(images, current_index, thumbnail_row, on_thumbnail_click)
        elapsed = (time.perf_counter() - step_start) * 1000
        logger.debug("更新缩略图轮播: {:.2f}ms", elapsed)

        # 4. 调整预览对话框大小
        step_start = time.perf_counter()
        if isinstance(preview_dialog.content, ft.Container):
            preview_dialog.content.width = page.window.width
            preview_dialog.content.height = page.window.height
        preview_dialog.open = True
        elapsed = (time.perf_counter() - step_start) * 1000
        logger.debug("调整预览对话框: {:.2f}ms", elapsed)

        # 5. 只调用一次 page.update()（关键优化！）
        step_start = time.perf_counter()
        page.update()
        elapsed = (time.perf_counter() - step_start) * 1000
        logger.info("page.update(): {:.2f}ms", elapsed)
        
        # 6. 异步预加载相邻图片（不阻塞）
        _preload_neighbor_images_async(images, current_index)
        
        total_elapsed = (time.perf_counter() - total_start_time) * 1000
        logger.info("预览图片完成: {} 总耗时: {:.2f}ms", image_path.name, total_elapsed)
        
    except Exception as exc:  # 保底异常处理
        total_elapsed = (time.perf_counter() - total_start_time) * 1000
        logger.exception("预览图片失败: {} 耗时: {:.2f}ms", image_path, total_elapsed)
        page.snack_bar = ft.SnackBar(
            content=ft.Text(f"无法预览图片: {exc}"),
            bgcolor=ft.Colors.RED_400,
        )
        page.snack_bar.open = True
        page.update()


def update_thumbnail_carousel_fast(
    images: List[Path], current_index: int, thumbnail_row: ft.Row, on_thumbnail_click: Callable[[int], None]
) -> None:
    """更新底部缩略图轮播（优化版：复用缩略图缓存）。"""
    start_time = time.perf_counter()
    
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

    # 获取缩略图缓存
    cache = get_thumbnail_cache()
    thumbnails_generated = 0
    cache_hits = 0
    
    for idx in range(start_idx, end_idx):
        image_path = images[idx]
        try:
            # 优先从缓存获取缩略图
            thumbnail = cache.get(image_path)
            if thumbnail:
                cache_hits += 1
            else:
                # 缓存未命中，生成新的缩略图
                thumbnail = image_service.create_thumbnail_data_uri(image_path, 80)
                if thumbnail:
                    cache.put(image_path, thumbnail)
        except Exception as exc:
            logger.error("生成预览缩略图失败: {}，错误: {}", image_path, exc)
            continue

        if not thumbnail:
            continue

        thumbnails_generated += 1
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
    
    elapsed = (time.perf_counter() - start_time) * 1000
    logger.info("更新缩略图轮播: {} 张 (缓存命中: {}), 耗时: {:.2f}ms", 
                thumbnails_generated, cache_hits, elapsed)


def update_thumbnail_carousel(
    images: List[Path], current_index: int, thumbnail_row: ft.Row, on_thumbnail_click: Callable[[int], None]
) -> None:
    """更新底部缩略图轮播（兼容旧接口）。"""
    update_thumbnail_carousel_fast(images, current_index, thumbnail_row, on_thumbnail_click)


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