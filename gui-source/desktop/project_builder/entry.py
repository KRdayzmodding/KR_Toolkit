# -*- coding: utf-8 -*-
"""Точка входа собранного ProjectBuilder.exe (окно).

`freeze_support` — первой строкой: сборка гоняет пул процессов, и в собранном
exe каждый процесс пула запускает тот же exe. Без неё вместо сборки PBO
открывались бы новые окна.
"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import main
    sys.exit(main.main())
