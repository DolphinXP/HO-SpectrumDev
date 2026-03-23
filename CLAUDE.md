# Hyperspectral Camera Ground Testing Application (地检软件)

## Project Overview

A Python/PySide6 desktop application for controlling a Daheng Imaging MER3-138-136G3M-P-SWIR SWIR hyperspectral push-broom (line-scan) camera. Used by optical engineers for alignment and calibration (MTF testing, spectral testing). Provides real-time display, per-pixel DN inspection, non-uniformity correction (NUC), raw/ENVI data saving, and extensible analysis modules.

## Device Specifications — Daheng Imaging MER3-138-136G3M-P-SWIR

| Parameter | Value |
|---|---|
| Model | MER3-138-136G3M-P-SWIR |
| Sensor | Sony IMX990 Global Shutter CMOS |
| Resolution | 1280(H) × 1024(V) |
| Target size | 1/2" |
| Pixel size | 5µm × 5µm |
| Frame rate | 72.4 fps @ 1280×1024; up to 135.54 fps BPP8 high-speed mode |
| ADC / Pixel depth | 8-bit, 10-bit, 12-bit |
| Pixel format | Mono8 / Mono10 / Mono12 |
| SNR | 50.76 dB |
| Exposure | Min: 3µs–100µs (step 1µs); Standard: 13µs–1s (step 1 line period) |
| Gain | 0–24 dB, default 0 dB, step 0.1 dB |
| Binning | 1×1, 1×2, 2×1, 2×2 |
| Subsampling | 1×1, 2×2 |
| Trigger | External trigger, software trigger |
| Acquisition modes | Single frame, continuous, soft trigger, external trigger |
| Flip | Horizontal, vertical |
| I/O | 1× opto-isolated input, 2× bidirectional GPIO |
| Data interface | 2.5 GigE |
| Power | PoE (IEEE 802.3af) or 12VDC–24VDC |
| Power consumption | < 5W @ 12V / PoE |
| Operating temp | 0°C – +50°C |

**Line-scan axes**: 1280 = spatial pixels (across slit), 1024 = spectral bands per line

**SDK**: Daheng Galaxy SDK — `gxipy` Python package (located in `daheng-example/gxipy/`)

## Project Structure

```
gpy4/
├── main.py                          # Entry point (--mock, --debug flags)
├── requirements.txt
├── CLAUDE.md
├── logs/                            # Rotating log files (auto-created)
├── daheng-example/
│   ├── daheng_camera.py             # Reference implementation (DO NOT MODIFY)
│   └── gxipy/                       # Daheng SDK Python bindings
├── src/
│   ├── __init__.py
│   ├── device/
│   │   ├── device_interface.py      # Abstract base class (DeviceInterface)
│   │   ├── mock_device.py           # Simulated device for dev/testing
│   │   ├── daheng_device.py         # Real Daheng camera wrapper
│   │   └── peripheral_interface.py  # Conveyor/light stub (future)
│   ├── data/
│   │   ├── acquisition.py           # QThread acquisition worker
│   │   ├── nuc.py                   # NUC processor (pluggable placeholder)
│   │   ├── envi_writer.py           # ENVI BIL .hdr + .dat writer
│   │   ├── raw_writer.py            # Raw binary frame writer + JSON sidecar
│   │   └── storage.py               # Session/file management
│   ├── analysis/
│   │   ├── mtf.py                   # MTF calculator (pluggable placeholder)
│   │   └── spectral.py              # Spectral profiler
│   ├── ui/
│   │   ├── main_window.py           # QMainWindow — full layout + signal wiring
│   │   ├── styles.qss               # Stylesheet (light/neutral theme)
│   │   └── widgets/
│   │       ├── image_display.py     # Image view with toolbar (图像/DN/光校 tabs)
│   │       ├── dn_table_widget.py   # Per-pixel DN value grid (DN tab)
│   │       ├── stats_panel.py       # 数据统计 right-panel table
│   │       ├── aux_data_panel.py    # 辅助数据 right-panel table
│   │       ├── optical_cal_panel.py # 光校 bottom-left (MTF, pixel coords, DN neighborhood)
│   │       └── spectrum_graph.py    # Reusable pyqtgraph plot (×4 instances)
│   └── utils/
│       ├── config.py                # QSettings persistence
│       └── logger.py                # Logging configuration
└── tests/
    ├── test_device.py
    ├── test_acquisition.py
    ├── test_envi_writer.py
    └── test_spectral.py
```

