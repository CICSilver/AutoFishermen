from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

cv2 = None
mss = None
np = None

WINDOW_NAME = "Desktop Region Selector"
DEFAULT_CONFIG_PATH = Path("capture_region_config.json")


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
        description="Capture the desktop, drag to select a region, and save matcher-ready parameters as JSON."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to save the selected region parameters as JSON. Default: capture_region_config.json",
    )
    parser.add_argument(
        "--save-template",
        help="Optional path to save the selected region itself as a cropped template image.",
    )
    return parser.parse_args()


def capture_primary_monitor():
    with mss.mss() as sct:
        if len(sct.monitors) < 2:
            raise RuntimeError("no primary monitor information available")
        monitor = sct.monitors[1]
        shot = np.array(sct.grab(monitor))
        frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
        return monitor, frame


def build_config_payload(monitor: dict, left: int, top: int, width: int, height: int) -> dict:
    monitor_center_x = monitor["width"] / 2.0
    monitor_center_y = monitor["height"] / 2.0
    selection_center_x = left + width / 2.0
    selection_center_y = top + height / 2.0
    centered = (
        abs(selection_center_x - monitor_center_x) < 0.5
        and abs(selection_center_y - monitor_center_y) < 0.5
    )

    screen_left = monitor["left"] + left
    screen_top = monitor["top"] + top
    payload = {
        "monitor": {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        },
        "capture_region": {
            "left": screen_left,
            "top": screen_top,
            "width": width,
            "height": height,
            "right": screen_left + width,
            "bottom": screen_top + height,
        },
        "relative_to_primary_monitor": {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        },
        "center_reference": {
            "screen_center_x": monitor["left"] + monitor_center_x,
            "screen_center_y": monitor["top"] + monitor_center_y,
            "selection_center_x": screen_left + width / 2.0,
            "selection_center_y": screen_top + height / 2.0,
            "offset_x_from_screen_center": selection_center_x - monitor_center_x,
            "offset_y_from_screen_center": selection_center_y - monitor_center_y,
            "is_exact_screen_center_region": centered,
        },
        "matcher_defaults": {
            "fps": 5.0,
            "threshold": 0.8,
            "max_candidates": 8,
            "sound_threshold": 80.0,
            "sound_notification_duration": 2.0,
            "enable_sound_monitor": True,
            "save_candidate_dataset": False,
            "dataset_dir": "data",
            "show_preview": True,
        },
        "matcher_args": {
            "region": f"--left {screen_left} --top {screen_top} --region-width {width} --region-height {height}",
            "centered_region": (
                f"--region-width {width} --region-height {height}" if centered else None
            ),
        },
    }
    return payload


class SelectionState:
    def __init__(self, monitor: dict, frame) -> None:
        self.monitor = monitor
        self.original = frame
        self.display = frame.copy()
        self.dragging = False
        self.start: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.selection: dict | None = None

    def set_selection(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        x1, y1 = start
        x2, y2 = end
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width == 0 or height == 0:
            self.selection = None
            return
        self.selection = build_config_payload(self.monitor, left, top, width, height)

    def render(self):
        canvas = self.display.copy()
        if self.dragging and self.start and self.current:
            cv2.rectangle(canvas, self.start, self.current, (0, 255, 255), 2)
            self._draw_status(canvas, self._preview_payload(self.start, self.current))
        elif self.selection:
            region = self.selection["relative_to_primary_monitor"]
            left = region["left"]
            top = region["top"]
            right = left + region["width"]
            bottom = top + region["height"]
            cv2.rectangle(canvas, (left, top), (right, bottom), (0, 255, 255), 2)
            self._draw_status(canvas, self.selection)
        else:
            self._draw_help(canvas)
        return canvas

    def _preview_payload(self, start: tuple[int, int], end: tuple[int, int]) -> dict:
        x1, y1 = start
        x2, y2 = end
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        return build_config_payload(self.monitor, left, top, width, height)

    def _draw_help(self, canvas) -> None:
        lines = [
            "Drag on the desktop screenshot to select a region",
            "Enter / Space: confirm and save JSON",
            "R: refresh desktop screenshot",
            "C: clear selection",
            "Q / Esc: quit",
        ]
        self._draw_lines(canvas, lines)

    def _draw_status(self, canvas, payload: dict) -> None:
        region = payload["capture_region"]
        center = payload["center_reference"]
        lines = [
            f"left={region['left']} top={region['top']}",
            f"width={region['width']} height={region['height']}",
            (
                "offset_from_center="
                f"({center['offset_x_from_screen_center']:.1f}, "
                f"{center['offset_y_from_screen_center']:.1f})"
            ),
            "Enter / Space: confirm  |  R: refresh  |  C: clear  |  Q / Esc: quit",
        ]
        self._draw_lines(canvas, lines)

    def _draw_lines(self, canvas, lines: list[str]) -> None:
        y = 28
        for line in lines:
            cv2.putText(
                canvas,
                line,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 32


def on_mouse(event, x, y, _flags, state: SelectionState) -> None:
    if event == cv2.EVENT_LBUTTONDOWN:
        state.dragging = True
        state.start = (x, y)
        state.current = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE and state.dragging:
        state.current = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and state.dragging:
        state.dragging = False
        state.current = (x, y)
        state.set_selection(state.start, state.current)


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_template_image(path: Path, frame, region: dict) -> None:
    rel_left = region["left"]
    rel_top = region["top"]
    rel_right = rel_left + region["width"]
    rel_bottom = rel_top + region["height"]
    cropped = frame[rel_top:rel_bottom, rel_left:rel_right]
    if cropped.size == 0:
        raise ValueError("selected template crop is empty")
    if not cv2.imwrite(str(path), cropped):
        raise RuntimeError(f"failed to save template image: {path}")


def run(args: argparse.Namespace) -> int:
    ensure_dependencies_loaded()
    output_path = Path(args.output).expanduser().resolve()
    template_output_path = (
        Path(args.save_template).expanduser().resolve() if args.save_template else None
    )
    monitor, frame = capture_primary_monitor()
    state = SelectionState(monitor, frame)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)

    print("Desktop screenshot loaded.")
    print(f"JSON output path: {output_path}")
    if template_output_path:
        print(f"Template image output path: {template_output_path}")
    print("Drag to select a region. Press Enter/Space to confirm, R to refresh, C to clear, Q/Esc to quit.")

    try:
        while True:
            cv2.imshow(WINDOW_NAME, state.render())
            key = cv2.waitKey(16) & 0xFF

            if key in (27, ord("q")):
                break
            if key == ord("c"):
                state.selection = None
                state.start = None
                state.current = None
                continue
            if key == ord("r"):
                monitor, frame = capture_primary_monitor()
                state = SelectionState(monitor, frame)
                cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)
                continue
            if key in (13, 32):
                if not state.selection:
                    print("No selection yet. Drag to select a region first.")
                    continue

                save_json(output_path, state.selection)
                print("Saved matcher config:")
                print(json.dumps(state.selection, indent=2))
                print(f"Saved JSON to: {output_path}")
                if template_output_path:
                    save_template_image(
                        template_output_path,
                        state.original,
                        state.selection["relative_to_primary_monitor"],
                    )
                    print(f"Saved template crop to: {template_output_path}")
                break
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
