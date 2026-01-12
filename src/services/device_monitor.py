"""设备监听服务：使用 watchdog 监听 /Volumes 目录变化。

使用文件系统监听代替轮询，实现事件驱动的设备热插拔检测。
"""

from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from loguru import logger


class DeviceEventHandler(FileSystemEventHandler):
    """设备变化事件处理器。
    
    监听 /Volumes 目录下的文件夹创建和删除事件，
    自动过滤掉系统盘（Macintosh HD）。
    """

    def __init__(self, on_device_change: Callable[[], None]):
        """初始化事件处理器。
        
        Args:
            on_device_change: 设备列表变化时的回调函数
        """
        super().__init__()
        self.on_device_change = on_device_change
        self.system_volumes = {"Macintosh HD", ".Spotlight-V100", ".Trashes"}
        logger.debug("DeviceEventHandler 已初始化，系统卷过滤列表: {}", self.system_volumes)

    def on_created(self, event: FileSystemEvent) -> None:
        """处理文件夹创建事件（设备挂载）。
        
        Args:
            event: 文件系统事件
        """
        logger.debug(
            "[watchdog] 检测到创建事件: path={}, is_directory={}",
            event.src_path,
            event.is_directory
        )
        
        if not event.is_directory:
            logger.debug("[watchdog] 跳过非目录事件: {}", event.src_path)
            return
        
        device_name = Path(event.src_path).name
        
        # 过滤系统卷
        if device_name in self.system_volumes:
            logger.debug("[watchdog] 过滤系统卷: {}", device_name)
            return
        
        # 过滤隐藏文件
        if device_name.startswith('.'):
            logger.debug("[watchdog] 过滤隐藏目录: {}", device_name)
            return
        
        logger.info("✅ 检测到设备挂载: {} (路径: {})", device_name, event.src_path)
        
        try:
            logger.debug("[watchdog] 触发设备列表更新回调...")
            self.on_device_change()
            logger.debug("[watchdog] 设备列表更新回调执行完成")
        except Exception as exc:
            logger.exception("[watchdog] 执行设备变化回调失败: {}", exc)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """处理文件夹删除事件（设备卸载）。
        
        Args:
            event: 文件系统事件
        """
        logger.debug(
            "[watchdog] 检测到删除事件: path={}, is_directory={}",
            event.src_path,
            event.is_directory
        )
        
        if not event.is_directory:
            logger.debug("[watchdog] 跳过非目录事件: {}", event.src_path)
            return
        
        device_name = Path(event.src_path).name
        
        # 过滤系统卷
        if device_name in self.system_volumes:
            logger.debug("[watchdog] 过滤系统卷: {}", device_name)
            return
        
        # 过滤隐藏文件
        if device_name.startswith('.'):
            logger.debug("[watchdog] 过滤隐藏目录: {}", device_name)
            return
        
        logger.info("❌ 检测到设备卸载: {} (路径: {})", device_name, event.src_path)
        
        try:
            logger.debug("[watchdog] 触发设备列表更新回调...")
            self.on_device_change()
            logger.debug("[watchdog] 设备列表更新回调执行完成")
        except Exception as exc:
            logger.exception("[watchdog] 执行设备变化回调失败: {}", exc)
    
    def on_modified(self, event: FileSystemEvent) -> None:
        """处理文件夹修改事件。
        
        有些设备挂载时会触发 modified 事件而不是 created 事件。
        
        Args:
            event: 文件系统事件
        """
        logger.debug(
            "[watchdog] 检测到修改事件: path={}, is_directory={}",
            event.src_path,
            event.is_directory
        )
        # 修改事件不处理，避免频繁触发
    
    def on_moved(self, event: FileSystemEvent) -> None:
        """处理文件夹移动事件。
        
        Args:
            event: 文件系统事件
        """
        logger.debug(
            "[watchdog] 检测到移动事件: path={}, is_directory={}",
            event.src_path,
            event.is_directory
        )
        # 移动事件可能代表重命名，暂不处理


class DeviceMonitor:
    """设备监听管理器。
    
    使用 watchdog 库监听 /Volumes 目录变化，
    提供启动、停止、状态查询等功能。
    """

    def __init__(self, volumes_path: Path, on_device_change: Callable[[], None]):
        """初始化设备监听器。
        
        Args:
            volumes_path: 设备挂载路径（通常是 /Volumes）
            on_device_change: 设备列表变化时的回调函数
        """
        self.volumes_path = volumes_path
        self.on_device_change = on_device_change
        self.observer: Optional[Observer] = None
        self.is_running = False
        logger.debug(
            "DeviceMonitor 已初始化, 监听路径: {}",
            self.volumes_path
        )

    def start(self) -> bool:
        """启动设备监听。
        
        Returns:
            bool: 是否成功启动
        """
        logger.debug("尝试启动设备监听器...")
        
        if self.is_running:
            logger.warning("设备监听器已在运行，无需重复启动")
            return False

        if not self.volumes_path.exists():
            logger.error(
                "设备挂载路径不存在: {}, 请检查系统配置",
                self.volumes_path
            )
            return False

        try:
            logger.debug("创建 DeviceEventHandler...")
            # 创建事件处理器
            event_handler = DeviceEventHandler(self.on_device_change)
            
            logger.debug("创建 watchdog Observer...")
            # 创建观察者
            self.observer = Observer()
            self.observer.schedule(
                event_handler,
                str(self.volumes_path),
                recursive=False  # 只监听第一层，不递归子目录
            )
            
            logger.debug("启动 Observer 线程...")
            # 启动观察者
            self.observer.start()
            self.is_running = True
            
            logger.info(
                "🔍 设备监听器已启动, 监听路径: {}, 递归: False",
                self.volumes_path
            )
            logger.info("将实时响应设备插拔事件...")
            return True
            
        except Exception as exc:
            logger.exception("启动设备监听器失败: {}", exc)
            return False

    def stop(self) -> None:
        """停止设备监听。"""
        logger.debug("尝试停止设备监听器...")
        
        if not self.is_running or self.observer is None:
            logger.warning("设备监听器未运行，无需停止")
            return

        try:
            logger.debug("停止 Observer 线程...")
            self.observer.stop()
            
            logger.debug("等待 Observer 线程结束 (最多2秒)...")
            self.observer.join(timeout=2.0)  # 最多等待2秒
            
            self.is_running = False
            logger.info("✅ 设备监听器已停止")
            
        except Exception as exc:
            logger.exception("停止设备监听器失败: {}", exc)

    def is_monitoring(self) -> bool:
        """检查监听器是否正在运行。
        
        Returns:
            bool: 是否正在运行
        """
        return self.is_running and self.observer is not None and self.observer.is_alive()
