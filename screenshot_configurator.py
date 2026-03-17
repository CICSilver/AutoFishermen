from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

cv2 = None

WINDOW_NAME = "Screenshot Configurator"


def ensure_dependencies_loaded() -> None:
    global cv2
    if cv2 is not None:
        return

    try:
        import cv2 as _cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "missing dependency. Install requirements with: pip install -r requirements.txt"
        ) from exc

    cv2 = _cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a screenshot and interactively select a region to get configuration values."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to the screenshot image you captured manually.",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=1600,
        help="Maximum display width for the preview window. Default: 1600.",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=900,
        help="Maximum display height for the preview window. Default: 900.",
    )
    parser.add_argument(
        "--save-json",
        help="Optional path to save the selected region as JSON.",
    )
    return parser.parse_args()


def load_image(image_path: Path):
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")
    if not image_path.is_file():
        raise ValueError(f"image path is not a file: {image_path}")

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"failed to load image: {image_path}")
    return image


def compute_scale(width: int, height: int, max_width: int, max_height: int) -> float:
    if max_width <= 0 or max_height <= 0:
        raise ValueError("max width and max height must be positive")
    return min(max_width / width, max_height / height, 1.0)


class SelectionState:
    def __init__(self, image, scale: float) -> None:
        self.original = image
        self.scale = scale
        self.display = (
            cv2.resize(
                image,
                (
                    max(1, int(round(image.shape[1] * scale))),
                    max(1, int(round(image.shape[0] * scale))),
                ),
                interpolation=cv2.INTER_AREA,
            )
            if scale < 1.0
            else image.copy()
        )
        self.dragging = False
        self.start = None
        self.current = None
        self.selection = None

    def screen_to_image(self, x: int, y: int) -> tuple[int, int]:
        image_x = int(round(x / self.scale))
        image_y = int(round(y / self.scale))
        image_x = max(0, min(self.original.shape[1] - 1, image_x))
        image_y = max(0, min(self.original.shape[0] - 1, image_y))
        return image_x, image_y

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
        self.selection = {
            "x": left,
            "y": top,
            "width": width,
            "height": height,
            "right": left + width,
            "bottom": top + height,
            "center_x": left + width / 2.0,
            "center_y": top + height / 2.0,
        }

    def render(self):
        canvas = self.display.copy()

        if self.dragging and self.start and self.current:
            self._draw_rect(canvas, self.start, self.current)
            self._draw_status(canvas, self._build_live_selection(self.start, self.current))
        elif self.selection:
            display_start = (
                int(round(self.selection["x"] * self.scale)),
                int(round(self.selection["y"] * self.scale)),
            )
            display_end = (
                int(round(self.selection["right"] * self.scale)),
                int(round(self.selection["bottom"] * self.scale)),
            )
            self._draw_rect(canvas, display_start, display_end)
            self._draw_status(canvas, self.selection)
        else:
            self._draw_help(canvas)

        return canvas

    def _build_live_selection(self, start: tuple[int, int], current: tuple[int, int]):
        image_start = self.screen_to_image(*start)
        image_end = self.screen_to_image(*current)
        x1, y1 = image_start
        x2, y2 = image_end
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        return {
            "x": left,
            "y": top,
            "width": width,
            "height": height,
            "right": left + width,
            "bottom": top + height,
            "center_x": left + width / 2.0,
            "center_y": top + height / 2.0,
        }

    def _draw_rect(self, canvas, start: tuple[int, int], end: tuple[int, int]) -> None:
        cv2.rectangle(canvas, start, end, (0, 255, 255), 2)

    def _draw_help(self, canvas) -> None:
        lines = [
            "Drag with mouse to select a region",
            "Enter / Space: confirm and print config",
            "R: reset selection",
            "Q / Esc: quit",
        ]
        self._draw_lines(canvas, lines)

    def _draw_status(self, canvas, selection: dict) -> None:
        lines = [
            f"x={selection['x']} y={selection['y']}",
            f"width={selection['width']} height={selection['height']}",
            f"right={selection['right']} bottom={selection['bottom']}",
            f"center=({selection['center_x']:.1f}, {selection['center_y']:.1f})",
            "Enter / Space: confirm  |  R: reset  |  Q / Esc: quit",
        ]
        self._draw_lines(canvas, lines)

    def _draw_lines(self, canvas, lines: list[str]) -> None:
        y = 25
        for line in lines:
            cv2.putText(
                canvas,
                line,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            y += 30


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
        start = state.screen_to_image(*state.start)
        end = state.screen_to_image(*state.current)
        state.set_selection(start, end)


def save_json(path: Path, selection: dict, image_path: Path) -> None:
    payload = {
        "image": str(image_path),
        "selection": selection,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    ensure_dependencies_loaded()
    image_path = Path(args.image).expanduser().resolve()
    image = load_image(image_path)
    scale = compute_scale(image.shape[1], image.shape[0], args.max_width, args.max_height)
    state = SelectionState(image, scale)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)

    print(f"Loaded image: {image_path}")
    print(f"Image size: {image.shape[1]}x{image.shape[0]}")
    print("Drag to select a region. Press Enter/Space to confirm, R to reset, Q/Esc to quit.")

    try:
        while True:
            cv2.imshow(WINDOW_NAME, state.render())
            key = cv2.waitKey(16) & 0xFF

            if key in (27, ord("q")):
                break
            if key == ord("r"):
                state.selection = None
                state.start = None
                state.current = None
                continue
            if key in (13, 32):
                if not state.selection:
                    print("No selection yet. Drag to select a region first.")
                    continue

                print("Selected region:")
                print(json.dumps(state.selection, indent=2))

                if args.save_json:
                    output_path = Path(args.save_json).expanduser().resolve()
                    save_json(output_path, state.selection, image_path)
                    print(f"Saved selection JSON to: {output_path}")
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
