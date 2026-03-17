# Screen Template Matcher

A Windows-first Python script that captures a screen region at a fixed FPS and performs real-time template matching with local tracking, multi-template support, and offline replay evaluation.

## Features

- Captures a configured screen region with `mss`
- Loads either a single template with `--template` or a template set with `--template-dir`
- Supports optional `manifest.json` metadata for per-template match mode and thresholds
- Builds candidate boxes from `float`, `halo`, or `intersection` masks before local/global fallback
- Keeps template continuity while tracking and logs template switches
- Shows a live dashboard with the active template, per-template scores, candidate counts, mask mode, and bite metrics
- Listens for loud live audio input and shows a 2-second preview notification when triggered
- Replays a directory of frames with `--replay-dir` and writes JSON/CSV reports with `--replay-output`

## Requirements

- Python 3.10+
- Windows desktop environment

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Live Usage

Single-template mode:

```bash
python screen_template_matcher.py --template .\template\float_template.png --config .\capture_region_config.json
```

Multi-template mode:

```bash
python screen_template_matcher.py --template-dir .\template --config .\capture_region_config.json --candidate-mask-mode float --use-halo-gate
```

When `--template-dir` is used, `manifest.json` inside that directory is loaded automatically when present. You can override it with `--manifest`.

## Offline Replay

```bash
python screen_template_matcher.py --template-dir .\template --replay-dir .\replay_frames --replay-output .\replay_report.json
```

Replay uses the full frame by default. If your replay frames are full-screen captures, pass `--config` or explicit region values to crop the same capture area used in live mode.

## Useful Options

- `--candidate-mask-mode float|halo|intersection`
- `--max-candidates 8`
- `--use-halo-gate`
- `--sound-threshold 80`
- `--sound-notification-duration 2`
- `--no-sound-monitor`
- `--candidate-threshold 0.52`
- `--tracking-threshold 0.60`
- `--no-preview`
- `--replay-output report.csv`

## Validation Notes

Test the following after installation:

- Run the old single-template command and confirm it still starts normally
- Run with `--template-dir .\template` and confirm the console prints multiple loaded templates
- Toggle `--use-halo-gate` and confirm candidate counts change in the overlay/dashboard
- Run a replay directory and confirm the output report contains per-frame score, template id, lock, and bite fields
- Press `q` or `Esc` in the preview window to exit cleanly
