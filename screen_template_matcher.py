from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

WINDOW_NAME = "Screen Template Matcher"
cv2 = None
mss = None
np = None


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
        description="Capture the center screen region and perform template matching."
    )
    parser.add_argument(
        "--template",
        required=True,
        help="Path to the local template image.",
    )
    parser.add_argument(
        "--region-width",
        type=int,
        required=True,
        help="Width of the capture region centered on the screen.",
    )
    parser.add_argument(
        "--region-height",
        type=int,
        required=True,
        help="Height of the capture region centered on the screen.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=5.0,
        help="Capture frequency in frames per second. Default: 5.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Similarity threshold used for hit labeling. Default: 0.8.",
    )
    parser.add_argument(
        "--show-preview",
        dest="show_preview",
        action="store_true",
        default=True,
        help="Show the live preview window. Enabled by default.",
    )
    parser.add_argument(
        "--no-preview",
        dest="show_preview",
        action="store_false",
        help="Disable the live preview window and print similarity only.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.region_width <= 0 or args.region_height <= 0:
        raise ValueError("region width and height must be positive integers")
    if args.fps <= 0:
        raise ValueError("fps must be greater than 0")
    if not 0.0 <= args.threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")


def load_template(template_path: Path) -> np.ndarray:
    if not template_path.exists():
        raise FileNotFoundError(f"template image not found: {template_path}")
    if not template_path.is_file():
        raise ValueError(f"template path is not a file: {template_path}")

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"failed to load template image: {template_path}")
    return template


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


def ensure_template_fits(region: dict, template: np.ndarray) -> None:
    template_height, template_width = template.shape[:2]
    if template_width > region["width"] or template_height > region["height"]:
        raise ValueError("template image must not be larger than the capture region")


def capture_region(sct: mss.mss, region: dict) -> np.ndarray:
    raw = np.array(sct.grab(region))
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def match_template(frame: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int]]:
    result = cv2.matchTemplate(frame, template, MATCH_METHOD)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return float(max_val), max_loc


def draw_overlay(
    frame: np.ndarray,
    template: np.ndarray,
    score: float,
    top_left: tuple[int, int],
    threshold: float,
    current_fps: float,
) -> np.ndarray:
    output = frame.copy()
    th, tw = template.shape[:2]
    bottom_right = (top_left[0] + tw, top_left[1] + th)
    hit = score >= threshold
    color = (0, 200, 0) if hit else (0, 0, 255)

    cv2.rectangle(output, top_left, bottom_right, color, 2)
    cv2.putText(
        output,
        f"Score: {score:.4f} ({score * 100:.2f}%)",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        f"Threshold: {threshold:.2f} | Status: {'HIT' if hit else 'MISS'}",
        (10, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        f"FPS: {current_fps:.2f}",
        (10, 85),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return output


def should_exit_from_preview() -> bool:
    key = cv2.waitKey(1) & 0xFF
    return key in (27, ord("q"))


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    ensure_dependencies_loaded()
    template_path = Path(args.template).expanduser().resolve()
    template = load_template(template_path)

    with mss.mss() as sct:
        monitor = get_primary_monitor(sct)
        region = build_center_region(monitor, args.region_width, args.region_height)
        ensure_template_fits(region, template)

        interval = 1.0 / args.fps
        next_capture_at = time.perf_counter()
        last_loop_at = None

        print(
            "Starting capture with "
            f"template={template_path}, region={region['width']}x{region['height']}, "
            f"fps={args.fps:.2f}, threshold={args.threshold:.2f}, "
            f"preview={'on' if args.show_preview else 'off'}"
        )

        try:
            while True:
                now = time.perf_counter()
                remaining = next_capture_at - now
                if remaining > 0:
                    time.sleep(min(remaining, 0.01))
                    continue

                frame = capture_region(sct, region)
                score, top_left = match_template(frame, template)

                loop_now = time.perf_counter()
                current_fps = 0.0 if last_loop_at is None else 1.0 / max(loop_now - last_loop_at, 1e-6)
                last_loop_at = loop_now

                status = "HIT" if score >= args.threshold else "MISS"
                timestamp = time.strftime("%H:%M:%S")
                print(
                    f"[{timestamp}] similarity={score:.4f} ({score * 100:.2f}%) status={status}",
                    flush=True,
                )

                if args.show_preview:
                    preview = draw_overlay(
                        frame=frame,
                        template=template,
                        score=score,
                        top_left=top_left,
                        threshold=args.threshold,
                        current_fps=current_fps,
                    )
                    cv2.imshow(WINDOW_NAME, preview)
                    if should_exit_from_preview():
                        break
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        break

                next_capture_at = max(next_capture_at + interval, time.perf_counter())
        finally:
            if args.show_preview:
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
