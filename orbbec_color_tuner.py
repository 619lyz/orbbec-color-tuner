#!/usr/bin/env python3
"""Live hardware color tuner for Orbbec RGB cameras."""

import argparse
import re
import signal
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

import cv2
import numpy as np
import pyorbbecsdk as ob
from PIL import Image, ImageTk


DEFAULTS = {
    "ORBBEC_AUTO_EXPOSURE": "false",
    "ORBBEC_EXPOSURE": "90",
    "ORBBEC_GAIN": "12",
    "ORBBEC_AUTO_WHITE_BALANCE": "false",
    "ORBBEC_WHITE_BALANCE": "4000",
    "ORBBEC_BRIGHTNESS": "0",
    "ORBBEC_CONTRAST": "50",
    "ORBBEC_SATURATION": "64",
    "ORBBEC_GAMMA": "300",
    "ORBBEC_HUE": "0",
    "ORBBEC_SHARPNESS": "50",
}

PROPERTY_IDS = {
    "exposure": ob.OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT,
    "gain": ob.OBPropertyID.OB_PROP_COLOR_GAIN_INT,
    "white_balance": ob.OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT,
    "brightness": ob.OBPropertyID.OB_PROP_COLOR_BRIGHTNESS_INT,
    "contrast": ob.OBPropertyID.OB_PROP_COLOR_CONTRAST_INT,
    "saturation": ob.OBPropertyID.OB_PROP_COLOR_SATURATION_INT,
    "gamma": ob.OBPropertyID.OB_PROP_COLOR_GAMMA_INT,
    "hue": ob.OBPropertyID.OB_PROP_COLOR_HUE_INT,
    "sharpness": ob.OBPropertyID.OB_PROP_COLOR_SHARPNESS_INT,
}

CONTROL_SPECS = (
    ("exposure", "曝光", 1, 300, 1),
    ("gain", "增益", 0, 64, 1),
    ("white_balance", "白平衡 (K)", 2800, 6500, 10),
    ("brightness", "亮度", -64, 64, 1),
    ("contrast", "对比度", 0, 100, 1),
    ("saturation", "饱和度", 0, 100, 1),
    ("gamma", "Gamma", 100, 500, 1),
    ("sharpness", "锐度", 0, 100, 1),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune Orbbec RGB camera hardware controls.")
    parser.add_argument(
        "--serial",
        help="Camera serial number. When omitted, the first detected Orbbec camera is used.",
    )
    parser.add_argument("--settings", type=Path, default=Path("orbbec_color.env"))
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def load_settings(path: Path) -> dict[str, str]:
    values = DEFAULTS.copy()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"([A-Z0-9_]+)=(.*)", line.strip())
            if match and match.group(1) in values:
                values[match.group(1)] = match.group(2)
    return values


