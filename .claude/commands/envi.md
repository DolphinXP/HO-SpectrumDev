# ENVI File Format

Implement or review `src/data/envi_writer.py`.

## File Pair

Every saved dataset produces two files:
- `<name>.hdr` — ASCII header
- `<name>.dat` — raw binary data

## Header Format (.hdr)

```
ENVI
description = {gpy4 hyperspectral acquisition YYYY-MM-DD HH:MM:SS}
samples = 1280
lines = N
bands = 1024
header offset = 0
file type = ENVI Standard
data type = {dtype_code}
interleave = bil
byte order = 0
wavelength units = nm
wavelength = {w0, w1, w2, ..., w1023}
acquisition date = YYYY-MM-DD
acquisition time = HH:MM:SS
exposure time = {us}
gain = {db}
pixel format = {Mono8|Mono10|Mono12}
```

Data type codes: `1` = uint8 (Mono8), `12` = uint16 (Mono10/12).

`lines` is updated to the final count when the file is closed. Written as `0` initially, then the .hdr is rewritten on `close()`.

Wavelengths: loaded from calibration CSV if available; otherwise `np.linspace(900, 1700, 1024)` (SWIR range placeholder).

## Binary Layout (.dat) — BIL Interleave

For each acquired line (one camera frame = one push-broom line):

```
[band_0_all_1280_samples][band_1_all_1280_samples]...[band_1023_all_1280_samples]
```

- Each band row: 1280 values × bytes_per_pixel
- uint8: 1 byte/pixel → 1280 bytes per band row
- uint16: 2 bytes/pixel, little-endian → 2560 bytes per band row
- Total per line: 1024 × 1280 × bpp bytes

Write using: `frame.astype(dtype).tobytes()` where frame shape is `(1024, 1280)`.

## Class API

```python
class EnviWriter:
    def open(self, path: str, pixel_format: str,
             wavelengths: np.ndarray | None = None,
             metadata: dict | None = None) -> None
    def write_line(self, frame: np.ndarray) -> None
        """Append one line (frame shape (1024,1280)) to .dat file."""
    def close(self) -> None
        """Flush .dat, rewrite .hdr with final line count."""
    def __enter__ / __exit__: context manager support
    @property
    def lines_written(self) -> int
    @property
    def bytes_written(self) -> int
```

## Usage Pattern

```python
writer = EnviWriter()
writer.open("data/session_20240101_120000", pixel_format="Mono12", wavelengths=wl)
for frame, meta in acquisition:
    writer.write_line(frame)
writer.close()
```
