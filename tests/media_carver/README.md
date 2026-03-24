# media_carver tests

This folder contains CLI-mode coverage for `media_carver.py`.

## Covered modes

- help/version
- report mode
- full scan mode
- range scan mode
- reset mode
- strict dedup (default SHA-256)
- fast dedup (`--fast-dedup`)
- argument validation error paths

## Fixtures

- `fixtures/pixel_1x1.png.b64` - base64-encoded 1x1 PNG used for building
  synthetic disk-image fixtures during tests.
- `fixtures/pixel_1x1.jpg.b64` - base64-encoded 1x1 JPEG used for frame-routing
  and post-video JPEG behavior tests.

## Run tests

From repository root:

```bash
python3 -m unittest discover -s tests/media_carver -p "test_*.py"
```
