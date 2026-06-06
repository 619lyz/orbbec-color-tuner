# Orbbec Color Tuner

A lightweight GUI for tuning RGB hardware controls on Orbbec cameras.

It provides a live camera preview and labeled controls for:

- Exposure
- Gain
- White balance
- Brightness
- Contrast
- Saturation
- Gamma
- Sharpness

The selected values are saved to an environment-style configuration file, making
them easy to reuse in robotics data collection and deployment pipelines.

## Why.

Automatic exposure and automatic white balance can cause the same object to look
different between episodes. This is especially noticeable in manipulation tasks
that depend on color, such as distinguishing red, orange, and yellow objects.

This tool disables both automatic controls while it is running and lets you select
stable, repeatable hardware settings.

## Tested Hardware

- Orbbec Gemini 335L
- Ubuntu 22.04
- Python 3.10

Other Orbbec RGB cameras supported by `pyorbbecsdk2` may also work.

## Installation

```bash
sudo apt install python3-tk

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The official Orbbec SDK and USB permissions must already be working. Verify that
the camera is visible before starting the tuner.

## Usage

Use the first detected Orbbec camera:

```bash
./run_tuner.sh
```

Select a camera by serial number:

```bash
./run_tuner.sh --serial YOUR_CAMERA_SERIAL
```

Select another stream profile:

```bash
./run_tuner.sh --width 1280 --height 720 --fps 30
```

Controls:

| Action | Result |
|---|---|
| Move a slider | Apply the value to the camera immediately |
| Save settings | Write values to `orbbec_color.env` |
| Restore saved values | Reload the last saved configuration |
| `S` | Save |
| `Q` or `Esc` | Close and release the camera |

Only one process can normally own the camera. Close Rerun, LeRobot recording, or
other camera viewers before launching this tool.

## Configuration Output

The generated `orbbec_color.env` looks like:

```bash
ORBBEC_AUTO_EXPOSURE=false
ORBBEC_EXPOSURE=90
ORBBEC_GAIN=12
ORBBEC_AUTO_WHITE_BALANCE=false
ORBBEC_WHITE_BALANCE=4000
ORBBEC_BRIGHTNESS=0
ORBBEC_CONTRAST=50
ORBBEC_SATURATION=64
ORBBEC_GAMMA=300
ORBBEC_HUE=0
ORBBEC_SHARPNESS=50
```

The included values are an example validated on a Gemini 335L under one lighting
setup. They are not universal calibration values.

## 中文说明

这是一个用于调节 Orbbec 彩色相机硬件参数的实时可视化工具，支持曝光、
增益、白平衡、亮度、对比度、饱和度、Gamma 和锐度。

自动曝光和自动白平衡可能导致同一个物体在不同数据采集 episode 中出现明显
色差。该工具会关闭这两个自动功能，并将调好的固定参数保存到
`orbbec_color.env`，方便在机器人数据采集和部署时复用。

启动：

```bash
./run_tuner.sh
```

指定相机序列号：

```bash
./run_tuner.sh --serial 相机序列号
```

界面中拖动滑块会立即修改相机参数；点击“保存参数”或按 `S` 保存；按 `Q`
或 `Esc` 关闭。启动前需要关闭占用相机的 Rerun、LeRobot 采集程序或其他
相机预览工具。
