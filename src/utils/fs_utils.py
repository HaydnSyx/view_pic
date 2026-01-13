"""通用文件系统工具方法。"""

def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为 MB 文本。"""
    size_mb = size_bytes / (1024 * 1024)
    return f"{size_mb:.2f} MB"
