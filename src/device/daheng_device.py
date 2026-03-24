"""Real Daheng camera device wrapper implementing DeviceInterface.

Wraps the gxipy SDK to emit raw mono numpy arrays (not RGB QImage).
Uses software trigger mode by default.
"""

import logging
import os
import sys
import time
from ctypes import addressof, c_ubyte

import numpy as np
from PySide6.QtCore import QObject

from src.device.device_interface import DeviceInterface

logger = logging.getLogger("specdev.device")

# Lazy imports for gxipy — only available when SDK is installed
gx = None
GxPixelFormatEntry = None
DxValidBit = None


def _ensure_sdk():
    global gx, GxPixelFormatEntry, DxValidBit
    if gx is None:
        device_dir = os.path.dirname(__file__)
        if device_dir not in sys.path:
            sys.path.insert(0, device_dir)

        import gxipy as _gx
        from gxipy.gxidef import GxPixelFormatEntry as _pf, DxValidBit as _vb
        gx = _gx
        GxPixelFormatEntry = _pf
        DxValidBit = _vb


def get_camera_list() -> list[dict]:
    """Return list of detected Daheng camera info dicts."""
    _ensure_sdk()
    device_manager = gx.DeviceManager()
    dev_num, dev_info_list = device_manager.update_all_device_list()
    if dev_num == 0:
        return []
    return dev_info_list


class DahengDevice(DeviceInterface):
    """Daheng MER3-138-136G3M-P-SWIR camera wrapper.

    Emits raw mono numpy arrays of shape (1024, 1280) via frame_acquired
    signal, unlike the reference implementation which converts to RGB QImage.
    """

    def __init__(self, serial_number: str = "", parent: QObject | None = None) -> None:
        super().__init__(parent)
        _ensure_sdk()

        self._sn = serial_number
        self._device_manager = gx.DeviceManager()
        self._camera = None
        self._remote_feature = None
        self._data_stream = None
        self._trigger_cmd = None

        self._exposure_us: float = 10000.0
        self._gain_db: float = 0.0
        self._pixel_format: str = "Mono8"
        self._running: bool = False
        self._frame_id_counter: int = 0
        self._last_error: str = ""

    def initialize(self) -> bool:
        try:
            self._last_error = ""
            # Auto-detect if no serial number given
            if not self._sn:
                dev_num, dev_info_list = self._device_manager.update_all_device_list()
                if dev_num == 0:
                    self._last_error = "No Daheng cameras found"
                    logger.error(self._last_error)
                    return False
                self._sn = dev_info_list[0].get("sn", "")
                logger.info("Auto-detected camera SN: %s", self._sn)

            self._camera = self._device_manager.open_device_by_sn(self._sn)
            self._remote_feature = self._camera.get_remote_device_feature_control()
            self._data_stream = self._camera.data_stream[0]

            # Set exposure
            self._remote_feature.get_float_feature(
                "ExposureTime").set(self._exposure_us)

            # Software trigger mode
            self._remote_feature.get_enum_feature("TriggerMode").set("On")
            self._remote_feature.get_enum_feature(
                "TriggerSource").set("Software")
            self._trigger_cmd = self._remote_feature.get_command_feature(
                "TriggerSoftware")

            logger.info("DahengDevice initialized: SN=%s", self._sn)
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error("DahengDevice initialization failed: %s", e)
            return False

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> None:
        if self._camera is None:
            logger.error("Cannot start — device not initialized")
            return

        self._running = True
        self._frame_id_counter = 0

        # Register capture callback — emits raw mono numpy array
        self._data_stream.register_capture_callback(self._capture_callback)
        self._camera.stream_on()

        # Initial trigger to start the chain
        time.sleep(0.1)
        self._trigger_cmd.send_command()
        logger.info("DahengDevice acquisition started")

    def stop(self) -> None:
        self._running = False
        if self._camera:
            try:
                self._camera.stream_off()
                self._data_stream.unregister_capture_callback()
            except Exception as e:
                logger.warning("Error stopping camera: %s", e)
        logger.info("DahengDevice acquisition stopped")

    def close(self) -> None:
        self.stop()
        if self._camera:
            try:
                self._camera.close_device()
            except Exception as e:
                logger.warning("Error closing device: %s", e)
            self._camera = None
        self._data_stream = None
        logger.info("DahengDevice closed")

    def set_exposure(self, us: float) -> None:
        self._exposure_us = us
        if self._remote_feature:
            try:
                self._remote_feature.get_float_feature("ExposureTime").set(us)
                logger.info("Exposure set to %.1f µs", us)
            except Exception as e:
                logger.error("Failed to set exposure: %s", e)

    def set_gain(self, db: float) -> None:
        self._gain_db = db
        if self._remote_feature:
            try:
                self._remote_feature.get_float_feature("Gain").set(db)
                logger.info("Gain set to %.1f dB", db)
            except Exception as e:
                logger.error("Failed to set gain: %s", e)

    def set_pixel_format(self, fmt: str) -> None:
        self._pixel_format = fmt
        if self._remote_feature:
            try:
                self._remote_feature.get_enum_feature("PixelFormat").set(fmt)
                logger.info("Pixel format set to %s", fmt)
            except Exception as e:
                logger.error("Failed to set pixel format: %s", e)

    def get_frame_shape(self) -> tuple[int, int]:
        return (1024, 1280)

    def get_exposure(self) -> float:
        return self._exposure_us

    def get_gain(self) -> float:
        return self._gain_db

    def get_pixel_format(self) -> str:
        return self._pixel_format

    def _capture_callback(self, raw_image) -> None:
        """SDK capture callback — extract raw mono numpy array and emit."""
        if raw_image is None or not self._running:
            return

        try:
            numpy_array = raw_image.get_numpy_array()
            if numpy_array is None:
                logger.warning("Failed to get numpy array from raw_image")
                return

            # Ensure shape is (1024, 1280) — raw mono frame
            # The SDK returns the array in the native pixel shape
            frame = numpy_array.reshape(1024, 1280)

            # Determine dtype based on pixel format
            pixel_format = raw_image.get_pixel_format()
            if pixel_format in (GxPixelFormatEntry.MONO10, GxPixelFormatEntry.MONO12):
                frame = frame.astype(np.uint16)
            else:
                frame = frame.astype(np.uint8)

            metadata = {
                "frame_id": self._frame_id_counter,
                "timestamp": time.time(),
                "pixel_format": self._pixel_format,
                "exposure_us": self._exposure_us,
                "gain_db": self._gain_db,
                "width": 1280,
                "height": 1024,
            }
            self._frame_id_counter += 1

            self.frame_acquired.emit(frame, metadata)

            # Send next software trigger to continue the chain
            if self._running and self._trigger_cmd:
                self._trigger_cmd.send_command()

        except Exception as e:
            logger.error("Capture callback error: %s", e)
