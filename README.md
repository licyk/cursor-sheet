# cursor-sheet

用于在 Windows 鼠标指针文件和图片序列之间互相转换的小工具集。

主要能力：

- 将 `.ani` / `.cur` 解析成 PNG 序列拼图。
- 将图片序列或带分隔线的 sprite sheet 转成 `.ani` / `.cur`。
- 将 `.ani` / `.cur` 转成 GIF 动图。
- 将 GIF 动图转成 `.ani` / `.cur` 鼠标指针。
- 自动分割黑色分隔线 sprite sheet。
- 自动去除纯色/绿幕背景，支持背景色和容差参数。
- 可选帧对齐，减少动画抖动。
- 可选像素化输出，例如把帧显式转成 `64x64`。
- 提供两个 Tk GUI：系统鼠标类型预览、hotspot 坐标查看器。

## 安装

建议在 Python 3.10+ 环境中安装：

```bash
python -m pip install -e .
```

依赖在 [pyproject.toml](pyproject.toml) 中声明，主要包括：

- `Pillow`
- `opencv-python`

如果不安装为命令，也可以用 `PYTHONPATH=src python -m ...` 的方式运行。

安装后只会暴露一个根命令 `cursor-sheet`，所有功能都通过子命令调用：

```bash
cursor-sheet sheet ...
cursor-sheet cursor ...
cursor-sheet gif ...
cursor-sheet gif-cursor ...
cursor-sheet demo
cursor-sheet hotspot
```

## 光标文件转图片拼图

将 `.ani` / `.cur` 转成 PNG 拼图：

```bash
cursor-sheet sheet cursors/Merry-Windows -o output/cursor_sheets
```

处理单个文件：

```bash
cursor-sheet sheet cursors/Merry-Windows/Arrow.ani -o output/cursor_sheets
```

常用参数：

```bash
cursor-sheet sheet cursors/Merry-Windows \
  -o output/cursor_sheets \
  --columns auto \
  --scale 1 \
  --separator-color "#000000" \
  --background-color transparent \
  --mode playback
```

说明：

- `--columns auto`：自动列数。
- `--mode playback`：按动画播放序列输出帧。
- `--mode unique`：只输出文件中唯一帧。
- `--separator-color`：拼图分隔线颜色，默认黑色。
- `--background-color`：拼图背景，默认透明。

## 鼠标指针转 GIF

将单个 `.ani` / `.cur` 转成 GIF：

```bash
cursor-sheet gif cursors/Merry-Windows/wink.ani -o output/wink.gif
```

批量转换目录中的鼠标指针文件：

```bash
cursor-sheet gif cursors/Merry-Windows -o output/cursor_gifs
```

常用参数：

```bash
cursor-sheet gif cursors/Merry-Windows/wink.ani \
  -o output/wink.gif \
  --scale 2 \
  --background-color transparent \
  --delay-ms 100 \
  --loop 0 \
  --mode playback
```

说明：

- `.ani` 会优先使用文件自带的每帧延迟。
- `.cur` 或没有延迟信息的帧会使用 `--delay-ms`。
- `--loop 0` 表示无限循环。
- `--mode unique` 可只导出唯一帧。

## GIF 转鼠标指针

将 GIF 动图转成 `.ani`：

```bash
cursor-sheet gif-cursor images/cursor.gif \
  -o output/cursor.ani \
  --hotspot 1,1
```

将单帧 GIF 转成 `.cur`：

```bash
cursor-sheet gif-cursor images/cursor.gif \
  -o output/cursor.cur \
  --format cur \
  --hotspot 1,1
```

批量转换目录中的 GIF：

```bash
cursor-sheet gif-cursor gifs_dir -o output/gif_cursors
```

常用参数：

```bash
cursor-sheet gif-cursor images/cursor.gif \
  -o output/cursor.ani \
  --hotspot 1,1 \
  --delay-ms 100 \
  --scale 1 \
  --align-frames \
  --pixelate-size 64
```

说明：

- 会优先使用 GIF 自带的每帧延迟。
- 缺失或无效的 GIF 帧延迟会使用 `--delay-ms`。
- Windows `.cur` / `.ani` 单帧尺寸必须在 `1..256` 像素之间；GIF 帧过大时可用 `--scale` 或 `--pixelate-size` 缩小。

## 图片序列转鼠标指针

将单张 sprite sheet 转成 `.ani`：

```bash
cursor-sheet cursor images/catgirl.png \
  -o output/catgirl.ani \
  --hotspot 1,1 \
  --delay-ms 100
```

将目录中的多张 PNG 按自然排序转成 `.ani`：

```bash
cursor-sheet cursor frames_dir \
  -o output/cursor.ani \
  --pattern "*.png" \
  --hotspot 1,1 \
  --delay-ms 100
```

生成静态 `.cur`：

