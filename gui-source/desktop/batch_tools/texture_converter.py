# -*- coding: utf-8 -*-
"""Точка входа собранного TextureConverter_GUI.exe (окно); пути в аргументах — во входы окна."""
import sys

if __name__ == "__main__":
    import main
    sys.exit(main.main("textures", sys.argv[1:]))
