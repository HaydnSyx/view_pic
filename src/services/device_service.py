"""设备相关服务：扫描 /Volumes 下的挂载设备。"""

from pathlib import Path
from typing import List


def get_connected_devices(volumes_path: Path) -> List[Path]:
    """返回当前已挂载的移动设备列表（排除系统盘）。"""
    if not volumes_path.exists():
        return []
    return [
        d
        for d in volumes_path.iterdir()
        if d.is_dir() and d.name != "Macintosh HD"
    ]
