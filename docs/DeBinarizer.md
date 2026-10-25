# [KR] DeBinarizer — бинарные файлы → текст

Бинарные (рапифицированные) конфиги и их родня → текст. Окно — общее для
массовых конвертеров: [как пользоваться](batch_tools.md).

## Что умеет

- `config.bin` → `config.cpp` рядом.
- `.rvmat`, `.bisurf`, `model.cfg`, `.sqm` — в текст на месте, под своим
  именем; прежний бинарник уходит копией в `%USERPROFILE%\.kr_devtoolkit\backup`.
- Файлы узнаются по содержимому (сигнатуре raP), а не по расширению.

## Командная строка

```
DeBinarizer.exe config.bin   → config.cpp рядом
DeBinarizer.exe x.rvmat      → текст на месте, бинарник — копией в backup
DeBinarizer.exe "P:\мод"     все бинарные конфиги дерева
```

Общие ключи — [здесь](batch_tools.md#общие-ключи-командной-строки).

## Важно знать

- С «Удалять исходник» прежний бинарник не сохраняется.
- Модели — [Model Converter](ModelConverter.md), PBO целиком —
  [PBO Unpacker](PboUnpacker.md).
