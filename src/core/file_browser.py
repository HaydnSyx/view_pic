"""文件夹浏览核心模块：构建左侧文件夹树与设备列表。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence, Set, Tuple

import flet as ft
from loguru import logger

from src.config import settings
from src.services import device_service


@dataclass
class FolderTreeContext:
    """文件夹树所需的上下文状态。"""

    home_path: Path
    volumes_path: Path
    current_folder: Path | None
    expanded_folders: Set[Path]


@dataclass
class FolderTreeCallbacks:
    """文件夹树与外部交互所需的回调。"""

    on_folder_selected: Callable[[Path], None]
    on_toggle_expand: Callable[[Path], None]
    on_refresh_devices: Callable[[], None] | None = None  # 刷新设备列表回调


def build_folder_tree(
    context: FolderTreeContext,
    callbacks: FolderTreeCallbacks,
) -> Tuple[List[ft.Control], ft.Column]:
    """构建左侧文件夹树及设备列表。

    返回值:
        controls: 文件夹树区域所有控件（包括分组标题和设备标题）
        device_list: 设备列表 Column，用于后续动态刷新
    """

    controls: List[ft.Control] = []

    # 常用文件夹（第一级）
    common_folders: Sequence[tuple[str, Path, str]] = [
        ("桌面", context.home_path / "Desktop", ft.icons.Icons.FOLDER_OUTLINED),
        ("文档", context.home_path / "Documents", ft.icons.Icons.DESCRIPTION),
        ("图片", context.home_path / "Pictures", ft.icons.Icons.IMAGE),
        ("下载", context.home_path / "Downloads", ft.icons.Icons.DOWNLOAD),
    ]

    # 分组标题：常用位置
    controls.append(
        ft.Container(
            content=ft.Text(
                "常用位置", size=12, color="#666666", weight=ft.FontWeight.BOLD
            ),
            padding=10,
        )
    )

    # 渲染常用文件夹（第一级扁平，但支持树形展开）
    for name, path, icon in common_folders:
        if path.exists():
            folder_controls = render_folder_with_children(
                context=context,
                callbacks=callbacks,
                folder_path=path,
                name=name,
                icon=icon,
                level=0,
            )
            controls.extend(folder_controls)

    # 分组标题：移动设备
    controls.append(ft.Container(height=10))
    
    # 创建刷新按钮（如果提供了回调）
    device_title_controls = [
        ft.Text(
            "移动设备", 
            size=12, 
            color="#666666", 
            weight=ft.FontWeight.BOLD
        )
    ]
    
    # 如果提供了刷新回调，添加刷新按钮
    if callbacks.on_refresh_devices is not None:
        device_title_controls.extend([
            ft.Container(expand=True),  # 占位，将按钮推到右侧
            ft.IconButton(
                icon=ft.icons.Icons.REFRESH,
                icon_size=16,
                tooltip="刷新设备列表",
                on_click=lambda _: callbacks.on_refresh_devices(),
                icon_color="#666666",
            )
        ])
    
    controls.append(
        ft.Container(
            content=ft.Row(
                controls=device_title_controls,
                spacing=5,
            ),
            padding=ft.padding.only(left=10, right=5, top=10, bottom=10),
        )
    )

    device_list = ft.Column(spacing=5)
    controls.append(device_list)

    # 初始设备列表
    device_items = build_device_items(context=context, callbacks=callbacks)
    if device_items:
        device_list.controls.extend(device_items)
    else:
        device_list.controls.append(
            ft.Container(
                content=ft.Text("未检测到移动设备", size=12, color="#999999"),
                padding=10,
            )
        )

    return controls, device_list


def build_device_items(
    context: FolderTreeContext, callbacks: FolderTreeCallbacks
) -> List[ft.Control]:
    """构建移动设备区域内的文件夹项列表。"""

    devices = device_service.get_connected_devices(context.volumes_path)
    items: List[ft.Control] = []
    for device in devices:
        items.extend(
            render_folder_with_children(
                context=context,
                callbacks=callbacks,
                folder_path=device,
                name=device.name,
                icon=ft.icons.Icons.USB,
                level=0,
            )
        )
    return items


def render_folder_with_children(
    context: FolderTreeContext,
    callbacks: FolderTreeCallbacks,
    folder_path: Path,
    name: str,
    icon,
    level: int = 0,
) -> List[ft.Control]:
    """递归渲染文件夹及其子文件夹。"""

    controls: List[ft.Control] = []

    # 当前文件夹项
    controls.append(
        create_folder_item(
            context=context,
            callbacks=callbacks,
            name=name,
            folder_path=folder_path,
            icon=icon,
            level=level,
        )
    )

    # 如已展开，则渲染子文件夹
    if is_folder_expanded(folder_path, context.expanded_folders):
        for subfolder in get_subfolders(folder_path):
            controls.extend(
                render_folder_with_children(
                    context=context,
                    callbacks=callbacks,
                    folder_path=subfolder,
                    name=subfolder.name,
                    icon=ft.icons.Icons.FOLDER_OUTLINED,
                    level=level + 1,
                )
            )

    return controls


def create_folder_item(
    context: FolderTreeContext,
    callbacks: FolderTreeCallbacks,
    name: str,
    folder_path: Path,
    icon,
    level: int = 0,
) -> ft.Container:
    """创建单个文件夹项控件。"""

    has_children = has_subfolders(folder_path)
    is_expanded = is_folder_expanded(folder_path, context.expanded_folders)

    # 展开/收起箭头（仅在可能存在子文件夹时显示）
    expand_button = ft.IconButton(
        icon=ft.icons.Icons.ARROW_DROP_DOWN
        if is_expanded
        else ft.icons.Icons.CHEVRON_RIGHT,
        icon_size=16,
        icon_color="#666666",
        on_click=lambda e, p=folder_path: callbacks.on_toggle_expand(p),
        visible=has_children,
        padding=0,
        width=20,
        height=20,
    )

    # 行内容
    row_controls: List[ft.Control] = []

    # 层级缩进（第二级及以下）
    if level > 0:
        row_controls.append(ft.Container(width=24 * level))

    row_controls.append(expand_button)
    row_controls.extend(
        [
            ft.Icon(icon, size=20, color="#1976D2"),
            ft.Text(name, size=14, color="#333333"),
        ]
    )

    is_selected = context.current_folder == folder_path

    return ft.Container(
        content=ft.Row(row_controls, spacing=5),
        padding=10,
        border_radius=8,
        ink=True,
        on_click=lambda e, p=folder_path: callbacks.on_folder_selected(p),
        bgcolor="#E3F2FD" if is_selected else "transparent",
        on_hover=_on_folder_hover,
        data=str(folder_path),
    )


def _on_folder_hover(e: ft.HoverEvent) -> None:
    """文件夹悬停效果处理。"""

    folder_path_str = e.control.data
    folder_path = Path(folder_path_str) if folder_path_str else None

    # 选中状态通过背景色是否为选中色来判断
    is_selected = e.control.bgcolor == "#E3F2FD"

    if e.data == "true":
        e.control.bgcolor = "#E3F2FD" if is_selected else "#F5F5F5"
    else:
        e.control.bgcolor = "#E3F2FD" if is_selected else "transparent"
    e.control.update()


def get_subfolders(parent_path: Path) -> List[Path]:
    """获取子文件夹列表。"""

    try:
        subfolders = [
            item
            for item in parent_path.iterdir()
            if item.is_dir()
            and not item.name.startswith(".")
            and not item.name.startswith("$")
        ]
        return sorted(subfolders, key=lambda x: x.name.lower())
    except (PermissionError, OSError) as exc:
        logger.error("无法访问文件夹 {}: {}", parent_path, exc)
        # 这里不直接抛出，让调用方优雅处理
        return []


def has_subfolders(folder_path: Path) -> bool:
    """检查文件夹是否可能包含子文件夹。

    当前实现保持与原逻辑一致：始终返回 True，用于始终显示箭头。
    后续如需优化表现，可改为实际扫描一次子目录。
    """

    return True


def is_folder_expanded(folder_path: Path, expanded_folders: Set[Path]) -> bool:
    """检查文件夹是否已展开。"""

    return folder_path in expanded_folders
