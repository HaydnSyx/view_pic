import flet as ft
import os
from pathlib import Path
from PIL import Image
import io
import base64
import threading
import time


class ImageViewerApp:
    """主应用类"""
    
    def __init__(self):
        self.current_folder = None
        self.images = []
        self.view_mode = "grid"  # "grid" or "list"
        self.current_image_index = 0
        self.supported_formats = (".jpg", ".jpeg", ".png", ".gif")
        self.volumes_path = Path("/Volumes")
        self.home_path = Path.home()
        self.monitoring_devices = False
        
    def main(self, page: ft.Page):
        """主程序入口"""
        page.title = "View Pic - 图片查看器"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 0
        page.spacing = 0
        page.window.width = 1200
        page.window.height = 800
        page.window.min_width = 900
        page.window.min_height = 600
        
        self.page = page
        
        # 创建UI组件
        self.create_ui()
        
        # 启动设备监听
        self.start_device_monitoring()
        
        # 监听窗口大小变化
        page.on_resized = self.on_window_resize
        
        # 监听键盘事件
        page.on_keyboard_event = self.on_keyboard_event
        
    def create_ui(self):
        """创建UI界面"""
        # 左侧文件夹树
        self.folder_tree = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=5,
            expand=True,
        )
        
        # 构建初始文件夹树
        self.build_folder_tree()
        
        left_panel = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Text(
                        "文件夹",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color="#1976D2"
                    ),
                    padding=15,
                    bgcolor="#E3F2FD",
                ),
                ft.Container(
                    content=self.folder_tree,
                    expand=True,
                    padding=10,
                )
            ]),
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
            content=ft.Row([
                ft.Text(
                    "图片库",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color="#333333",
                ),
                ft.Container(expand=True),
                self.view_mode_btn,
            ]),
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
            content=ft.Column([
                toolbar,
                self.image_container,
            ], spacing=0),
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
        
        # 大图预览对话框
        self.preview_image = ft.Image(
            src="",
            fit=ft.ImageFit.CONTAIN if hasattr(ft, 'ImageFit') else ft.BoxFit.CONTAIN,
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
                content=ft.Column([
                    # 顶部区域：关闭按钮
                    ft.Container(
                        content=ft.Row([
                            ft.Container(expand=True),
                            ft.IconButton(
                                icon=ft.icons.Icons.CLOSE,
                                icon_color="white",
                                bgcolor="#00000080",
                                on_click=self.close_preview,
                                tooltip="关闭 (ESC)",
                            ),
                        ]),
                        height=50,
                    ),
                    # 中间区域：左按钮 + 图片 + 右按钮
                    ft.Container(
                        content=ft.Row([
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
                        ], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER),
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
                ], spacing=0),
                width=1000,
                height=800,  # 增加高度以容纳缩略图
                bgcolor="#000000E0",  # 半透明黑色背景
            ),
        )
        
        self.page.overlay.append(self.preview_dialog)
        self.page.add(main_content)
        
    def build_folder_tree(self):
        """构建文件夹树"""
        self.folder_tree.controls.clear()
        
        # 常用文件夹
        common_folders = [
            ("桌面", self.home_path / "Desktop", ft.icons.Icons.FOLDER_OUTLINED),
            ("文档", self.home_path / "Documents", ft.icons.Icons.DESCRIPTION),
            ("图片", self.home_path / "Pictures", ft.icons.Icons.IMAGE),
            ("下载", self.home_path / "Downloads", ft.icons.Icons.DOWNLOAD),
        ]
        
        self.folder_tree.controls.append(
            ft.Container(
                content=ft.Text("常用位置", size=12, color="#666666", weight=ft.FontWeight.BOLD),
                padding=10,
            )
        )
        
        for name, path, icon in common_folders:
            if path.exists():
                self.folder_tree.controls.append(
                    self.create_folder_item(name, str(path), icon)
                )
        
        # 移动设备
        self.folder_tree.controls.append(
            ft.Container(height=10)
        )
        self.folder_tree.controls.append(
            ft.Container(
                content=ft.Text("移动设备", size=12, color="#666666", weight=ft.FontWeight.BOLD),
                padding=10,
            )
        )
        
        self.device_list = ft.Column(spacing=5)
        self.folder_tree.controls.append(self.device_list)
        self.update_device_list()
        
        if hasattr(self, 'page'):
            self.page.update()
        
    def create_folder_item(self, name: str, path: str, icon):
        """创建文件夹项"""
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=20, color="#1976D2"),
                ft.Text(name, size=14, color="#333333"),
            ], spacing=10),
            padding=10,
            border_radius=8,
            ink=True,
            on_click=lambda e: self.load_folder(path),
            bgcolor="transparent",
            on_hover=self.on_folder_hover,
        )
    
    def on_folder_hover(self, e):
        """文件夹悬停效果"""
        e.control.bgcolor = "#E3F2FD" if e.data == "true" else "transparent"
        e.control.update()
        
    def load_folder(self, folder_path: str):
        """加载文件夹中的图片"""
        self.current_folder = Path(folder_path)
        self.images = []
        
        try:
            # 获取文件夹中的所有图片
            for file in self.current_folder.iterdir():
                if file.is_file() and file.suffix.lower() in self.supported_formats:
                    self.images.append(file)
            
            # 按名称排序
            self.images.sort(key=lambda x: x.name)
            
            # 显示图片
            self.display_images()
            
        except Exception as e:
            print(f"加载文件夹失败: {e}")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"无法加载文件夹: {e}"),
                bgcolor=ft.colors.RED_400,
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def display_images(self):
        """显示图片列表"""
        self.image_display.controls.clear()
        
        if not self.images:
            self.image_display.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.Icons.IMAGE_NOT_SUPPORTED, size=100, color="#CCCCCC"),
                        ft.Text("此文件夹中没有图片", color="#999999", size=16),
                        ft.Text(f"当前文件夹: {self.current_folder.name if self.current_folder else ''}", 
                               color="#CCCCCC", size=12),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    alignment=ft.alignment.center,
                    expand=True,
                )
            )
        else:
            if self.view_mode == "grid":
                self.display_grid_view()
            else:
                self.display_list_view()
        
        self.page.update()
    
    def display_grid_view(self):
        """网格视图"""
        # 计算每行显示的图片数量
        container_width = self.page.window.width - 280 - 60  # 减去左侧面板和padding
        thumbnail_size = 150
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
                thumbnail = self.create_thumbnail(image_path, thumbnail_size)
                if thumbnail:
                    img_container = ft.Container(
                        content=ft.Column([
                            ft.Image(
                                src=thumbnail,
                                width=thumbnail_size,
                                height=thumbnail_size,
                                fit=ft.BoxFit.COVER if hasattr(ft, 'BoxFit') else "cover",
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
                        ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, i=idx: self.preview_image_at_index(i),
                        ink=True,
                        border_radius=8,
                        padding=5,
                        bgcolor="transparent",
                        on_hover=self.on_image_hover,
                    )
                    grid.controls.append(img_container)
            except Exception as e:
                print(f"加载缩略图失败: {image_path.name}, {e}")
        
        self.image_display.controls.append(grid)
    
    def display_list_view(self):
        """列表视图"""
        for idx, image_path in enumerate(self.images[:100]):  # 虚拟滚动
            try:
                stat = image_path.stat()
                size_mb = stat.st_size / (1024 * 1024)
                
                item = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.icons.Icons.IMAGE, size=30, color="#1976D2"),
                        ft.Column([
                            ft.Text(image_path.name, size=14, weight=ft.FontWeight.W_500),
                            ft.Text(
                                f"{size_mb:.2f} MB",
                                size=12,
                                color="#666666"
                            ),
                        ], spacing=2, expand=True),
                    ], spacing=15),
                    padding=15,
                    border=ft.Border(bottom=ft.BorderSide(1, "#E0E0E0")),
                    ink=True,
                    on_click=lambda e, i=idx: self.preview_image_at_index(i),
                    bgcolor="transparent",
                    on_hover=self.on_image_hover,
                )
                self.image_display.controls.append(item)
            except Exception as e:
                print(f"加载图片信息失败: {image_path.name}, {e}")
    
    def on_image_hover(self, e):
        """图片悬停效果"""
        e.control.bgcolor = "#F5F5F5" if e.data == "true" else "transparent"
        e.control.update()
    
    def create_thumbnail(self, image_path: Path, size: int = 150) -> str:
        """创建缩略图并返回base64编码"""
        try:
            img = Image.open(image_path)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            
            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            # Flet 0.80+ 需要 data URI 格式
            return f"data:image/png;base64,{img_base64}"
        except Exception as e:
            print(f"生成缩略图失败: {e}")
            return None
    
    def toggle_view_mode(self, e):
        """切换视图模式"""
        if self.view_mode == "grid":
            self.view_mode = "list"
            self.view_mode_btn.icon = ft.icons.Icons.LIST
        else:
            self.view_mode = "grid"
            self.view_mode_btn.icon = ft.icons.Icons.GRID_VIEW
        
        self.display_images()
        self.page.update()
    
    def preview_image_at_index(self, index: int):
        """预览指定索引的图片"""
        self.current_image_index = index
        self.show_preview()
    
    def show_preview(self):
        """显示大图预览"""
        if 0 <= self.current_image_index < len(self.images):
            image_path = self.images[self.current_image_index]
            try:
                # 加载图片
                img = Image.open(image_path)
                
                # 转换为base64
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                img_base64 = base64.b64encode(buffer.getvalue()).decode()
                
                # Flet 0.80+ 需要 data URI 格式
                self.preview_image.src = f"data:image/png;base64,{img_base64}"
                
                # 更新位置指示器
                self.position_indicator.content.value = f"{self.current_image_index + 1} / {len(self.images)}"
                
                # 更新底部缩略图轮播
                self.update_thumbnail_carousel()
                
                self.preview_dialog.open = True
                self.page.update()
            except Exception as e:
                print(f"预览图片失败: {e}")
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"无法预览图片: {e}"),
                    bgcolor=ft.colors.RED_400,
                )
                self.page.snack_bar.open = True
                self.page.update()
    
    def update_thumbnail_carousel(self):
        """更新底部缩略图轮播"""
        self.thumbnail_row.controls.clear()
        
        # 计算显示范围：当前图片左右3张，右右3张，总共7张
        total_images = len(self.images)
        visible_count = 7
        
        if total_images <= visible_count:
            # 如果图片总数小于7张，全部显示
            start_idx = 0
            end_idx = total_images
        else:
            # 计算居中显示的范围
            half_visible = visible_count // 2  # 3
            start_idx = max(0, self.current_image_index - half_visible)
            end_idx = min(total_images, start_idx + visible_count)
            
            # 边界调整
            if end_idx == total_images:
                start_idx = max(0, total_images - visible_count)
        
        # 生成缩略图
        for idx in range(start_idx, end_idx):
            image_path = self.images[idx]
            thumbnail = self.create_thumbnail(image_path, 80)  # 缩略图尺寸为80x80
            
            if thumbnail:
                # 当前图片有高亮边框
                is_current = (idx == self.current_image_index)
                border = ft.Border(
                    left=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    right=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    top=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                    bottom=ft.BorderSide(3, "#1976D2" if is_current else "transparent"),
                )
                
                thumb_container = ft.Container(
                    content=ft.Image(
                        src=thumbnail,
                        width=80,
                        height=80,
                        fit=ft.BoxFit.COVER if hasattr(ft, 'BoxFit') else "cover",
                    ),
                    border=border,
                    border_radius=5,
                    on_click=lambda e, i=idx: self.jump_to_image(i),
                    ink=True,
                )
                self.thumbnail_row.controls.append(thumb_container)
    
    def jump_to_image(self, index: int):
        """跳转到指定图片"""
        self.current_image_index = index
        self.show_preview()
    
    def show_previous_image(self, e):
        """显示上一张图片（支持循环）"""
        if len(self.images) > 0:
            self.current_image_index = (self.current_image_index - 1) % len(self.images)
            self.show_preview()
    
    def show_next_image(self, e):
        """显示下一张图片（支持循环）"""
        if len(self.images) > 0:
            self.current_image_index = (self.current_image_index + 1) % len(self.images)
            self.show_preview()
    
    def close_preview(self, e):
        """关闭预览"""
        self.preview_dialog.open = False
        self.page.update()
    
    def on_keyboard_event(self, e: ft.KeyboardEvent):
        """处理键盘事件"""
        # 只在预览对话框打开时处理键盘事件
        if self.preview_dialog.open:
            if e.key == "Arrow Left":
                self.show_previous_image(None)
            elif e.key == "Arrow Right":
                self.show_next_image(None)
            elif e.key == "Escape":
                self.close_preview(None)
    
    def on_window_resize(self, e):
        """窗口大小变化时重新布局"""
        if self.view_mode == "grid" and self.images:
            self.display_images()
    
    def update_device_list(self):
        """更新移动设备列表"""
        self.device_list.controls.clear()
        
        if self.volumes_path.exists():
            try:
                devices = [d for d in self.volumes_path.iterdir() if d.is_dir() and d.name != "Macintosh HD"]
                if devices:
                    for device in devices:
                        self.device_list.controls.append(
                            self.create_folder_item(
                                device.name,
                                str(device),
                                ft.icons.Icons.USB
                            )
                        )
                else:
                    self.device_list.controls.append(
                        ft.Container(
                            content=ft.Text("未检测到移动设备", size=12, color="#999999"),
                            padding=10,
                        )
                    )
            except Exception as e:
                print(f"读取设备列表失败: {e}")
        
        if hasattr(self, 'page'):
            self.page.update()
    
    def start_device_monitoring(self):
        """启动设备监听"""
        self.monitoring_devices = True
        
        def monitor():
            while self.monitoring_devices:
                time.sleep(3)  # 每3秒检查一次
                self.update_device_list()
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()


def main():
    app = ImageViewerApp()
    ft.run(app.main)


if __name__ == "__main__":
    main()
