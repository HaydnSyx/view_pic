"""日志配置模块：基于 loguru 的统一日志初始化。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger


_IS_CONFIGURED: bool = False


def setup_logging() -> None:
    """初始化 loguru 日志配置。

    - 日志目录固定为项目根目录下的 ``logs/``；
    - 日志文件按小时维度滚动，文件名形如 ``view_pic_YYYYMMDD_HH.log``；
    - 默认保留最近 72 小时的日志。
    """

    global _IS_CONFIGURED
    if _IS_CONFIGURED:
        return

    # 计算项目根目录：.../view_pic/src/config/logging_config.py -> .../view_pic
    project_root = Path(__file__).resolve().parents[2]
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file_pattern = logs_dir / "view_pic_{time:YYYYMMDD_HH}.log"

    # 清理默认 handlers，避免重复输出
    logger.remove()

    # 控制台输出（方便开发调试）
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    )

    # 文件输出：按小时轮转
    logger.add(
        log_file_pattern,
        rotation="1 hour",
        retention="72 hours",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    )

    _IS_CONFIGURED = True
