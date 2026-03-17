from __future__ import annotations

import argparse
import sys
import time

cv2 = None
mss = None
np = None

WINDOW_NAME = "Capture Region Preview"
WINDOW_NAME_PROCESSED = "Capture Region Preview - Processed"
WINDOW_NAME_HALO = "Capture Region Preview - Halo Mask"


def ensure_dependencies_loaded() -> None:
    global cv2, mss, np
    if cv2 is not None and mss is not None and np is not None:
        return

    try:
        import cv2 as _cv2
        import mss as _mss
        import numpy as _np
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "missing dependency. Install requirements with: pip install -r requirements.txt"
        ) from exc

    cv2 = _cv2
    mss = _mss
    np = _np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview the centered screen capture region before template matching."
    )
    parser.add_argument(
        "--region-width",
        type=int,
        required=True,
        help="Width of the centered capture region.",
    )
    parser.add_argument(
        "--region-height",
        type=int,
        required=True,
        help="Height of the centered capture region.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=5.0,
        help="Preview refresh rate in frames per second. Default: 5.",
    )
    parser.add_argument(
        "--view-mode",
        choices=("raw", "gray", "edge", "texture", "halo", "float"),
        default="float",
        help="Processed preview mode. Default: float.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.region_width <= 0 or args.region_height <= 0:
        raise ValueError("region width and height must be positive integers")
    if args.fps <= 0:
        raise ValueError("fps must be greater than 0")


def get_primary_monitor(sct: mss.mss) -> dict:
    if len(sct.monitors) < 2:
        raise RuntimeError("no primary monitor information available")
    return sct.monitors[1]


def build_center_region(monitor: dict, region_width: int, region_height: int) -> dict:
    monitor_left = monitor["left"]
    monitor_top = monitor["top"]
    monitor_width = monitor["width"]
    monitor_height = monitor["height"]

    if region_width > monitor_width or region_height > monitor_height:
        raise ValueError("capture region cannot be larger than the primary monitor")

    left = monitor_left + (monitor_width - region_width) // 2
    top = monitor_top + (monitor_height - region_height) // 2
    return {
        "left": left,
        "top": top,
        "width": region_width,
        "height": region_height,
    }


def capture_region(sct: mss.mss, region: dict):
    raw = np.array(sct.grab(region))
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def preprocess_gray(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.equalizeHist(gray)


def preprocess_edges(image):
    gray = preprocess_gray(image)
    return cv2.Canny(gray, 50, 150)


def preprocess_texture(image):
    gray = preprocess_gray(image)
    blur = cv2.GaussianBlur(gray, (0, 0), 3.0)
    high_pass = cv2.addWeighted(gray, 1.8, blur, -0.8, 0)
    grad_x = cv2.Sobel(high_pass, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(high_pass, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    magnitude = cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX)
    magnitude = magnitude.astype(np.uint8)
    _, binary = cv2.threshold(magnitude, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    return cv2.dilate(opened, kernel, iterations=1)


def preprocess_halo(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array([18, 50, 130], dtype=np.uint8)
    upper_yellow = np.array([45, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, _a_channel, b_channel = cv2.split(lab)
    bright_mask = cv2.inRange(l_channel, 140, 255)
    warm_mask = cv2.inRange(b_channel, 140, 255)
    mask = cv2.bitwise_or(mask, cv2.bitwise_and(bright_mask, warm_mask))

    kernel_small = np.ones((3, 3), np.uint8)
    kernel_large = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_large, iterations=2)
    return cv2.dilate(mask, kernel_small, iterations=1)


def preprocess_float_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)

    h_channel, s_channel, v_channel = cv2.split(hsv)
    l_channel, _a_channel, b_channel = cv2.split(lab)

    not_water = cv2.inRange(h_channel, 0, 179)
    blue_water = cv2.inRange(h_channel, 85, 135)
    not_water = cv2.bitwise_and(not_water, cv2.bitwise_not(blue_water))

    saturated = cv2.inRange(s_channel, 35, 255)
    bright = cv2.inRange(v_channel, 95, 255)
    warm_or_neutral = cv2.inRange(b_channel, 118, 255)
    light_outline = cv2.inRange(l_channel, 140, 255)

    edge = preprocess_edges(image)
    texture = preprocess_texture(image)

    color_candidate = cv2.bitwise_and(not_water, saturated)
    color_candidate = cv2.bitwise_and(color_candidate, bright)
    outline_candidate = cv2.bitwise_and(light_outline, cv2.bitwise_or(edge, texture))
    warm_candidate = cv2.bitwise_and(warm_or_neutral, cv2.bitwise_or(edge, texture))

    mask = cv2.bitwise_or(color_candidate, outline_candidate)
    mask = cv2.bitwise_or(mask, warm_candidate)

    kernel_small = np.ones((3, 3), np.uint8)
    kernel_large = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_small, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_large, iterations=2)
    return cv2.dilate(mask, kernel_small, iterations=1)


def prepare_view(image, mode: str):
    if mode == "raw":
        return image
    if mode == "gray":
        return preprocess_gray(image)
    if mode == "edge":
        return preprocess_edges(image)
    if mode == "texture":
        return preprocess_texture(image)
    if mode == "halo":
        return preprocess_halo(image)
    if mode == "float":
        return preprocess_float_mask(image)
    raise ValueError(f"unsupported view mode: {mode}")


def draw_overlay(frame, region: dict, current_fps: float, view_mode: str):
    output = frame.copy()
    text_lines = [
        f"Region: {region['width']}x{region['height']}",
        f"Top-left: ({region['left']}, {region['top']})",
        f"FPS: {current_fps:.2f}",
        f"Processed: {view_mode}",
        "Press Q / Esc to exit",
    ]
    y = 25
    for line in text_lines:
        cv2.putText(
            output,
            line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 30
    return output


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    ensure_dependencies_loaded()

    with mss.mss() as sct:
        monitor = get_primary_monitor(sct)
        region = build_center_region(monitor, args.region_width, args.region_height)

        interval = 1.0 / args.fps
        next_capture_at = time.perf_counter()
        last_loop_at = None

        print(
            "Starting preview with "
            f"region={region['width']}x{region['height']} "
            f"at ({region['left']}, {region['top']}), fps={args.fps:.2f}"
        )

        try:
            while True:
                now = time.perf_counter()
                remaining = next_capture_at - now
                if remaining > 0:
                    time.sleep(min(remaining, 0.01))
                    continue

                frame = capture_region(sct, region)
                loop_now = time.perf_counter()
                current_fps = 0.0 if last_loop_at is None else 1.0 / max(loop_now - last_loop_at, 1e-6)
                last_loop_at = loop_now

                preview = draw_overlay(frame, region, current_fps, args.view_mode)
                processed = prepare_view(frame, args.view_mode)
                halo = preprocess_float_mask(frame)
                cv2.imshow(WINDOW_NAME, preview)
                cv2.imshow(WINDOW_NAME_PROCESSED, processed)
                cv2.imshow(WINDOW_NAME_HALO, halo)

                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break
                if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if cv2.getWindowProperty(WINDOW_NAME_PROCESSED, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if cv2.getWindowProperty(WINDOW_NAME_HALO, cv2.WND_PROP_VISIBLE) < 1:
                    break

                next_capture_at = max(next_capture_at + interval, time.perf_counter())
        finally:
            cv2.destroyAllWindows()

    return 0


def main() -> int:
    try:
        return run(parse_args())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
