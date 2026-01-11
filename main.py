import flet as ft

from src.app import ImageViewerApp


def main() -> None:
    app = ImageViewerApp()
    ft.run(app.main)


if __name__ == "__main__":
    main()
