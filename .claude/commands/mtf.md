# MTF Calculation

Implement or review `src/analysis/mtf.py` using the following algorithm (ported from `mtf-calc-example/OCWidget.cpp`).

## Formula

Per-direction MTF:

```
MTF = ((A - B) / (A + B)) * π/4
```

- `A = dnCenter - blackLevel` — center pixel DN minus noise floor
- `B = dnNeighbor - blackLevel` — adjacent pixel DN minus noise floor
- `blackLevel` — user-set noise floor (spinbox, default 0)

## Four Directions

Given selected pixel `(x, y)` on the frame array (shape `(1024, 1280)`):

| Direction | Neighbor coords | Boundary check |
|---|---|---|
| above | `frame[y-1, x]` | invalid if `y == 0` |
| below | `frame[y+1, x]` | invalid if `y == rows-1` |
| left  | `frame[y, x-1]` | invalid if `x == 0` |
| right | `frame[y, x+1]` | invalid if `x == cols-1` |

Out-of-bounds directions → `float('nan')`.

Mean MTF = `(above + below + left + right) / 4` (only over valid directions).

## N-Frame Averaging

- User selects averaging count: 1, 5, or 10 frames (每1/5/10帧计算)
- Accumulate directional MTF sums over N frames, then divide and display
- Reset accumulator after each display update
- If averaging count changed by user → reset immediately

## Class API

```python
class MTFCalculator:
    def __init__(self): ...
    def set_avg_count(self, n: int)          # 1, 5, or 10
    def set_black_level(self, level: float)
    def reset(self)
    def update(self, frame: np.ndarray, x: int, y: int) -> dict | None:
        """
        Call once per frame.
        Returns dict when avg_count frames accumulated, else None.
        Return: {'above': float, 'below': float, 'left': float,
                 'right': float, 'mean': float}
        NaN for invalid directions.
        """
```

## DN Neighborhood Table

The 光校 control panel shows a 9×9 QTableWidget of DN values centered at `(x, y)`:
- Rows span `y-4` to `y+4` (spectral axis)
- Columns span `x-4` to `x+4` (spatial axis)
- Out-of-bounds cells show `"-"`
- dnCenter = `frame[y, x]`, dnAbove = `frame[y-1, x]`, etc. (read from table row/col 4±1)

## Display in UI (control_panel.py)

MTF values shown as cross pattern of QLabel/QLineEdit:

```
          [above]
[left]  [mean]  [right]
          [below]
```

Values formatted to 3 decimal places. "无效值" shown for NaN.
