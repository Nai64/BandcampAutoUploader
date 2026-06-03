"""Experimental PySide6 GUI migration package."""


def main():
    from .app import main as run_qt_gui

    return run_qt_gui()

__all__ = ["main"]
