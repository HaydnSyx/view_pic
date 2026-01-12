"""缩略图缓存管理：使用FIFO队列实现先进先出缓存。"""

from collections import OrderedDict
from pathlib import Path
from typing import Optional
from loguru import logger

from src.config import settings


class ThumbnailCache:
    """缩略图FIFO缓存管理器。
    
    使用有序字典实现固定容量的先进先出队列。
    当缓存满时，自动移除最早加入的条目。
    """

    def __init__(self, max_size: int = 200):
        """初始化缓存。
        
        Args:
            max_size: 缓存最大容量（默认200）
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, str] = OrderedDict()
        logger.info("ThumbnailCache 初始化, 容量: {}", max_size)

    def get(self, image_path: Path) -> Optional[str]:
        """从缓存中获取缩略图。
        
        Args:
            image_path: 图片路径
            
        Returns:
            Optional[str]: 缩略图 data URI，如果不存在则返回 None
        """
        key = str(image_path.resolve())
        
        if key in self._cache:
            logger.debug("缓存命中: {}", image_path.name)
            return self._cache[key]
        else:
            logger.debug("缓存未命中: {}", image_path.name)
            return None

    def put(self, image_path: Path, data_uri: str) -> None:
        """将缩略图放入缓存。
        
        如果缓存已满，移除最早的条目（FIFO）。
        
        Args:
            image_path: 图片路径
            data_uri: 缩略图 data URI
        """
        key = str(image_path.resolve())
        
        # 如果已存在，先删除（这样可以更新顺序）
        if key in self._cache:
            del self._cache[key]
        
        # 如果缓存已满，移除最早的条目
        if len(self._cache) >= self.max_size:
            # OrderedDict.popitem(last=False) 移除最早的条目（FIFO）
            removed_key, _ = self._cache.popitem(last=False)
            logger.debug(
                "缓存已满，移除最早条目: {} (当前容量: {}/{})",
                Path(removed_key).name,
                len(self._cache),
                self.max_size
            )
        
        # 添加新条目
        self._cache[key] = data_uri
        logger.debug(
            "缓存新增: {} (当前容量: {}/{})",
            image_path.name,
            len(self._cache),
            self.max_size
        )

    def clear(self) -> None:
        """清空缓存。"""
        count = len(self._cache)
        self._cache.clear()
        logger.info("缓存已清空, 清除 {} 条记录", count)

    def size(self) -> int:
        """获取当前缓存条目数量。"""
        return len(self._cache)

    def contains(self, image_path: Path) -> bool:
        """检查缓存中是否存在指定图片。
        
        Args:
            image_path: 图片路径
            
        Returns:
            bool: 是否存在
        """
        key = str(image_path.resolve())
        return key in self._cache


# 全局单例缓存实例
_global_cache: Optional[ThumbnailCache] = None


def get_thumbnail_cache() -> ThumbnailCache:
    """获取全局缩略图缓存实例。"""
    global _global_cache
    if _global_cache is None:
        _global_cache = ThumbnailCache(max_size=settings.THUMBNAIL_CACHE_SIZE)
    return _global_cache
