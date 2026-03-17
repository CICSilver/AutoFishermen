# AGENTS.md

## Working rules
- Make minimal, high-confidence changes.
- Do not refactor unrelated code.
- Keep CLI backward compatible.
- Prefer traditional OpenCV methods.
- Preserve existing features unless they directly hurt detection.
- Explain modified functions and verification steps after coding.

## For this project
- Detection priority should be: candidate regions -> local search -> global search.
- Avoid using max-of-many-modes unstable matching as the default strategy.
- History should only store trustworthy detections.
- Debuggability is required.