# Add New Analysis Module

Use this skill when adding a new optical/spectral analysis algorithm to the app.

## Pattern

All analysis modules live in `src/analysis/`. They follow this pattern:

1. **Pure numpy computation** — no Qt imports, no UI code
2. **Stateless or minimal state** — accept frame array + params, return result
3. **Pluggable** — UI calls the module; the module doesn't know about UI
4. **Well-logged** — use `logging.getLogger("gpy4.analysis")`

## Template

```python
# src/analysis/my_analysis.py
import logging
import numpy as np

logger = logging.getLogger("gpy4.analysis")


class MyAnalysis:
    def __init__(self):
        self._param = None

    def configure(self, **kwargs) -> None:
        """Set parameters. Called from settings dialog."""
        logger.debug("MyAnalysis configured: %s", kwargs)
        self._param = kwargs.get("param", default_value)

    def compute(self, frame: np.ndarray, x: int, y: int) -> dict:
        """
        Args:
            frame: shape (1024, 1280), uint8 or uint16
            x: selected spatial pixel (0-1279)
            y: selected spectral band (0-1023)
        Returns:
            dict of named results, float values, NaN if invalid
        """
        logger.debug("MyAnalysis.compute x=%d y=%d", x, y)
        try:
            result = ...  # your algorithm here
            logger.info("MyAnalysis result: %s", result)
            return result
        except Exception:
            logger.exception("MyAnalysis.compute failed")
            return {}
```

## Integration Checklist

1. Create `src/analysis/my_analysis.py` using template above
2. Instantiate in `main_window.py`: `self.my_analysis = MyAnalysis()`
3. Call in the appropriate slot (e.g., `_on_pixel_selected(x, y)`)
4. Display results in the relevant UI widget (optical_cal_panel or new panel)
5. Add settings to `src/utils/config.py` if configurable
6. Write test in `tests/test_my_analysis.py` using synthetic frame data

## Existing Modules

| Module | Class | Trigger |
|---|---|---|
| `src/analysis/mtf.py` | `MTFCalculator` | every frame, at selected (x,y) |
| `src/analysis/spectral.py` | `SpectralAnalyzer` | on pixel selection change |
| `src/data/nuc.py` | `NUCProcessor` | every frame in acquisition worker |
