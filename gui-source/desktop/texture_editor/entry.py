# -*- coding: utf-8 -*-
"""Точка входа собранного TextureEditor_GUI.exe (PyInstaller).

Импорты явные: анализатор PyInstaller не видит модулей вкладок (их находят
через sys.path, который ``main`` дописывает на лету). Китов здесь нет: работу
делает TextureEditor.exe рядом (remote.py).
"""
import sys

import canvas                                # noqa: F401
import fresnel_page                          # noqa: F401
import look                                  # noqa: F401
import resize_page                           # noqa: F401
import smdi_folder                           # noqa: F401
import viewer                                # noqa: F401
import remote                                # noqa: F401
from main import main

if __name__ == "__main__":
    sys.exit(main())
