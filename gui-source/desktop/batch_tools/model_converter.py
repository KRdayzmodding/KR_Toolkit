# -*- coding: utf-8 -*-
"""Точка входа собранного ModelConverter_GUI.exe (окно); пути в аргументах — во входы окна."""
import sys

if __name__ == "__main__":
    import main
    sys.exit(main.main("models", sys.argv[1:]))
