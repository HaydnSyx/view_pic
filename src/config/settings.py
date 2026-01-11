"""全局配置与常量定义。"""

from pathlib import Path

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".gif")

# 路径配置
VOLUMES_PATH: Path = Path("/Volumes")
HOME_PATH: Path = Path.home()

# 设备扫描时间间隔（秒）
DEVICE_SCAN_INTERVAL: int = 3

# UI 相关常量
WINDOW_WIDTH: int = 1200
WINDOW_HEIGHT: int = 800
WINDOW_MIN_WIDTH: int = 900
WINDOW_MIN_HEIGHT: int = 600

LEFT_PANEL_WIDTH: int = 280
GRID_PADDING: int = 60
GRID_THUMBNAIL_SIZE: int = 150
