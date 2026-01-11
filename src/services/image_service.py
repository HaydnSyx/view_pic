"""图片相关服务：扫描、缩略图生成、原图加载等。"""

from pathlib import Path
from typing import List, Optional

import base64
import io

from loguru import logger
from PIL import Image


def list_images_in_folder(folder: Path, supported_formats: tuple[str, ...]) -> List[Path]:
    """扫描文件夹下所有符合扩展名的图片，按文件名排序返回。"""
    images: List[Path] = []
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in supported_formats:
            images.append(file)
    images.sort(key=lambda x: x.name)
    return images


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
