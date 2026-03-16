# Screen Template Matcher

A Windows-first Python script that captures a centered region of the screen at a fixed FPS and performs real-time template matching against a local image.

## Features

- Captures the screen center region with configurable width and height
- Matches a local template image on every sampled frame
- Prints the current similarity score in the console
- Shows an optional live preview window with the best match box and similarity overlay

## Requirements

- Python 3.10+
- Windows desktop environment

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
python screen_template_matcher.py --template .\template.png --region-width 600 --region-height 400 --fps 5
```

Or use the Windows batch launcher to create `.venv`, install dependencies, and run the script:

```bat
run_matcher.bat --template .\template.png --region-width 600 --region-height 400 --fps 5
```

Optional arguments:

- `--threshold 0.8`: marks matches as `HIT` when similarity is equal to or above this score
- `--no-preview`: disables the OpenCV preview window and prints similarity only

## Template Guidance

- Keep the template smaller than the capture region
- Use a template with the same size and scale as the target UI element
- If the target colors vary a lot, consider a future grayscale or multi-template extension

## Validation Notes

Test the following after installation:

- Start with a visible target inside the center capture area and confirm the score rises
- Use a template that is not on screen and confirm the score stays low
- Try invalid paths or oversize templates and confirm the script exits with a clear error
- Press `q` or `Esc` in the preview window to exit cleanly
