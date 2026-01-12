"""异步缩略图生成服务：使用线程池避免阻塞主线程。"""

import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Callable, List, Optional, Dict
from loguru import logger

from src.services import image_service
from src.config import settings


class AsyncThumbnailService:
    """异步缩略图生成服务
    
    使用线程池并发生成缩略图，避免阻塞主线程，
    每生成一张就通过回调通知更新UI。
    """

    def __init__(self, max_workers: int = 4):
        """初始化异步缩略图服务
        
        Args:
            max_workers: 线程池大小（建议 2-8）
        """
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="thumbnail-worker"
        )
        self.current_task_id: Optional[str] = None
        self.futures: List[Future] = []
        
        logger.info("AsyncThumbnailService 初始化, 线程池大小: {}", max_workers)

    def generate_thumbnails_async(
        self,
        images: List[Path],
        thumbnail_size: int,
        on_single_complete: Callable[[int, str, Path], None],
        on_all_complete: Callable[[], None],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """异步生成缩略图列表
        
        Args:
            images: 图片路径列表
            thumbnail_size: 缩略图尺寸
            on_single_complete: 单张完成回调 (index, data_uri, image_path)
            on_all_complete: 全部完成回调
            on_progress: 进度回调 (completed_count, total_count)
            
        Returns:
            str: 任务唯一ID
        """
        task_id = str(uuid.uuid4())
        self.current_task_id = task_id
        self.futures.clear()

        total_count = len(images)
        completed_count = 0

        logger.info(
            "开始异步生成缩略图任务: {}, 共 {} 张图片",
            task_id[:8],
            total_count
        )

        def process_single_image(index: int, image_path: Path) -> Optional[tuple]:
            """处理单张图片（在工作线程中执行）"""
            # 检查任务是否已取消
            if self.current_task_id != task_id:
                logger.debug("任务已取消，跳过图片: {}", image_path.name)
                return None

            try:
                # 生成缩略图
                data_uri = image_service.create_thumbnail_data_uri(
                    image_path, thumbnail_size
                )
                
                if data_uri:
                    logger.debug(
                        "缩略图生成成功 [{}/{}]: {}",
                        index + 1,
                        total_count,
                        image_path.name
                    )
                    return (index, data_uri, image_path)
                else:
                    logger.warning("缩略图生成失败: {}", image_path)
                    return None
                    
            except Exception as exc:
                logger.error("缩略图生成异常: {}, 错误: {}", image_path, exc)
                return None

        def on_future_done(future: Future):
            """单个任务完成的回调（在工作线程中调用）"""
            nonlocal completed_count
            
            try:
                result = future.result()
                if result and self.current_task_id == task_id:
                    index, data_uri, image_path = result
                    # 调用外部回调（需要线程安全处理）
                    on_single_complete(index, data_uri, image_path)
                    
                completed_count += 1
                
                # 更新进度
                if on_progress and self.current_task_id == task_id:
                    on_progress(completed_count, total_count)
                    
            except Exception as exc:
                logger.exception("处理缩略图完成回调时出错: {}", exc)

        # 提交所有任务到线程池
        for idx, img_path in enumerate(images):
            future = self.executor.submit(process_single_image, idx, img_path)
            future.add_done_callback(on_future_done)
            self.futures.append(future)

        # 创建一个监控任务，等待所有缩略图完成
        def wait_all_complete():
            """等待所有任务完成（在单独的线程中）"""
            try:
                for future in self.futures:
                    future.result()  # 阻塞等待
                    
                # 所有任务完成
                if self.current_task_id == task_id:
                    logger.info(
                        "缩略图生成任务完成: {}, 共处理 {} 张",
                        task_id[:8],
                        total_count
                    )
                    on_all_complete()
            except Exception as exc:
                logger.exception("等待缩略图任务完成时出错: {}", exc)

        # 提交监控任务
        self.executor.submit(wait_all_complete)

        return task_id

    def cancel_current_task(self) -> None:
        """取消当前任务
        
        注意：已提交到线程池的任务无法真正中断，
        但会通过 task_id 判断跳过后续处理。
        """
        if self.current_task_id:
            logger.info("取消缩略图生成任务: {}", self.current_task_id[:8])
            self.current_task_id = None
        else:
            logger.debug("没有活动的缩略图生成任务")

    def shutdown(self, wait: bool = True) -> None:
        """关闭线程池
        
        Args:
            wait: 是否等待所有任务完成
        """
        logger.info("关闭 AsyncThumbnailService, wait={}", wait)
        self.executor.shutdown(wait=wait)


# 全局单例实例（可选，也可以在 ImageViewerApp 中创建）
_global_service: Optional[AsyncThumbnailService] = None


def get_async_thumbnail_service() -> AsyncThumbnailService:
    """获取全局异步缩略图服务实例"""
    global _global_service
    if _global_service is None:
        _global_service = AsyncThumbnailService(
            max_workers=settings.THUMBNAIL_WORKER_THREADS
        )
    return _global_service
