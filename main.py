import flet as ft

from src.app import ImageViewerApp
from src.config.logging_config import setup_logging
from loguru import logger


def main() -> None:
    setup_logging()
    logger.info("Starting View Pic application")

    app = ImageViewerApp()
    ft.run(app.main)


if __name__ == "__main__":
    main()
