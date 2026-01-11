"""应用入口模块，包含 ImageViewerApp 主类。"""

import threading
import time
from pathlib import Path
from typing import List, Set

import flet as ft
from loguru import logger

from src.config import settings
from src.core import file_browser, image_gallery, preview
from src.services import device_service, image_service


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
        self.monitoring_devices: bool = False

        # 预览相关状态
        self.zoom_level: float = 1.0
        self.expanded_folders: Set[Path] = set()  # 存储展开的文件夹路径

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

        toolbar = ft.Container(
            content=ft.Row(
                [
                    ft.Text(
                        "图片库",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color="#333333",
                    ),
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
        """加载文件夹中的图片"""
        assert self.page is not None

        self.current_folder = Path(folder_path)
        try:
            logger.info("Loading folder: {}", self.current_folder)
            self.images = image_service.list_images_in_folder(
                self.current_folder, self.supported_formats
            )
            logger.info(
                "Loaded folder: {} with {} images",
                self.current_folder,
                len(self.images),
            )
            self.display_images()
            # 刷新文件夹树以更新选中状态
            self.build_folder_tree()
        except Exception as exc:  # 保底异常处理
            logger.exception("加载文件夹失败: {}", self.current_folder)
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"无法加载文件夹: {exc}"),
                bgcolor=ft.Colors.RED_400,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def update_device_list(self) -> None:
        """更新移动设备列表（委托给 core.file_browser）。"""
        assert self.device_list is not None

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

        try:
            device_items = file_browser.build_device_items(context, callbacks)
            if device_items:
                logger.info("Detected {} device(s) in /Volumes", len(device_items))
                self.device_list.controls.extend(device_items)
            else:
                logger.info("No external devices detected")
                self.device_list.controls.append(
                    ft.Container(
                        content=ft.Text(
                            "未检测到移动设备", size=12, color="#999999"
                        ),
                        padding=10,
                    )
                )
        except Exception as exc:
            logger.exception("读取设备列表失败: {}", exc)

        if self.page is not None:
            self.page.update()

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
        """启动设备监听"""
        logger.info("Starting device monitoring thread")
        self.monitoring_devices = True

        def monitor() -> None:
            while self.monitoring_devices:
                time.sleep(settings.DEVICE_SCAN_INTERVAL)
                logger.debug("Refreshing device list from monitoring thread")
                self.update_device_list()

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    # === 图片列表与视图模式 ===

    def display_images(self) -> None:
        """显示图片列表（委托给 core.image_gallery）。"""
        assert self.image_display is not None
        assert self.page is not None

        self.image_display.controls.clear()

        controls = image_gallery.build_image_views(
            images=self.images,
            view_mode=self.view_mode,
            current_folder=self.current_folder,
            window_width=self.page.window.width,
            on_preview=self.preview_image_at_index,
        )

        self.image_display.controls.extend(controls)
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
