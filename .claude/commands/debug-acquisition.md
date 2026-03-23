# Debug Acquisition Pipeline

Use this skill when diagnosing issues with camera data flow, dropped frames, or UI freezes.

## Diagnostic Checklist

### 1. Frame Drop / FPS Lower Than Expected
```bash
# Check log for frame drop warnings
grep "frame drop\|dropped\|timeout\|buffer overflow" logs/app_*.log | tail -20
```
- Look for `gpy4.acquisition` logger warnings
- Check buffer utilization in stats panel — if > 80%, increase buffer size in settings
- Software trigger mode: verify `send_command()` is called after each callback
- Check if NUC is taking too long: log time inside `NUCProcessor.apply()`

### 2. UI Freeze During Acquisition
- Root cause: something blocking the main thread
- Checklist:
  - Is `frame_acquired` signal connected to a slot that does heavy work synchronously?
  - Is `EnviWriter.write_line()` being called from the UI thread? → must be in worker
  - Is `DNTableWidget.update()` being called every frame? → throttle to 5 FPS max
  - Check `QApplication.processEvents()` calls — these are code smells

### 3. No Frames Received (Mock or Real Camera)
- MockDevice: check QTimer is running, verify `frame_ready` signal connections
- Real camera: check `gxipy` initialization log in `gpy4.device` logger
- Verify `data_stream.register_capture_callback()` was called after `stream_on()`
- Check network: `ping <camera_ip>`, verify 2.5GigE adapter MTU = 9000 (jumbo frames)

### 4. Memory Leak During Long Acquisition
- numpy arrays must not be retained across frames in UI widgets
- `ImageDisplay` should replace its internal array reference, not append
- `RawWriter`: verify file handle is flushed periodically, not buffering in RAM
- Profile with: `python -m tracemalloc main.py --mock`

## Log Analysis Commands

```bash
# Show all ERROR and WARNING lines
grep -E "ERROR|WARNING" logs/app_$(date +%Y%m%d).log

# Show acquisition stats over time
grep "stats_updated\|FPS\|MBps" logs/app_$(date +%Y%m%d).log

# Show all device events
grep "gpy4.device" logs/app_$(date +%Y%m%d).log
```

## Thread Verification

All these must run in worker threads (not main thread):
- `AcquisitionWorker` — in `QThread`
- `EnviWriter.write_line()` calls
- `NUCProcessor.apply()` calls
- `MTFCalculator.update()` calls

All these must run in main thread:
- Any `QWidget` method call
- `ImageDisplay.update_image()`
- `SpectrumGraphWidget.update_plot()`
