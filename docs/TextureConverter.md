# [KR] Texture Converter — конвертация текстур

Картинки ⇄ PAA и EDDS, сразу много файлов. Окно — общее для массовых
конвертеров: [как пользоваться](batch_tools.md).

## Что умеет

- Картинки (png, tga, dds, jpg, jpeg) → **PAA** или **EDDS**.
- **PAA и EDDS** → png, tga или dds.
- Оба направления — за один прогон.
- Тип сжатия PAA задаёт суффикс имени файла, как у ImageToPAA: `_co` → DXT1,
  `_ca` → DXT5, `_nohq` → DXT5 со свизлом, `_smdi`, `_as` и другие. Выбранный
  тип виден в отчёте.

Настройки: «Картинки →» (PAA или EDDS), «PAA и EDDS →» (PNG, TGA или DDS).

## Командная строка

```
TextureConverter.exe "P:\мод\data"                   картинки → PAA, PAA/EDDS → PNG
TextureConverter.exe x_co.png --image-to edds        картинка → EDDS
TextureConverter.exe x_co.png --image-to edds --edds-format DXT5
TextureConverter.exe x_co.paa --texture-to tga       PAA → TGA
```

Общие ключи — [здесь](batch_tools.md#общие-ключи-командной-строки).

## Важно знать

- Размер картинки не меняется: для PAA стороны должны быть степенями двойки.
  Размер меняет [Texture Editor](TextureEditor.md).
- EDDS по умолчанию — BGRA8, без потерь.
