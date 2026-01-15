"""图片相关服务：扫描、缩略图生成、原图加载等。"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import base64
import io

from loguru import logger
from PIL import Image


@dataclass
class ImageBatchResult:
    """图片批次加载结果"""

    images: List[Path]  # 本批次图片列表
    total_count: int  # 当前已扫描总数（估算值）
    has_more: bool  # 是否可能还有更多图片
    offset: int  # 下一批的起始偏移量


def list_images_in_folder(folder: Path, supported_formats: tuple[str, ...]) -> List[Path]:
    """扫描文件夹下所有符合扩展名的图片，按文件名排序返回。
    
    注意：此方法保留以保证向后兼容，新代码应使用 list_images_in_folder_batch
    """
    images: List[Path] = []
    for file in folder.iterdir():
        # 过滤隐藏文件（以 . 开头）
        if file.name.startswith('.'):
            continue
        
        if file.is_file() and file.suffix.lower() in supported_formats:
            images.append(file)
    
    images.sort(key=lambda x: x.name)
    return images


def list_images_in_folder_batch(
    folder: Path,
    supported_formats: tuple[str, ...],
    offset: int = 0,
    limit: int = 500,
) -> ImageBatchResult:
    """分页扫描文件夹下的图片（方案A：快速首屏）。

    Args:
        folder: 文件夹路径
        supported_formats: 支持的图片格式
        offset: 跳过前 N 个符合条件的文件
        limit: 本次最多返回数量

    Returns:
        ImageBatchResult: 包含图片列表、总数等信息
    """
    images: List[Path] = []
    skipped = 0
    collected = 0
    stopped_early = False

    try:
        # 遍历文件夹，收集符合条件的图片
        for file in folder.iterdir():
            # 过滤隐藏文件（以 . 开头）
            if file.name.startswith('.'):
                continue
            
            if not file.is_file() or file.suffix.lower() not in supported_formats:
                continue

            # 跳过前 offset 个
            if skipped < offset:
                skipped += 1
                continue

            # 收集当前文件
            images.append(file)
            collected += 1

            # 达到 limit 后停止扫描（关键优化）
            if collected >= limit:
                stopped_early = True
                break

        # 按文件名排序
        images.sort(key=lambda x: x.name.lower())

        # 计算结果
        current_total = offset + collected
        has_more = stopped_early  # 如果提前停止，说明可能还有更多

        logger.info(
            "扫描文件夹: {}, offset={}, limit={}, 得到 {} 张, "
            "当前总数={}, has_more={}",
            folder.name,
            offset,
            limit,
            collected,
            current_total,
            has_more,
        )

        return ImageBatchResult(
            images=images,
            total_count=current_total,
            has_more=has_more,
            offset=offset + collected,
        )

    except Exception as exc:
        logger.exception("扫描文件夹失败: {}", folder)
        # 返回空结果
        return ImageBatchResult(
            images=[],
            total_count=0,
            has_more=False,
            offset=offset,
        )


def _encode_image_to_data_uri(img: Image.Image, use_jpeg: bool = False, quality: int = 85) -> str:
    """将 Pillow 图片对象编码为 data URI 字符串。
    
    Args:
        img: Pillow图片对象
        use_jpeg: 是否使用JPEG格式（更快，但质量略低）
        quality: JPEG质量（1-100，仅当use_jpeg=True时有效）
    """
    start_time = time.perf_counter()
    
    # 获取图片尺寸用于日志
    img_size = f"{img.width}x{img.height}"
    
    step_start = time.perf_counter()
    buffer = io.BytesIO()
    if use_jpeg and img.mode in ("RGB", "RGBA"):
        # 如果是RGBA，需要转换为RGB
        if img.mode == "RGBA":
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = rgb_img
        # 性能优化：移除 optimize=True
        # optimize=True 会做额外的优化pass来减小文件体积，但不影响图像质量
        # quality 参数才是决定图像质量的关键
        img.save(buffer, format="JPEG", quality=quality)
        mime_type = "jpeg"
    else:
        # PNG 也移除 optimize，加快编码
        img.save(buffer, format="PNG")
        mime_type = "png"
    save_elapsed = (time.perf_counter() - step_start) * 1000
    
    step_start = time.perf_counter()
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    encode_elapsed = (time.perf_counter() - step_start) * 1000
    
    total_elapsed = (time.perf_counter() - start_time) * 1000
    buffer_size_kb = len(buffer.getvalue()) / 1024
    
    if total_elapsed > 50:  # 只记录耗时超过50ms的编码操作
        logger.info("编码图片为data URI: 尺寸={}, 格式={}, 大小={:.1f}KB, 总耗时: {:.2f}ms (保存: {:.2f}ms, base64编码: {:.2f}ms)", 
                     img_size, mime_type.upper(), buffer_size_kb, total_elapsed, save_elapsed, encode_elapsed)
    
    return f"data:image/{mime_type};base64,{img_base64}"


def create_thumbnail_data_uri(image_path: Path, size: int = 150) -> Optional[str]:
    """创建缩略图并返回 base64 data URI。"""
    try:
        img = Image.open(image_path)
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return _encode_image_to_data_uri(img)
    except Exception as exc:  # 保底异常处理
        logger.exception("生成缩略图失败: {}", image_path)
        return None


def load_image_data_uri(image_path: Path, use_jpeg: bool = True, max_size: tuple[int, int] | None = None) -> str:
    """加载原图并转换为 data URI 字符串。
    
    Args:
        image_path: 图片路径
        use_jpeg: 是否使用JPEG格式（更快，但质量略低），默认True
        max_size: 最大尺寸元组(width, height)，如果图片超过此尺寸会缩放，默认None不缩放
    """
    total_start = time.perf_counter()
    
    step_start = time.perf_counter()
    img = Image.open(image_path)
    open_elapsed = (time.perf_counter() - step_start) * 1000
    original_size = img.size
    
    # 如果指定了最大尺寸，进行缩放
    if max_size:
        step_start = time.perf_counter()
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        resize_elapsed = (time.perf_counter() - step_start) * 1000
        logger.debug("缩放图片: {} {} -> {} 耗时: {:.2f}ms", 
                    image_path.name, original_size, img.size, resize_elapsed)
    
    logger.debug("打开图片文件: {} 尺寸: {} 耗时: {:.2f}ms", 
                image_path.name, img.size, open_elapsed)
    
    step_start = time.perf_counter()
    data_uri = _encode_image_to_data_uri(img, use_jpeg=use_jpeg)
    encode_elapsed = (time.perf_counter() - step_start) * 1000
    
    total_elapsed = (time.perf_counter() - total_start) * 1000
    logger.info("加载图片data URI: {} 总耗时: {:.2f}ms (打开: {:.2f}ms, 编码: {:.2f}ms)", 
                image_path.name, total_elapsed, open_elapsed, encode_elapsed)
    return data_uri
