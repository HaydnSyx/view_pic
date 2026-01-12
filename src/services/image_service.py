"""图片相关服务：扫描、缩略图生成、原图加载等。"""

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


def _encode_image_to_data_uri(img: Image.Image) -> str:
    """将 Pillow 图片对象编码为 data URI 字符串。"""
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_base64}"


def create_thumbnail_data_uri(image_path: Path, size: int = 150) -> Optional[str]:
    """创建缩略图并返回 base64 data URI。"""
    try:
        img = Image.open(image_path)
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        return _encode_image_to_data_uri(img)
    except Exception as exc:  # 保底异常处理
        logger.exception("生成缩略图失败: {}", image_path)
        return None


def load_image_data_uri(image_path: Path) -> str:
    """加载原图并转换为 data URI 字符串。"""
    img = Image.open(image_path)
    return _encode_image_to_data_uri(img)
