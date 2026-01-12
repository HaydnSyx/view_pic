"""应用入口模块，包含 ImageViewerApp 主类。"""

from pathlib import Path
from typing import List, Set

import flet as ft
from loguru import logger

from src.config import settings
from src.core import file_browser, image_gallery, preview
from src.services import device_service, image_service
from src.services.async_thumbnail_service import AsyncThumbnailService
from src.services.device_monitor import DeviceMonitor


class ImageViewerApp:
    """主应用类"""

    def __init__(self) -> None:
        # 路径与配置
        self.current_folder: Path | None = None
        self.images: List[Path] = []
        self.view_mode: str = "grid"  # "grid" or "list"
        self.current_image_index: int = 0
        self.supported_formats = settings.SUPPORTED_IMAGE_FORMATS
        self.volumes_path: Path = settings.VOLUMES_PATH
        self.home_path: Path = settings.HOME_PATH
        self.device_monitor: DeviceMonitor | None = None  # 设备监听器

        # 预览相关状态
        self.zoom_level: float = 1.0
        self.expanded_folders: Set[Path] = set()  # 存储展开的文件夹路径

        # 分页加载相关状态
        self.current_offset: int = 0  # 当前加载偏移量
        self.has_more_images: bool = False  # 是否还有更多图片
        self.total_images_count: int = 0  # 当前已知总数（估算值）

        # 异步缩略图相关状态
        self.async_thumbnail_service: AsyncThumbnailService | None = None
        self.current_grid: ft.GridView | None = None  # 当前网格视图引用
        self.is_loading_thumbnails: bool = False  # 是否正在加载缩略图
        self.loaded_thumbnail_count: int = 0  # 已加载的缩略图数量
        self._uncached_index_map: dict = {}  # 未缓存图片的索引映射

        # 运行时属性（初始化为 None，create_ui 中赋值）
        self.page: ft.Page | None = None
        self.folder_tree: ft.Column | None = None
        self.device_list: ft.Column | None = None
        self.view_mode_btn: ft.IconButton | None = None
        self.image_display: ft.Column | None = None
        self.image_container: ft.Container | None = None
        self.preview_image: ft.Image | None = None
        self.position_indicator: ft.Container | None = None
        self.thumbnail_row: ft.Row | None = None
        self.preview_dialog: ft.AlertDialog | None = None
        self.load_more_button: ft.Container | None = None  # "加载更多"按钮

    def main(self, page: ft.Page) -> None:
        """Flet 应用入口函数"""
        page.title = "图片查看器"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.spacing = 0
        page.window.width = settings.WINDOW_WIDTH
        page.window.height = settings.WINDOW_HEIGHT
        page.window.min_width = settings.WINDOW_MIN_WIDTH
        page.window.min_height = settings.WINDOW_MIN_HEIGHT

        # 启动时将窗口最大化（非系统级全屏）
        try:
            if hasattr(page.window, "maximized"):
                page.window.maximized = True
        except Exception as exc:
            logger.error("设置窗口最大化失败: {}", exc)

        self.page = page

        logger.info("Initializing ImageViewerApp UI")

        # 初始化异步缩略图服务
        self.async_thumbnail_service = AsyncThumbnailService(
            max_workers=settings.THUMBNAIL_WORKER_THREADS
        )

        # 创建UI组件
        self.create_ui()

        # 启动设备监听
        self.start_device_monitoring()

        # 监听窗口大小变化
        page.on_resized = self.on_window_resize

        # 监听键盘事件
        page.on_keyboard_event = self.on_keyboard_event

    # === UI 构建 ===

    def create_ui(self) -> None:
        """创建UI界面"""
        assert self.page is not None

        # 左侧文件夹树
        self.folder_tree = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=5,
            expand=True,
        )

        # 构建初始文件夹树
        self.build_folder_tree()

        left_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=self.folder_tree,
                        expand=True,
                        padding=10,
                    ),
                ]
            ),
            width=280,
            bgcolor="#FAFAFA",
            border=ft.Border(right=ft.BorderSide(1, "#E0E0E0")),
        )

        # 右侧工具栏
        self.view_mode_btn = ft.IconButton(
            icon=ft.icons.Icons.GRID_VIEW,
            icon_color="#1976D2",
            tooltip="切换视图模式",
            on_click=self.toggle_view_mode,
        )

        # 图片数量统计文本
        self.image_count_text = ft.Text(
            "",
            size=14,
            color="#666666",
            weight=ft.FontWeight.W_400,
        )

        toolbar = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "图片库",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color="#333333",
                    ),
                    ft.Container(width=10),  # 间距
                    self.image_count_text,  # 图片数量
                    ft.Container(expand=True),
                    self.view_mode_btn,
                ]
            ),
            padding=15,
            bgcolor="#FFFFFF",
            border=ft.Border(bottom=ft.BorderSide(1, "#E0E0E0")),
        )

        # 右侧图片展示区域
        self.image_display = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            expand=True,
        )

        # 加载状态指示器
        self.loading_progress_text = ft.Text(
            "正在加载图片... (0/0)",
            size=14,
            color="#FF6F00",
        )

        self.loading_indicator = ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(width=20, height=20, stroke_width=2),
                    self.loading_progress_text,
                    ft.TextButton(
                        "取消",
                        icon=ft.icons.Icons.CANCEL,
                        on_click=self.cancel_loading,
                        style=ft.ButtonStyle(
                            color="#D32F2F",  # 红色
                        ),
                    ),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(left=10, right=10, top=10, bottom=10),
            bgcolor="#FFF3E0",
            border_radius=8,
            border=ft.Border(
                left=ft.BorderSide(4, "#FF6F00"),
            ),
            visible=False,  # 默认隐藏
        )

        self.image_container = ft.Container(
            content=self.image_display,
            expand=True,
            padding=20,
            bgcolor="#FFFFFF",
        )

        right_panel = ft.Container(
            content=ft.Column([toolbar, self.image_container], spacing=0),
            expand=True,
        )

        # 主布局
        main_content = ft.Row(
            [
                left_panel,
                right_panel,
            ],
            spacing=0,
            expand=True,
        )

        # 大图预览对话框及子组件
        self.preview_image = ft.Image(
            src="",
            fit=ft.ImageFit.CONTAIN
            if hasattr(ft, "ImageFit")
            else ft.BoxFit.CONTAIN,
        )

        # 位置指示器
        self.position_indicator = ft.Container(
            content=ft.Text(
                "1 / 1",
                size=16,
                color="white",
                weight=ft.FontWeight.W_500,
            ),
            bgcolor="#00000080",
            padding=ft.Padding(left=20, right=20, top=10, bottom=10),
            border_radius=20,
            alignment=ft.Alignment(0, 0),
        )

        # 底部缩略图列表
        self.thumbnail_row = ft.Row(
            scroll=ft.ScrollMode.HIDDEN,  # 隐藏滚动条
            spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        self.preview_dialog = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Column(
                    [
                        # 顶部区域：关闭按钮
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Container(expand=True),
                                    ft.IconButton(
                                        icon=ft.icons.Icons.CLOSE,
                                        icon_color="white",
                                        bgcolor="#00000080",
                                        on_click=self.close_preview,
                                        tooltip="关闭 (ESC)",
                                    ),
                                ]
                            ),
                            height=50,
                        ),
                        # 中间区域：左按钮 + 图片 + 右按钮
                        ft.Container(
                            content=ft.Row(
                                [
                                    # 左侧按钮
                                    ft.IconButton(
                                        icon=ft.icons.Icons.CHEVRON_LEFT,
                                        icon_color="white",
                                        bgcolor="#00000080",
                                        on_click=self.show_previous_image,
                                        icon_size=40,
                                    ),
                                    # 图片容器
                                    ft.Container(
                                        content=self.preview_image,
                                        expand=True,
                                        alignment=ft.Alignment(0, 0),
                                    ),
                                    # 右侧按钮
                                    ft.IconButton(
                                        icon=ft.icons.Icons.CHEVRON_RIGHT,
                                        icon_color="white",
                                        bgcolor="#00000080",
                                        on_click=self.show_next_image,
                                        icon_size=40,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            expand=True,
                        ),
                        # 位置指示器
                        ft.Container(
                            content=self.position_indicator,
                            alignment=ft.Alignment(0, 0),
                            height=40,
                        ),
                        # 底部缩略图轮播条
                        ft.Container(
                            content=ft.Container(
                                content=self.thumbnail_row,
                                alignment=ft.Alignment(0, 0),  # 居中对齐
                            ),
                            height=100,
                            bgcolor="#00000060",
                            padding=10,
                        ),
                    ],
                    spacing=0,
                ),
                width=1000,
                height=800,  # 增加高度以容纳缩略图
                bgcolor="#000000E0",  # 半透明黑色背景
            ),
        )

        self.page.overlay.append(self.preview_dialog)
        self.page.add(main_content)

    def apply_zoom(self) -> None:
        """根据当前 zoom_level 调整预览图片大小。"""
        if self.preview_image is None or self.page is None:
            return

        base_width = self.page.window.width * 0.8
        base_height = self.page.window.height * 0.8

        self.preview_image.width = base_width * self.zoom_level
        self.preview_image.height = base_height * self.zoom_level

        self.page.update()

    # === 文件夹与设备 ===

    def build_folder_tree(self) -> None:
        """构建文件夹树（委托给 core.file_browser）。"""
        assert self.folder_tree is not None

        context = file_browser.FolderTreeContext(
            home_path=self.home_path,
            volumes_path=self.volumes_path,
            current_folder=self.current_folder,
            expanded_folders=self.expanded_folders,
        )
        callbacks = file_browser.FolderTreeCallbacks(
            on_folder_selected=lambda p: self.load_folder(str(p)),
            on_toggle_expand=self.toggle_folder_expand,
        )

        controls, device_list = file_browser.build_folder_tree(context, callbacks)

        self.folder_tree.controls.clear()
        self.folder_tree.controls.extend(controls)
        self.device_list = device_list

        if self.page is not None:
            self.page.update()

    def create_folder_item(
        self, 
        name: str, 
        path: str, 
        icon, 
        level: int = 0, 
        folder_path: Path | None = None
    ) -> ft.Container:
        """创建文件夹项
        
        Args:
            name: 文件夹显示名称
            path: 文件夹路径字符串
            icon: 文件夹图标
            level: 层级（用于缩进），0表示第一级
            folder_path: 文件夹 Path 对象（用于展开/收起）
        """
        folder_path_obj = Path(path) if folder_path is None else folder_path
        
        # 检查是否有子文件夹
        has_children = self.has_subfolders(folder_path_obj) if level >= 0 else False
        is_expanded = self.is_folder_expanded(folder_path_obj)
        
        # 展开/收起箭头（仅在有子文件夹时显示）
        expand_button = ft.IconButton(
            icon=ft.icons.Icons.ARROW_DROP_DOWN if is_expanded else ft.icons.Icons.CHEVRON_RIGHT,
            icon_size=16,
            icon_color="#666666",
            on_click=lambda e: self.toggle_folder_expand(folder_path_obj),
            visible=has_children,
            padding=0,
            width=20,
            height=20,
        )
        
        # 构建文件夹项内容
        row_controls = []
        
        # 层级缩进（第二级及以下）
        if level > 0:
            row_controls.append(ft.Container(width=24 * level))
        
        # 所有级别都显示箭头
        row_controls.append(expand_button)
        
        row_controls.extend([
            ft.Icon(icon, size=20, color="#1976D2"),
            ft.Text(name, size=14, color="#333333"),
        ])
        
        # 检查是否为当前选中的文件夹
        is_selected = self.current_folder == folder_path_obj
        
        return ft.Container(
            content=ft.Row(
                row_controls,
                spacing=5,
            ),
            padding=10,
            border_radius=8,
            ink=True,
            on_click=lambda e: self.load_folder(path),
            bgcolor="#E3F2FD" if is_selected else "transparent",
            on_hover=self.on_folder_hover,
            data=path,  # 存储路径以便后续使用
        )

    def on_folder_hover(self, e: ft.HoverEvent) -> None:
        """文件夹悬停效果"""
        # 检查是否为当前选中的文件夹
        folder_path = Path(e.control.data) if e.control.data else None
        is_selected = folder_path and self.current_folder == folder_path
        
        if e.data == "true":
            # 悬停时：如果已选中则保持选中色，否则显示悬停色
            e.control.bgcolor = "#E3F2FD" if is_selected else "#F5F5F5"
        else:
            # 离开时：如果已选中则保持选中色，否则透明
            e.control.bgcolor = "#E3F2FD" if is_selected else "transparent"
        e.control.update()

    def load_folder(self, folder_path: str) -> None:
        """加载文件夹中的图片（使用分页加载）"""
        assert self.page is not None

        self.current_folder = Path(folder_path)
        # 重置分页状态
        self.current_offset = 0
        self.has_more_images = False
        self.total_images_count = 0
        self.images = []  # 清空现有图片列表

        try:
            logger.info("开始加载文件夹: {}", self.current_folder)

            # 使用新的分页加载方法
            batch_result = image_service.list_images_in_folder_batch(
                self.current_folder,
                self.supported_formats,
                offset=0,
                limit=settings.INITIAL_IMAGE_LOAD_LIMIT,
            )

            self.images = batch_result.images
            self.current_offset = batch_result.offset
            self.has_more_images = batch_result.has_more
            self.total_images_count = batch_result.total_count

            logger.info(
                "加载文件夹完成: {}, 得到 {} 张图片, "
                "总数={}, has_more={}",
                self.current_folder.name,
                len(self.images),
                self.total_images_count,
                self.has_more_images,
            )

            self.display_images()
            # 刷新文件夹树以更新选中状态
            self.build_folder_tree()
            # 更新图片数量显示
            self.update_image_count_display()
        except Exception as exc:  # 保底异常处理
            logger.exception("加载文件夹失败: {}", self.current_folder)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"无法加载文件夹: {exc}"),
                bgcolor=ft.Colors.RED_400,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def load_more_images(self, e: ft.ControlEvent | None = None) -> None:
        """加载更多图片（下一批）"""
        assert self.page is not None
        assert self.current_folder is not None

        if not self.has_more_images:
            logger.warning("没有更多图片可加载")
            return

        try:
            logger.info(
                "加载更多图片, offset={}, limit={}",
                self.current_offset,
                settings.LOAD_MORE_BATCH_SIZE,
            )

            batch_result = image_service.list_images_in_folder_batch(
                self.current_folder,
                self.supported_formats,
                offset=self.current_offset,
                limit=settings.LOAD_MORE_BATCH_SIZE,
            )

            # 追加新图片到现有列表
            self.images.extend(batch_result.images)
            self.current_offset = batch_result.offset
            self.has_more_images = batch_result.has_more
            self.total_images_count = batch_result.total_count

            logger.info(
                "加载更多完成, 新增 {} 张, "
                "当前总数={}, has_more={}",
                len(batch_result.images),
                len(self.images),
                self.has_more_images,
            )

            # 重新渲染图片列表
            self.display_images()
            # 更新图片数量显示
            self.update_image_count_display()

        except Exception as exc:
            logger.exception("加载更多图片失败: {}", exc)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"加载失败: {exc}"),
                bgcolor=ft.Colors.RED_400,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def update_device_list(self) -> None:
        """更新移动设备列表（委托给 core.file_browser）。"""
        if not self.device_list or not self.page:
            logger.warning("设备列表或页面未初始化，跳过更新")
            return

        try:
            logger.debug("开始更新设备列表...")
            
            self.device_list.controls.clear()

            context = file_browser.FolderTreeContext(
                home_path=self.home_path,
                volumes_path=self.volumes_path,
                current_folder=self.current_folder,
                expanded_folders=self.expanded_folders,
            )
            callbacks = file_browser.FolderTreeCallbacks(
                on_folder_selected=lambda p: self.load_folder(str(p)),
                on_toggle_expand=self.toggle_folder_expand,
            )

            device_items = file_browser.build_device_items(context, callbacks)
            if device_items:
                logger.info("检测到 {} 个外部设备", len(device_items))
                self.device_list.controls.extend(device_items)
            else:
                logger.info("未检测到外部设备")
                self.device_list.controls.append(
                    ft.Container(
                        content=ft.Text(
                            "未检测到移动设备", size=12, color="#999999"
                        ),
                        padding=10,
                    )
                )
            
            # 强制更新UI
            self.device_list.update()
            self.page.update()
            logger.debug("设备列表更新完成")
            
        except Exception as exc:
            logger.exception("更新设备列表失败: {}", exc)

    def get_subfolders(self, parent_path: Path) -> List[Path]:
        """获取子文件夹列表（委托给 core.file_browser）。"""
        return file_browser.get_subfolders(parent_path)

    def has_subfolders(self, folder_path: Path) -> bool:
        """检查文件夹是否包含子文件夹（委托给 core.file_browser）。"""
        return file_browser.has_subfolders(folder_path)

    def is_folder_expanded(self, folder_path: Path) -> bool:
        """检查文件夹是否已展开。"""
        return folder_path in self.expanded_folders

    def toggle_folder_expand(self, folder_path: Path) -> None:
        """切换文件夹展开状态并重新构建文件夹树。"""
        if folder_path in self.expanded_folders:
            self.expanded_folders.remove(folder_path)
        else:
            self.expanded_folders.add(folder_path)
        self.build_folder_tree()

    def render_folder_with_children(
        self,
        folder_path: Path,
        name: str,
        icon,
        level: int = 0
    ) -> List[ft.Control]:
        """递归渲染文件夹及其子文件夹（委托给 core.file_browser）。"""
        context = file_browser.FolderTreeContext(
            home_path=self.home_path,
            volumes_path=self.volumes_path,
            current_folder=self.current_folder,
            expanded_folders=self.expanded_folders,
        )
        callbacks = file_browser.FolderTreeCallbacks(
            on_folder_selected=lambda p: self.load_folder(str(p)),
            on_toggle_expand=self.toggle_folder_expand,
        )
        return file_browser.render_folder_with_children(
            context=context,
            callbacks=callbacks,
            folder_path=folder_path,
            name=name,
            icon=icon,
            level=level,
        )

    def start_device_monitoring(self) -> None:
        """启动设备监听（使用 watchdog 事件驱动）。"""
        logger.info("启动设备监听器（watchdog 模式）")
        
        # 创建设备监听器
        self.device_monitor = DeviceMonitor(
            volumes_path=self.volumes_path,
            on_device_change=self.update_device_list
        )
        
        # 启动监听
        success = self.device_monitor.start()
        if success:
            logger.info("设备监听器启动成功，将实时响应设备插拔")
        else:
            logger.error("设备监听器启动失败，请检查日志")

    def stop_device_monitoring(self) -> None:
        """停止设备监听。"""
        if self.device_monitor:
            self.device_monitor.stop()
            logger.info("设备监听器已停止")

    # === 图片列表与视图模式 ===

    def display_images(self) -> None:
        """显示图片列表（委托给 core.image_gallery）。"""
        assert self.image_display is not None
        assert self.page is not None

        self.image_display.controls.clear()

        # 如果启用异步渲染且是网格视图，使用异步加载
        if (
            settings.ENABLE_PROGRESSIVE_RENDERING
            and self.view_mode == "grid"
            and len(self.images) > 0
        ):
            self._display_images_async()
        else:
            # 否则使用同步加载（列表视图或禁用异步）
            self._display_images_sync()

        # 如果还有更多图片，显示“加载更多”按钮
        if self.has_more_images and len(self.images) > 0:
            self.load_more_button = ft.Container(
                content=ft.Row(
                    [
                        ft.ElevatedButton(
                            content=ft.Text(f"加载更多 (当前已加载 {len(self.images)} 张)"),
                            icon=ft.icons.Icons.EXPAND_MORE,
                            on_click=self.load_more_images,
                            bgcolor="#1976D2",
                            color="white",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=20,
            )
            self.image_display.controls.append(self.load_more_button)

        self.page.update()

    def _display_images_sync(self) -> None:
        """同步显示图片（原有逻辑）。"""
        assert self.image_display is not None
        assert self.page is not None

        controls = image_gallery.build_image_views(
            images=self.images,
            view_mode=self.view_mode,
            current_folder=self.current_folder,
            window_width=self.page.window.width,
            on_preview=self.preview_image_at_index,
        )

        self.image_display.controls.extend(controls)

    def _display_images_async(self) -> None:
        """异步显示图片（渐进式渲染）。"""
        assert self.image_display is not None
        assert self.page is not None
        assert self.async_thumbnail_service is not None

        # 取消之前的加载任务
        if self.is_loading_thumbnails:
            self.async_thumbnail_service.cancel_current_task()

        # 只加载前100张（与占位符数量一致）
        images_to_display = self.images[:100]
        
        # 检查缓存，分离已缓存和未缓存的图片
        cache = self.async_thumbnail_service.cache
        cached_images = []  # (index, image_path, data_uri)
        uncached_images = []  # (index, image_path)
        
        for idx, image_path in enumerate(images_to_display):
            data_uri = cache.get(image_path)
            if data_uri:
                cached_images.append((idx, image_path, data_uri))
            else:
                uncached_images.append((idx, image_path))
        
        logger.info(
            "图片缓存检查: 总数={}, 缓存命中={}, 需生成={}",
            len(images_to_display),
            len(cached_images),
            len(uncached_images)
        )

        # 显示加载指示器（只在有未缓存图片时显示）
        if settings.SHOW_LOADING_INDICATOR and len(uncached_images) > 0:
            self.show_loading_indicator(len(uncached_images))

        # 创建带占位符的网格视图
        self.current_grid = image_gallery.build_grid_with_placeholders(
            images=self.images,
            window_width=self.page.window.width,
            on_preview=self.preview_image_at_index,
        )

        self.image_display.controls.append(self.current_grid)
        
        # 先更新已缓存的图片（同步，立即显示）
        for idx, image_path, data_uri in cached_images:
            image_gallery.update_thumbnail_in_grid(
                grid=self.current_grid,
                index=idx,
                data_uri=data_uri,
                image_path=image_path,
                thumbnail_size=settings.GRID_THUMBNAIL_SIZE,
                on_preview=self.preview_image_at_index,
            )
        
        self.page.update()  # 立即显示占位符和已缓存的图片

        # 如果所有图片都已缓存，直接返回，不启动异步任务
        if len(uncached_images) == 0:
            logger.info("所有图片已缓存，无需生成缩略图")
            return

        # 启动异步缩略图生成（只为未缓存的图片）
        self.is_loading_thumbnails = True
        self.loaded_thumbnail_count = len(cached_images)  # 已缓存的计为已完成

        # 提取未缓存图片的 Path 列表
        uncached_image_paths = [img_path for idx, img_path in uncached_images]
        
        logger.info(
            "启动异步缩略图生成, 共 {} 张",
            len(uncached_image_paths)
        )

        # 生成缩略图，但需要映射回原始索引
        self._uncached_index_map = {i: original_idx for i, (original_idx, _) in enumerate(uncached_images)}
        
        self.async_thumbnail_service.generate_thumbnails_async(
            images=uncached_image_paths,
            thumbnail_size=settings.GRID_THUMBNAIL_SIZE,
            on_single_complete=self._on_thumbnail_complete_filtered,
            on_all_complete=self._on_all_thumbnails_complete,
            on_progress=self._on_thumbnail_progress_filtered,
        )

    def _on_thumbnail_complete(self, index: int, data_uri: str, image_path: Path) -> None:
        """单张缩略图生成完成回调（在工作线程中调用）。"""
        if not self.page or not self.current_grid:
            return

        try:
            success = image_gallery.update_thumbnail_in_grid(
                grid=self.current_grid,
                index=index,
                data_uri=data_uri,
                image_path=image_path,
                thumbnail_size=settings.GRID_THUMBNAIL_SIZE,
                on_preview=self.preview_image_at_index,
            )

            if success:
                # Flet 支持在线程中直接调用 update()
                self.current_grid.update()
                logger.debug(
                    "缩略图UI更新成功: index={}, name={}",
                    index,
                    image_path.name
                )
        except Exception as exc:
            logger.exception("更新缩略图UI失败: {}", exc)

    def _on_thumbnail_complete_filtered(self, index: int, data_uri: str, image_path: Path) -> None:
        """单张缩略图生成完成回调（过滤后的索引）。
        
        Args:
            index: 在未缓存列表中的索引
            data_uri: 缩略图 data URI
            image_path: 图片路径
        """
        # 映射回原始索引
        original_index = self._uncached_index_map.get(index, index)
        self._on_thumbnail_complete(original_index, data_uri, image_path)

    def _on_thumbnail_progress(self, completed: int, total: int) -> None:
        """缩略图生成进度回调。"""
        self.loaded_thumbnail_count = completed
        
        # 更新加载指示器
        if settings.SHOW_LOADING_INDICATOR:
            try:
                self.update_loading_progress(completed, total)
            except Exception as exc:
                logger.error("更新进度指示器失败: {}", exc)
        
        logger.debug("缩略图生成进度: {}/{}", completed, total)

    def _on_thumbnail_progress_filtered(self, completed: int, total: int) -> None:
        """缩略图生成进度回调（过滤后的）。
        
        Args:
            completed: 已完成数量（未缓存的）
            total: 总数量（未缓存的）
        """
        # 加上已缓存的数量
        cached_count = self.loaded_thumbnail_count - completed  # 初始时设置为已缓存数
        actual_completed = len(self._uncached_index_map) - total + completed  # 已缓存 + 已生成
        
        self._on_thumbnail_progress(completed, total)

    def _on_all_thumbnails_complete(self) -> None:
        """所有缩略图生成完成回调。"""
        self.is_loading_thumbnails = False
        
        # 隐藏加载指示器
        if settings.SHOW_LOADING_INDICATOR:
            try:
                self.hide_loading_indicator()
            except Exception as exc:
                logger.error("隐藏指示器失败: {}", exc)
        
        logger.info(
            "所有缩略图生成完成, 共 {} 张",
            self.loaded_thumbnail_count
        )

    # === 加载状态指示器 ===

    def update_image_count_display(self) -> None:
        """更新图片数量显示。
        
        根据懒加载状态显示不同格式：
        - 如果 has_more_images=True：显示 "共{total_count}+张"
        - 否则显示 "共{len(images)}张"
        """
        if not self.image_count_text:
            return

        if len(self.images) == 0:
            self.image_count_text.value = ""
        elif self.has_more_images:
            # 还有更多图片未加载，显示 "+" 号
            self.image_count_text.value = f"共 {len(self.images)}+ 张"
        else:
            # 已加载全部，显示真实数量
            self.image_count_text.value = f"共 {len(self.images)} 张"

        if self.image_count_text:
            self.image_count_text.update()

    def show_loading_indicator(self, total: int) -> None:
        """显示加载指示器。
        
        Args:
            total: 总图片数量
        """
        if not self.loading_indicator or not self.page:
            return

        self.loaded_thumbnail_count = 0
        self.loading_progress_text.value = f"正在加载图片... (0/{total})"
        self.loading_indicator.visible = True
        
        # 将指示器插入到图片显示区域顶部
        if self.image_display:
            self.image_display.controls.insert(0, self.loading_indicator)
        
        self.page.update()
        logger.debug("显示加载指示器, 总数: {}", total)

    def update_loading_progress(self, completed: int, total: int) -> None:
        """更新加载进度。
        
        Args:
            completed: 已完成数量
            total: 总数量
        """
        if not self.loading_progress_text:
            return

        self.loading_progress_text.value = (
            f"正在加载图片... ({completed}/{total})"
        )
        
        if self.loading_indicator:
            self.loading_indicator.update()

    def hide_loading_indicator(self) -> None:
        """隐藏加载指示器。"""
        if not self.loading_indicator:
            return

        self.loading_indicator.visible = False
        
        # 从图片显示区域移除指示器
        if self.image_display and self.loading_indicator in self.image_display.controls:
            self.image_display.controls.remove(self.loading_indicator)
        
        if self.page:
            self.page.update()
        
        logger.debug("隐藏加载指示器")

    def cancel_loading(self, e: ft.ControlEvent | None = None) -> None:
        """取消当前加载任务。
        
        Args:
            e: 事件对象（可选）
        """
        logger.info("用户取消加载任务")

        # 取消异步缩略图生成
        if self.async_thumbnail_service:
            self.async_thumbnail_service.cancel_current_task()

        self.is_loading_thumbnails = False
        
        # 隐藏指示器
        self.hide_loading_indicator()
        
        # 显示取消提示
        if self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(
                    f"已取消加载，已显示 {self.loaded_thumbnail_count} 张图片"
                ),
                bgcolor="#F57C00",  # 橙色
            )
            self.page.snack_bar.open = True
            self.page.update()

    def display_grid_view(self) -> None:
        """网格视图（委托给 core.image_gallery）。"""
        assert self.page is not None
        assert self.image_display is not None

        grid = image_gallery._build_grid_view(  # 内部使用，仅为兼容旧接口
            images=self.images,
            window_width=self.page.window.width,
            on_preview=self.preview_image_at_index,
        )

        self.image_display.controls.clear()
        self.image_display.controls.append(grid)

    def display_list_view(self) -> None:
        """列表视图（委托给 core.image_gallery）。"""
        assert self.image_display is not None
    
        items = image_gallery._build_list_view(  # 内部使用，仅为兼容旧接口
            images=self.images,
            on_preview=self.preview_image_at_index,
        )
    
        self.image_display.controls.clear()
        self.image_display.controls.extend(items)
    
    def on_image_hover(self, e: ft.HoverEvent) -> None:
        """图片悬停效果（已由 core.image_gallery 处理，这里保留兼容）。"""
        e.control.bgcolor = "#F5F5F5" if e.data == "true" else "transparent"
        e.control.update()
    
    def toggle_view_mode(self, e: ft.ControlEvent) -> None:
        """切换视图模式"""
        assert self.view_mode_btn is not None
        assert self.page is not None

        if self.view_mode == "grid":
            self.view_mode = "list"
            self.view_mode_btn.icon = ft.icons.Icons.LIST
        else:
            self.view_mode = "grid"
            self.view_mode_btn.icon = ft.icons.Icons.GRID_VIEW

        self.display_images()
        self.page.update()

    # === 预览与缩略图轮播 ===

    def preview_image_at_index(self, index: int) -> None:
        """预览指定索引的图片"""
        self.current_image_index = index
        self.show_preview()

    def show_preview(self) -> None:
        """显示大图预览（委托给 core.preview）。"""
        assert self.preview_image is not None
        assert self.preview_dialog is not None
        assert self.position_indicator is not None
        assert self.thumbnail_row is not None
        assert self.page is not None

        preview.show_preview(
            images=self.images,
            current_index=self.current_image_index,
            preview_image=self.preview_image,
            position_indicator=self.position_indicator,
            thumbnail_row=self.thumbnail_row,
            preview_dialog=self.preview_dialog,
            page=self.page,
            on_thumbnail_click=lambda i: self.jump_to_image(i),
        )

        # 应用当前缩放级别
        self.apply_zoom()

    def update_thumbnail_carousel(self) -> None:
        """更新底部缩略图轮播（委托给 core.preview）。"""
        assert self.thumbnail_row is not None

        preview.update_thumbnail_carousel(
            images=self.images,
            current_index=self.current_image_index,
            thumbnail_row=self.thumbnail_row,
            on_thumbnail_click=lambda i: self.jump_to_image(i),
        )

    def jump_to_image(self, index: int) -> None:
        """跳转到指定图片"""
        self.current_image_index = index
        self.show_preview()

    def show_previous_image(self, e: ft.ControlEvent | None) -> None:
        """显示上一张图片（支持循环）"""
        if self.images:
            self.current_image_index = (self.current_image_index - 1) % len(self.images)
            self.show_preview()

    def show_next_image(self, e: ft.ControlEvent | None) -> None:
        """显示下一张图片（支持循环）"""
        if self.images:
            self.current_image_index = (self.current_image_index + 1) % len(self.images)
            self.show_preview()

    def close_preview(self, e: ft.ControlEvent | None) -> None:
        """关闭预览"""
        assert self.preview_dialog is not None
        assert self.page is not None

        self.preview_dialog.open = False
        self.page.update()

    # === 事件处理 ===

    def on_keyboard_event(self, e: ft.KeyboardEvent) -> None:
        """处理键盘事件（委托给 core.preview + 本地缩放快捷键）。"""
        assert self.preview_dialog is not None

        # 仅在预览模式下处理导航和缩放快捷键
        if self.preview_dialog.open:
            # 缩放快捷键：+ / - / 0
            if e.key in {"+", "="}:
                self.zoom_level = min(self.zoom_level + 0.1, 3.0)
                self.apply_zoom()
                return
            elif e.key in {"-", "_"}:
                self.zoom_level = max(self.zoom_level - 0.1, 0.5)
                self.apply_zoom()
                return
            elif e.key in {"0", ")"}:
                self.zoom_level = 1.0
                self.apply_zoom()
                return

            # 其他导航相关按键交给 core.preview 处理
            preview.handle_keyboard_event(
                key=e.key,
                preview_open=self.preview_dialog.open,
                show_previous=lambda: self.show_previous_image(None),
                show_next=lambda: self.show_next_image(None),
                close=lambda: self.close_preview(None),
                show_first=lambda: self.jump_to_image(0),
                show_last=lambda: self.jump_to_image(len(self.images) - 1) if self.images else None,
            )

    def on_window_resize(self, e: ft.ControlEvent) -> None:
        """窗口大小变化时重新布局"""
        if self.view_mode == "grid" and self.images:
            self.display_images()
