# Non-Uniformity Correction (NUC)

Implement or review `src/data/nuc.py`.

## Algorithm

Per-pixel linear correction applied to every raw frame:

```
output_pixel = A[row, col] * raw_pixel + B[row, col]
```

- `raw_pixel` — raw DN value from camera (uint8 or uint16)
- `A` — gain coefficient array, shape `(1024, 1280)`, dtype float32
- `B` — offset coefficient array, shape `(1024, 1280)`, dtype float32
- Output dtype: float32 (caller clips/converts as needed for display)

Applied element-wise via numpy: `output = A * frame.astype(np.float32) + B`

## Coefficient File Formats

Both A and B files must have shape `(1024, 1280)`. Supported formats (auto-detected by extension):

| Extension | Format |
|---|---|
| `.npy` | numpy save file — `np.load(path)` |
| `.csv` | CSV, 1024 rows × 1280 columns — `np.loadtxt(path, delimiter=',')` |
| `.bin` / `.raw` | Raw binary float32, row-major — `np.fromfile(path, dtype=np.float32).reshape(1024, 1280)` |

## Class API

```python
class NUCProcessor:
    def load(self, a_path: str, b_path: str) -> None:
        """Load A and B coefficient files. Raises ValueError if shape mismatch."""

    def unload(self) -> None:
        """Clear loaded coefficients."""

    def is_loaded(self) -> bool:
        """True if A and B are loaded and shape-validated."""

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply NUC. Returns float32 array shape (1024, 1280).
        If not loaded, returns frame.astype(np.float32) unchanged (identity).
        """
```

## UI Integration

- Settings dialog has "加载NUC系数" section with two file pickers: A文件, B文件
- Status shown in status bar: "NUC: 已加载" / "NUC: 未加载"
- NUC applied in `AcquisitionWorker` before emitting `frame_acquired`
- Log when loaded: `logger.info("NUC loaded: A=%s B=%s shape=%s", a_path, b_path, A.shape)`
- Log when applied per-frame at DEBUG level (not INFO — too frequent)