## Key Technical Decisions

- **UI language**: Chinese (Simplified) — all labels, menus, tooltips in Chinese
- **UI framework**: PySide6 with QSplitter-based layout
- **Plotting**: pyqtgraph (not matplotlib) — required for real-time performance at 72+ FPS
- **Threading**: QThread + signals/slots; never call UI methods from worker threads
- **Frame format**: numpy arrays shape `(1024, 1280)` — rows=spectral bands, cols=spatial pixels; uint8 (Mono8) or uint16 (Mono10/12)
- **Storage**: two independent modes — ENVI BIL for hyperspectral cubes, raw binary for frame sequences
- **Device abstraction**: `DeviceInterface` ABC — swap mock ↔ real SDK without touching UI
- **Logging**: named loggers per module (`gpy4.device`, `gpy4.acquisition`, etc.), rotating file + console

## Device Data Model

- Frame shape: `(1024, 1280)` numpy array, axis-0 = spectral bands (1024), axis-1 = spatial pixels (1280)
- Pixel format: Mono8 → uint8; Mono10/Mono12 → uint16
- Wavelength axis: 1024-element float array (nm), loaded from calibration .csv file
- Frame metadata dict: `{frame_id, timestamp, pixel_format, exposure_us, gain_db, width, height}`

## UI Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Toolbar: 开始 | 停止 | 查看记录 | 开始回放 | 开始存储 | 停止存储 | 光校 | 设置 | 关于 | Exit │
├───────────────────────────────────────────────┬─────────────────────────────┤
│  Image Display Widget (Left)                  │  Right Panels (Stack)       │
│  Button Bar: 保存图片 | 重置缩放               │  1. 数据统计 (StatsPanel)   │
│  Level Control: [min] - [max] [应用] [原始]   │     (FPS, MiB/s, 丢帧, 队列)│
│  Info Bar: X:__ Y:__ DN:__ Zoom:__            ├─────────────────────────────┤
│                                               │  2. 辅助数据 (AuxDataPanel) │
│  [Image Plot Area]                            │     (FrameID, Exposure, ...)│
├─────────────────┬─────────────────────────────┴─────────────────────────────┤
│ 光校 Panel      │  Spectral/Spatial Graphs (Scroll Area)                    │
│ (Bottom-Left)   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│ X / Y Inputs    │  │ 临近空间 │ │ 临近光谱 │ │ 全域空间 │ │ 全域光谱 │      │
│ 定位最大DN      │  │ (行)     │ │ (列)     │ │ (行)     │ │ (列)     │      │
│ MTF Results     │  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│ DN Neighborhood │                                                           │
└─────────────────┴───────────────────────────────────────────────────────────┘
│ Status bar: 设备: -- Connection | NUC: Status | 存储: Status                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### UI Features

- **Toolbar (主工具栏)**: Provides primary state control (start/stop/save). The "光校" button toggles the visibility of the entire bottom section.
- **Image Display (图像显示)**: Driven by `ImageDisplayWidget`. Uses `pyqtgraph.ImageView`. Supports manual DN range (Levels) adjustment and mouse-driven zoom/pan.
- **Stats & Aux (统计与辅助)**: Right-side panels showing real-time performance and frame-header metadata.
- **Optical Calibration (光校控制)**: Left panel in the bottom area. Allows programmatic navigation to peak DN and displays MTF results.
- **Spectrum Graphs (光谱/空间曲线)**: Four synchronized charts showing profiles across spectral and spatial dimensions.

## Data Save Modes

### ENVI BIL (hyperspectral cube)
Files: `<session>_YYYYMMDD_HHMMSS.dat` + `.hdr`