def save_settings(path: Path, values: dict[str, int]) -> None:
    text = "\n".join(
        [
            "# Fixed Gemini 335L color controls for dataset collection and deployment.",
            "# Generated/tuned with tune_orbbec_color.sh.",
            "ORBBEC_AUTO_EXPOSURE=false",
            f"ORBBEC_EXPOSURE={values['exposure']}",
            f"ORBBEC_GAIN={values['gain']}",
            "ORBBEC_AUTO_WHITE_BALANCE=false",
            f"ORBBEC_WHITE_BALANCE={values['white_balance']}",
            f"ORBBEC_BRIGHTNESS={values['brightness']}",
            f"ORBBEC_CONTRAST={values['contrast']}",
            f"ORBBEC_SATURATION={values['saturation']}",
            f"ORBBEC_GAMMA={values['gamma']}",
            f"ORBBEC_HUE={values['hue']}",
            f"ORBBEC_SHARPNESS={values['sharpness']}",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def find_device(serial: str | None) -> ob.Device:
    context = ob.Context()
    context.set_logger_level(ob.OBLogLevel.NONE)
    devices = context.query_devices()
    for index in range(devices.get_count()):
        try:
            device = devices.get_device_by_index(index)
        except Exception as exc:
            raise RuntimeError(
                "Failed to open the Orbbec camera. Close Rerun, LeRobot recording, "
                "or any other camera viewer, then try again."
            ) from exc
        if serial is None or device.get_device_info().get_serial_number() == serial:
            info = device.get_device_info()
            print(f"[camera] {info.get_name()} ({info.get_serial_number()})")
            return device
    if serial is None:
        raise RuntimeError("No Orbbec camera was found.")
    raise RuntimeError(f"Orbbec camera {serial} was not found.")


def decode_color_frame(frame: ob.ColorFrame) -> np.ndarray:
    width = frame.get_width()
    height = frame.get_height()
    raw = np.asanyarray(frame.get_data(), dtype=np.uint8)
    frame_format = frame.get_format()
    if frame_format == ob.OBFormat.RGB:
        return cv2.cvtColor(raw.reshape(height, width, 3), cv2.COLOR_RGB2BGR)
    if frame_format == ob.OBFormat.BGR:
        return raw.reshape(height, width, 3)
    if frame_format == ob.OBFormat.MJPG:
        image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Failed to decode the Orbbec MJPG frame.")
        return image
    if frame_format == ob.OBFormat.YUYV:
        return cv2.cvtColor(raw.reshape(height, width, 2), cv2.COLOR_YUV2BGR_YUYV)
    raise RuntimeError(f"Unsupported Orbbec color format: {frame_format}")


def create_pipeline(device: ob.Device, width: int, height: int, fps: int) -> ob.Pipeline:
    pipeline = ob.Pipeline(device)
    config = ob.Config()
    profiles = pipeline.get_stream_profile_list(ob.OBSensorType.COLOR_SENSOR)
    profile = None
    for frame_format in (ob.OBFormat.RGB, ob.OBFormat.MJPG, ob.OBFormat.BGR, ob.OBFormat.YUYV):
        try:
            profile = profiles.get_video_stream_profile(width, height, frame_format, fps)
            break
        except Exception:
            continue
    config.enable_stream(profile or profiles.get_default_video_stream_profile())
    pipeline.start(config)
    return pipeline


@dataclass
class ColorTunerApp:
    root: tk.Tk
    device: ob.Device
    pipeline: ob.Pipeline
    settings_path: Path
    initial_values: dict[str, int]

    def __post_init__(self) -> None:
        self.running = True
        self.previous: dict[str, int] = {}
        self.variables: dict[str, tk.IntVar] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self.photo: ImageTk.PhotoImage | None = None

        self.root.title("Orbbec RGB Camera Color Tuner")
        self.root.geometry("1080x650")
        self.root.minsize(980, 620)
        self.root.configure(bg="#17191c")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _: self.close())
        self.root.bind("<KeyPress-q>", lambda _: self.close())
        self.root.bind("<KeyPress-Q>", lambda _: self.close())
        self.root.bind("<KeyPress-s>", lambda _: self.save())
        self.root.bind("<KeyPress-S>", lambda _: self.save())

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#f4f5f6")
        style.configure("Title.TLabel", background="#f4f5f6", foreground="#17191c", font=("Sans", 15, "bold"))
        style.configure("Name.TLabel", background="#f4f5f6", foreground="#30343a", font=("Sans", 11))
        style.configure("Value.TLabel", background="#f4f5f6", foreground="#176b55", font=("Sans", 11, "bold"))
        style.configure("Status.TLabel", background="#f4f5f6", foreground="#555b63", font=("Sans", 10))
        style.configure("Accent.TButton", font=("Sans", 11, "bold"), padding=(14, 8))
        style.configure("Tool.TButton", font=("Sans", 10), padding=(10, 8))

        container = tk.Frame(self.root, bg="#17191c")
        container.pack(fill="both", expand=True, padx=18, pady=18)

        video_panel = tk.Frame(container, bg="#0c0d0f")
        video_panel.pack(side="left", fill="both", expand=True)
        self.video_label = tk.Label(video_panel, bg="#0c0d0f")
        self.video_label.pack(expand=True)

        panel = ttk.Frame(container, style="Panel.TFrame", width=360)
        panel.pack(side="right", fill="y", padx=(16, 0))
        panel.pack_propagate(False)

        ttk.Label(panel, text="Orbbec 相机色彩", style="Title.TLabel").pack(anchor="w", padx=20, pady=(18, 2))
        ttk.Label(
            panel,
            text="已关闭自动曝光与自动白平衡",
            style="Status.TLabel",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        controls = ttk.Frame(panel, style="Panel.TFrame")
        controls.pack(fill="x", padx=20)
        for name, label, minimum, maximum, step in CONTROL_SPECS:
            row = ttk.Frame(controls, style="Panel.TFrame")
            row.pack(fill="x", pady=4)
            header = ttk.Frame(row, style="Panel.TFrame")
            header.pack(fill="x")
            ttk.Label(header, text=label, style="Name.TLabel").pack(side="left")
            value_label = ttk.Label(header, text="", style="Value.TLabel")
            value_label.pack(side="right")
            self.value_labels[name] = value_label

            variable = tk.IntVar(value=self.initial_values[name])
            self.variables[name] = variable
            scale = tk.Scale(
                row,
                from_=minimum,
                to=maximum,
                resolution=step,
                orient="horizontal",
                showvalue=False,
                variable=variable,
                command=lambda _value, control=name: self.on_control_changed(control),
                bg="#f4f5f6",
                fg="#30343a",
                troughcolor="#d4d8dc",
                activebackground="#21866c",
                highlightthickness=0,
                bd=0,
                sliderrelief="flat",
                length=310,
            )
            scale.pack(fill="x")
            self.update_value_label(name)

        self.status_label = ttk.Label(panel, text="当前参数已保存", style="Status.TLabel")
        self.status_label.pack(anchor="w", padx=20, pady=(10, 8))

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(fill="x", padx=20, pady=(0, 14))
        ttk.Button(buttons, text="保存参数", style="Accent.TButton", command=self.save).pack(
            side="left", expand=True, fill="x"
        )
        ttk.Button(buttons, text="恢复已保存值", style="Tool.TButton", command=self.restore).pack(
            side="left", expand=True, fill="x", padx=(8, 0)
        )
        ttk.Button(buttons, text="关闭", style="Tool.TButton", command=self.close).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(
            panel,
            text="快捷键：S 保存，Q / Esc 关闭",
            style="Status.TLabel",
        ).pack(anchor="w", padx=20)

        self.root.after(0, self.update_frame)

    def current_values(self) -> dict[str, int]:
        values = {name: variable.get() for name, variable in self.variables.items()}
        values["hue"] = 0
        return values

    def update_value_label(self, name: str) -> None:
        value = self.variables[name].get()
        suffix = " K" if name == "white_balance" else ""
        self.value_labels[name].configure(text=f"{value}{suffix}")

    def on_control_changed(self, name: str) -> None:
        self.update_value_label(name)
        self.status_label.configure(text="有尚未保存的修改")

    def apply_controls(self) -> None:
        for name, value in self.current_values().items():
            if self.previous.get(name) == value:
                continue
            self.device.set_int_property(PROPERTY_IDS[name], value)
            self.previous[name] = value

    def update_frame(self) -> None:
        if not self.running:
            return
        try:
            self.apply_controls()
            frames = self.pipeline.wait_for_frames(100)
            if frames is not None and frames.get_color_frame() is not None:
                image_bgr = decode_color_frame(frames.get_color_frame())
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(image_rgb)
                image.thumbnail((680, 570), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(image=image)
                self.video_label.configure(image=self.photo)
        except Exception as exc:
            self.status_label.configure(text=f"读取失败：{exc}")
        finally:
            if self.running:
                self.root.after(15, self.update_frame)

    def save(self) -> None:
        values = self.current_values()
        save_settings(self.settings_path, values)
        self.initial_values = values.copy()
        self.status_label.configure(text=f"已保存：{self.settings_path.name}")
        print(f"[tuner] Saved: {self.settings_path}")

    def restore(self) -> None:
        saved = load_settings(self.settings_path)
        key_map = {
            "exposure": "ORBBEC_EXPOSURE",
            "gain": "ORBBEC_GAIN",
            "white_balance": "ORBBEC_WHITE_BALANCE",
            "brightness": "ORBBEC_BRIGHTNESS",
            "contrast": "ORBBEC_CONTRAST",
            "saturation": "ORBBEC_SATURATION",
            "gamma": "ORBBEC_GAMMA",
            "sharpness": "ORBBEC_SHARPNESS",
        }
        for name, env_name in key_map.items():
            self.variables[name].set(int(saved[env_name]))
            self.update_value_label(name)
        self.status_label.configure(text="已恢复到文件中保存的参数")

    def close(self) -> None:
        self.running = False
        self.root.quit()


def main() -> int:
    args = parse_args()
    settings = load_settings(args.settings)
    device = find_device(args.serial)
    pipeline = create_pipeline(device, args.width, args.height, args.fps)

    device.set_bool_property(ob.OBPropertyID.OB_PROP_COLOR_AUTO_EXPOSURE_BOOL, False)
    device.set_bool_property(ob.OBPropertyID.OB_PROP_COLOR_AUTO_WHITE_BALANCE_BOOL, False)

    initial_values = {
        "exposure": int(settings["ORBBEC_EXPOSURE"]),
        "gain": int(settings["ORBBEC_GAIN"]),
        "white_balance": int(settings["ORBBEC_WHITE_BALANCE"]),
        "brightness": int(settings["ORBBEC_BRIGHTNESS"]),
        "contrast": int(settings["ORBBEC_CONTRAST"]),
        "saturation": int(settings["ORBBEC_SATURATION"]),
        "gamma": int(settings["ORBBEC_GAMMA"]),
        "sharpness": int(settings["ORBBEC_SHARPNESS"]),
        "hue": 0,
    }

    root = tk.Tk()
    app = ColorTunerApp(root, device, pipeline, args.settings, initial_values)
    signal.signal(signal.SIGINT, lambda *_: root.after(0, app.close))
    signal.signal(signal.SIGTERM, lambda *_: root.after(0, app.close))
    print("[tuner] Use the labeled controls; S=save, Q/Esc=close.")
    try:
        root.mainloop()
    finally:
        app.running = False
        pipeline.stop()
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
