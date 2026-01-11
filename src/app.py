"""应用入口模块，包含 ImageViewerApp 主类。"""

import threading
import time
from pathlib import Path
from typing import List, Set

import flet as ft

from src.config import settings
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
        
        # 文件夹树状态
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

        self.page = page

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

    # === 文件夹与设备 ===

    def build_folder_tree(self) -> None:
        """构建文件夹树（混合策略：一级扁平+二级树形）"""
        assert self.folder_tree is not None

        self.folder_tree.controls.clear()

        # 常用文件夹（第一级）
        common_folders = [
            ("桌面", self.home_path / "Desktop", ft.icons.Icons.FOLDER_OUTLINED),
            ("文档", self.home_path / "Documents", ft.icons.Icons.DESCRIPTION),
            ("图片", self.home_path / "Pictures", ft.icons.Icons.IMAGE),
            ("下载", self.home_path / "Downloads", ft.icons.Icons.DOWNLOAD),
        ]

        self.folder_tree.controls.append(
            ft.Container(
                content=ft.Text(
                    "常用位置", size=12, color="#666666", weight=ft.FontWeight.BOLD
                ),
                padding=10,
            )
        )

        # 渲染常用文件夹（第一级扁平，但可展开为树形）
        for name, path, icon in common_folders:
            if path.exists():
                # 使用递归渲染，支持展开子文件夹
                folder_controls = self.render_folder_with_children(
                    folder_path=path,
                    name=name,
                    icon=icon,
                    level=0  # 第一级
                )
                self.folder_tree.controls.extend(folder_controls)

        # 移动设备（第一级）
        self.folder_tree.controls.append(ft.Container(height=10))
        self.folder_tree.controls.append(
            ft.Container(
                content=ft.Text(
                    "移动设备", size=12, color="#666666", weight=ft.FontWeight.BOLD
                ),
                padding=10,
            )
        )

        self.device_list = ft.Column(spacing=5)
        self.folder_tree.controls.append(self.device_list)
        self.update_device_list()

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
            self.images = image_service.list_images_in_folder(
                self.current_folder, self.supported_formats
            )
            self.display_images()
            # 刷新文件夹树以更新选中状态
            self.build_folder_tree()
        except Exception as exc:  # 保底异常处理
            print(f"加载文件夹失败: {exc}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"无法加载文件夹: {exc}"),
                bgcolor=ft.Colors.RED_400,
            )
            self.page.snack_bar.open = True
            self.page.update()

    def update_device_list(self) -> None:
        """更新移动设备列表"""
        assert self.device_list is not None

        self.device_list.controls.clear()

        try:
            devices = device_service.get_connected_devices(self.volumes_path)
            if devices:
                for device in devices:
                    # 使用递归渲染，支持展开子文件夹
                    device_controls = self.render_folder_with_children(
                        folder_path=device,
                        name=device.name,
                        icon=ft.icons.Icons.USB,
                        level=0  # 第一级
                    )
                    self.device_list.controls.extend(device_controls)
            else:
                self.device_list.controls.append(
                    ft.Container(
                        content=ft.Text(
                            "未检测到移动设备", size=12, color="#999999"
                        ),
                        padding=10,
                    )
                )
        except Exception as exc:
            print(f"读取设备列表失败: {exc}")

        if self.page is not None:
            self.page.update()

    def get_subfolders(self, parent_path: Path) -> List[Path]:
        """获取子文件夹列表"""
        try:
            subfolders = [
                item for item in parent_path.iterdir()
                if item.is_dir() 
                and not item.name.startswith('.')  # 过滤隐藏文件夹
                and not item.name.startswith('$')  # 过滤系统文件夹如 $RECYCLE.BIN
            ]
            return sorted(subfolders, key=lambda x: x.name.lower())
        except (PermissionError, OSError) as exc:
            print(f"无法访问文件夹 {parent_path}: {exc}")
            return []

    def has_subfolders(self, folder_path: Path) -> bool:
        """检查文件夹是否包含子文件夹（总是返回 True 以显示箭头）"""
        # 始终返回 True，让所有文件夹都显示箭头
        return True

    def is_folder_expanded(self, folder_path: Path) -> bool:
        """检查文件夹是否已展开"""
        return folder_path in self.expanded_folders

    def toggle_folder_expand(self, folder_path: Path) -> None:
        """切换文件夹展开状态"""
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
        """递归渲染文件夹及其子文件夹
        
        Args:
            folder_path: 文件夹路径
            name: 显示名称
            icon: 图标
            level: 当前层级（0表示第一级）
            
        Returns:
            包含文件夹项及其子文件夹的控件列表
        """
        controls = []
        
        # 添加当前文件夹项
        controls.append(
            self.create_folder_item(
                name=name,
                path=str(folder_path),
                icon=icon,
                level=level,
                folder_path=folder_path
            )
        )
        
        # 如果展开，递归渲染子文件夹
        if self.is_folder_expanded(folder_path):
            subfolders = self.get_subfolders(folder_path)
            for subfolder in subfolders:
                controls.extend(
                    self.render_folder_with_children(
                        folder_path=subfolder,
                        name=subfolder.name,
                        icon=ft.icons.Icons.FOLDER_OUTLINED,
                        level=level + 1
                    )
                )
        
        return controls

    def start_device_monitoring(self) -> None:
        """启动设备监听"""
        self.monitoring_devices = True

        def monitor() -> None:
            while self.monitoring_devices:
                time.sleep(settings.DEVICE_SCAN_INTERVAL)
                self.update_device_list()

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    # === 图片列表与视图模式 ===

    def display_images(self) -> None:
        """显示图片列表"""
        assert self.image_display is not None
        assert self.page is not None

        self.image_display.controls.clear()

        if not self.images:
            self.image_display.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.icons.Icons.IMAGE_NOT_SUPPORTED,
                                size=100,
                                color="#CCCCCC",
                            ),
                            ft.Text(
                                "此文件夹中没有图片",
                                color="#999999",
                                size=16,
                            ),
                            ft.Text(
                                f"当前文件夹: {self.current_folder.name if self.current_folder else ''}",
                                color="#CCCCCC",
                                size=12,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    alignment=ft.Alignment(0, 0),
                    expand=True,
                )
            )
        else:
            if self.view_mode == "grid":
                self.display_grid_view()
            else:
                self.display_list_view()

        self.page.update()

    def display_grid_view(self) -> None:
        """网格视图"""
        assert self.page is not None
        assert self.image_display is not None

        # 计算每行显示的图片数量
        container_width = (
            self.page.window.width - settings.LEFT_PANEL_WIDTH - settings.GRID_PADDING
        )
        thumbnail_size = settings.GRID_THUMBNAIL_SIZE
        cols = max(2, int(container_width // (thumbnail_size + 20)))

        # 创建网格
        grid = ft.GridView(
            expand=True,
            runs_count=cols,
            max_extent=thumbnail_size + 20,
            child_aspect_ratio=0.8,
            spacing=15,
            run_spacing=15,
        )

        for idx, image_path in enumerate(self.images[:100]):  # 虚拟滚动：先只加载前100张
            try:
                thumbnail = image_service.create_thumbnail_data_uri(
                    image_path, thumbnail_size
                )
                if thumbnail:
                    img_container = ft.Container(
                        content=ft.Column(
                            [
                                ft.Image(
                                    src=thumbnail,
                                    width=thumbnail_size,
                                    height=thumbnail_size,
                                    fit=ft.BoxFit.COVER
                                    if hasattr(ft, "BoxFit")
                                    else "cover",
                                    border_radius=8,
                                ),
                                ft.Text(
                                    image_path.name,
                                    size=12,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    width=thumbnail_size,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ],
                            spacing=5,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        on_click=lambda e, i=idx: self.preview_image_at_index(i),
                        ink=True,
                        border_radius=8,
                        padding=5,
                        bgcolor="transparent",
                        on_hover=self.on_image_hover,
                    )
                    grid.controls.append(img_container)
            except Exception as exc:
                print(f"加载缩略图失败: {image_path.name}, {exc}")

        self.image_display.controls.append(grid)

    def display_list_view(self) -> None:
        """列表视图"""
        assert self.image_display is not None

        for idx, image_path in enumerate(self.images[:100]):  # 虚拟滚动
            try:
                stat = image_path.stat()
                size_mb = stat.st_size / (1024 * 1024)

                item = ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.icons.Icons.IMAGE,
                                size=30,
                                color="#1976D2",
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        image_path.name,
                                        size=14,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        f"{size_mb:.2f} MB",
                                        size=12,
                                        color="#666666",
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=15,
                    ),
                    padding=15,
                    border=ft.Border(
                        bottom=ft.BorderSide(1, "#E0E0E0"),
                    ),
                    ink=True,
                    on_click=lambda e, i=idx: self.preview_image_at_index(i),
                    bgcolor="transparent",
                    on_hover=self.on_image_hover,
                )
                self.image_display.controls.append(item)
            except Exception as exc:
                print(f"加载图片信息失败: {image_path.name}, {exc}")

    def on_image_hover(self, e: ft.HoverEvent) -> None:
        """图片悬停效果"""
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
        """显示大图预览"""
        assert self.preview_image is not None
        assert self.preview_dialog is not None
        assert self.position_indicator is not None
        assert self.page is not None

        if 0 <= self.current_image_index < len(self.images):
            image_path = self.images[self.current_image_index]
            try:
                # 加载图片并转换为 data URI
                self.preview_image.src = image_service.load_image_data_uri(image_path)

                # 更新位置指示器
                self.position_indicator.content.value = (
                    f"{self.current_image_index + 1} / {len(self.images)}"
                )

                # 更新底部缩略图轮播
                self.update_thumbnail_carousel()

                self.preview_dialog.open = True
                self.page.update()
            except Exception as exc:
                print(f"预览图片失败: {exc}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"无法预览图片: {exc}"),
                    bgcolor=ft.Colors.RED_400,
                )
                self.page.snack_bar.open = True
                self.page.update()

    def update_thumbnail_carousel(self) -> None:
        """更新底部缩略图轮播"""
        assert self.thumbnail_row is not None

        self.thumbnail_row.controls.clear()

        # 计算显示范围：当前图片左右3张，总共7张
        total_images = len(self.images)
        visible_count = 7

        if total_images <= visible_count:
            start_idx = 0
            end_idx = total_images
        else:
            half_visible = visible_count // 2  # 3
            start_idx = max(0, self.current_image_index - half_visible)
            end_idx = min(total_images, start_idx + visible_count)

            if end_idx == total_images:
                start_idx = max(0, total_images - visible_count)

        for idx in range(start_idx, end_idx):
            image_path = self.images[idx]
            thumbnail = image_service.create_thumbnail_data_uri(image_path, 80)

            if thumbnail:
                is_current = idx == self.current_image_index
                border = ft.Border(
                    left=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    right=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    top=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    bottom=ft.BorderSide(
                        3, "#1976D2" if is_current else "transparent"
                    ),
                )

                thumb_container = ft.Container(
                    content=ft.Image(
                        src=thumbnail,
                        width=80,
                        height=80,
                        fit=ft.BoxFit.COVER
                        if hasattr(ft, "BoxFit")
                        else "cover",
                    ),
                    border=border,
                    border_radius=5,
                    on_click=lambda e, i=idx: self.jump_to_image(i),
                    ink=True,
                )
                self.thumbnail_row.controls.append(thumb_container)

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
        """处理键盘事件"""
        assert self.preview_dialog is not None

        # 只在预览对话框打开时处理键盘事件
        if self.preview_dialog.open:
            if e.key == "Arrow Left":
                self.show_previous_image(None)
            elif e.key == "Arrow Right":
                self.show_next_image(None)
            elif e.key == "Escape":
                self.close_preview(None)

    def on_window_resize(self, e: ft.ControlEvent) -> None:
        """窗口大小变化时重新布局"""
        if self.view_mode == "grid" and self.images:
            self.display_images()