```
ENVI
samples = 1280
lines = N              (accumulated push-broom lines)
bands = 1024
data type = 1          (uint8) or 12 (uint16)
interleave = bil
byte order = 0
wavelength units = nm
wavelength = {w0, w1, ..., w1023}
```

Each line written as (1024, 1280) array in band-interleaved order.

### Raw Binary
Files: `<session>_YYYYMMDD_HHMMSS.raw` + `.json` sidecar

JSON sidecar: `{frame_count, width, height, pixel_format, dtype, exposure_us, gain_db, fps}`
Binary: concatenated raw numpy frames, one after another.

## Logging

- File: `logs/app_YYYYMMDD.log` — DEBUG level, rotating 10MB × 5 backups
- Console: INFO level (DEBUG if `--debug` flag)
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Named loggers: `gpy4.device`, `gpy4.acquisition`, `gpy4.storage`, `gpy4.ui`, `gpy4.analysis`
- Log all: device events, parameter changes, frame drops, file open/close, write stats, analysis results

## Analysis Modules

Detailed algorithm specs are in project skills (`.claude/commands/`):

| Skill | Command | What it covers |
|---|---|---|
| MTF calculation | `/mtf` | Formula, 4-direction calc, N-frame averaging, DN neighborhood table, UI layout |
| NUC correction | `/nuc` | Per-pixel `A*x+B`, coefficient file formats, class API, UI integration |
| ENVI format | `/envi` | Full .hdr spec, BIL binary layout, class API, usage pattern |
| Acquisition debug | `/debug-acquisition` | Frame drops, UI freeze, memory leak, log analysis |
| Add new analysis | `/add-analysis` | Template and checklist for new optical analysis modules |

### Quick Reference

**MTF**: `MTF = ((dnCenter−BL) − (dnNeighbor−BL)) / ((dnCenter−BL) + (dnNeighbor−BL)) × π/4`
Four directions (above/below/left/right), averaged over 1/5/10 frames. → `src/analysis/mtf.py`

**NUC**: `output = A * raw_pixel + B` per pixel, A/B arrays shape (1024,1280). → `src/data/nuc.py`

**Spectral profiles**: near spatial ±10px, near spectral ±10 bands, full row, full column. → `src/analysis/spectral.py`

## Peripheral Control (Future Extension)

`src/device/peripheral_interface.py` defines abstract `ConveyorController` and `LightController` classes. All methods are stubs. Connect via serial port or GPIO — implementation deferred.

## Development Conventions

- Python 3.10+, type hints on all public methods
- PySide6 signals as class attributes: `frame_acquired = Signal(np.ndarray, dict)`
- No direct UI calls from worker threads — always use signals
- Config: `QSettings("gpy4", "HyperspectralApp")`, keys in `snake_case`
- pyqtgraph `PlotWidget` embedded in layouts (not standalone windows)
- `daheng-example/` is reference only — do not modify those files

## SDK Integration

`src/device/daheng_device.py` adapts `daheng-example/daheng_camera.py`:
- Add `daheng-example/` to `sys.path` in `main.py` to access `gxipy`
- Reuse: `gx.DeviceManager()`, `open_device_by_sn()`, capture callback, pixel format constants
- Change: emit raw Mono numpy array (not RGB QImage), implement `DeviceInterface` ABC
- Trigger mode: software trigger by default (matches existing example)

## Environment

- Conda: `C:\miniconda3`, environment name: `gpy4`
- Python: `C:\miniconda3\envs\gpy4\python.exe` (Python 3.10)
- Always use the full path to the conda Python for running scripts and tests
- Activate: `conda activate gpy4` (or use full path directly)

## Running

```bash
C:\miniconda3\envs\gpy4\python.exe main.py             # real camera
C:\miniconda3\envs\gpy4\python.exe main.py --mock      # simulated device
C:\miniconda3\envs\gpy4\python.exe main.py --debug     # verbose console logging
```

## Testing

```bash
C:\miniconda3\envs\gpy4\python.exe -m pytest tests/ -v
```

All tests use `MockDevice` — no hardware required.