```bash
cursor-sheet cursor frame.png \
  -o output/cursor.cur \
  --format cur \
  --hotspot 1,1
```

### 背景和分隔线

默认会尝试自动去除纯色背景，并按黑色分隔线自动拆分 sprite sheet。

如果背景或分隔线颜色不稳定，可以显式指定颜色和容差：

```bash
cursor-sheet cursor images/sheet.png \
  -o output/cursor.ani \
  --hotspot 1,1 \
  --background-color "#00ff00" \
  --background-tolerance 24 \
  --separator-color "#000000" \
  --separator-tolerance 20
```

关闭背景去除：

```bash
cursor-sheet cursor images/sheet.png -o output/cursor.ani --remove-background none
```

强制把单张输入当作普通单帧图片：

```bash
cursor-sheet cursor image.png -o output/cursor.ani --sheet-mode single
```

强制把单张输入按 sprite sheet 分割：

```bash
cursor-sheet cursor sheet.png -o output/cursor.ani --sheet-mode split
```

### 减少动画抖动

如果分割出来的每帧主体位置不同，可以启用帧对齐：

```bash
cursor-sheet cursor images/sheet.png \
  -o output/cursor.ani \
  --hotspot 1,1 \
  --align-frames
```

默认锚点是底部中心，适合角色动画：

```bash
--align-anchor bottom-center
```

也可以按中心对齐：

```bash
--align-anchor center
```

### 像素化输出

工具不会默认压缩或缩小图片。Windows `.cur` / `.ani` 单帧尺寸必须在 `1..256` 像素之间；如果分割出的帧是 `440x390`，直接写入会报错：

```text
cursor frames must be between 1 and 256 pixels
```

如果你希望显式转成低像素尺寸，可以使用：

```bash
cursor-sheet cursor images/sheet.png \
  -o output/cursor.ani \
  --hotspot 1,1 \
  --pixelate-size 64
```

也支持矩形尺寸：

```bash
--pixelate-size 64x48
```

`--pixelate` 等价于使用默认 `64x64`：

```bash
cursor-sheet cursor images/sheet.png -o output/cursor.ani --hotspot 1,1 --pixelate
```

如果不想缩小，请先把每帧源图裁剪到 `256x256` 以内，再转换。

## 批量转换 test_images

`test_images/` 中每个 PNG 通常是一张 sprite sheet。可以批量转换到另一个目录：

```bash
mkdir -p output/test_images_ani
for f in test_images/*.png; do
  name=$(basename "$f" .png)
  cursor-sheet cursor "$f" \
    -o "output/test_images_ani/$name.ani" \
    --hotspot 1,1 \
    --delay-ms 100
done
```

如果某张图分割后的帧超过 `256x256`，命令会失败。此时可以选择：

- 手动裁剪源图，让每帧不超过 `256x256`。
- 显式使用 `--pixelate-size 64` 等参数输出低像素版本。

## GUI 工具

### 鼠标类型预览

启动 Windows 鼠标类型预览 GUI：

```bash
cursor-sheet demo
```

界面会显示多个区域，鼠标移动到不同区域时，会切换成对应的 Windows 系统光标类型，例如：

- `Arrow`
- `Help`
- `AppStarting`
- `Wait`
- `Crosshair`
- `IBeam`
- `NWPen`
- `No`
- `SizeNS`
- `SizeWE`
- `SizeNWSE`
- `SizeNESW`
- `SizeAll`
- `UpArrow`
- `Hand`
- `Pin`
- `Person`

可指定列数：

```bash
cursor-sheet demo --columns 5
```

### Hotspot 查看器

启动 hotspot 坐标查看器：

```bash
cursor-sheet hotspot
```

直接打开文件：

```bash
cursor-sheet hotspot output/cursor.ani
cursor-sheet hotspot images/sheet.png
```

功能：

- 支持 `.ani` / `.cur` / 常见图片文件。
- `.ani` 可切换帧。
- 鼠标移动到图像上时，右上角显示当前像素坐标。
- 同时显示可复制到命令中的 `--hotspot x,y`。
- 左键点击可锁定坐标。

## 不安装时的运行方式

如果还没有 `pip install -e .`，可以这样运行：

```bash
PYTHONPATH=src python -m cursor_sheet sheet cursors/Merry-Windows -o output/cursor_sheets
PYTHONPATH=src python -m cursor_sheet cursor images/sheet.png -o output/cursor.ani --hotspot 1,1
PYTHONPATH=src python -m cursor_sheet gif cursors/Merry-Windows/wink.ani -o output/wink.gif
PYTHONPATH=src python -m cursor_sheet gif-cursor images/cursor.gif -o output/cursor.ani --hotspot 1,1
PYTHONPATH=src python -m cursor_sheet demo
PYTHONPATH=src python -m cursor_sheet hotspot
```

## 测试

运行全部测试：

```bash
python -m pytest
```
