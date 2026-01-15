"""全局配置与常量定义。"""

from pathlib import Path

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".gif")

# 路径配置
VOLUMES_PATH: Path = Path("/Volumes")
HOME_PATH: Path = Path.home()

# UI 相关常量
WINDOW_WIDTH: int = 1200
WINDOW_HEIGHT: int = 800
WINDOW_MIN_WIDTH: int = 900
WINDOW_MIN_HEIGHT: int = 600

LEFT_PANEL_WIDTH: int = 280
GRID_PADDING: int = 60
GRID_THUMBNAIL_SIZE: int = 150

# ==================== 性能优化配置 ====================

# 文件扫描配置
INITIAL_IMAGE_LOAD_LIMIT: int = 100  # 初次加载图片数量上限
LOAD_MORE_BATCH_SIZE: int = 50  # "加载更多"每次追加数量

# 缩略图生成配置
THUMBNAIL_WORKER_THREADS: int = 4  # 线程池大小（建议 2-8）
INITIAL_THUMBNAIL_COUNT: int = 50  # 首屏立即生成数量
THUMBNAIL_GENERATION_TIMEOUT: int = 5  # 单张缩略图生成超时（秒）
THUMBNAIL_CACHE_SIZE: int = 200  # 缩略图缓存队列大小（FIFO）

# 渲染配置
ENABLE_PROGRESSIVE_RENDERING: bool = True  # 是否启用渐进式渲染
SHOW_LOADING_INDICATOR: bool = True  # 是否显示加载指示器

# 预览图片配置
PREVIEW_USE_JPEG: bool = True  # 预览大图是否使用JPEG格式（更快，但质量略低）
PREVIEW_JPEG_QUALITY: int = 85  # JPEG质量（1-100，仅当PREVIEW_USE_JPEG=True时有效）
PREVIEW_MAX_SIZE: tuple[int, int] | None = (3840, 2160)  # 预览图片最大尺寸，超过会缩放，None表示不缩放
