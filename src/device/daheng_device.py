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

from src.device.device_interface import DEFAULT_PIXEL_FORMAT, DeviceInterface

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
        self._pixel_format: str = DEFAULT_PIXEL_FORMAT
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

            # Select the sensor ADC depth when the camera exposes that
            # feature, then select the matching wire pixel format.
            self._apply_sensor_bit_depth()
            # Configure the camera before stream_on(). Do not rely on the
            # camera's persisted/user-set format, because the frame parser and
            # downstream storage are configured for unpacked Mono12 samples.
            self._apply_pixel_format(DEFAULT_PIXEL_FORMAT)

            # Set payload size for GigE cameras (critical for proper data transfer)
            try:
                payload_size = self._remote_feature.get_int_feature("PayloadSize").get()
                logger.info("Payload size: %d bytes", payload_size)
            except Exception as e:
                logger.warning("Could not read PayloadSize (may not be GigE camera): %s", e)

            # Set exposure
            self._remote_feature.get_float_feature("ExposureTime").set(self._exposure_us)

            # Set gain
            self._remote_feature.get_float_feature("Gain").set(self._gain_db)

            # Software trigger mode
            self._remote_feature.get_enum_feature("TriggerMode").set("On")
            self._remote_feature.get_enum_feature("TriggerSource").set("Software")
            self._trigger_cmd = self._remote_feature.get_command_feature("TriggerSoftware")

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

        # Register capture callback — emits raw mono numpy array.
        # gxipy rejects bound methods (isinstance FunctionType check),
        # so wrap in a lambda like the reference example does.
        self._data_stream.register_capture_callback(
            lambda raw_image: self._capture_callback(raw_image))
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
        if fmt != DEFAULT_PIXEL_FORMAT:
            raise ValueError(
                f"This application requires {DEFAULT_PIXEL_FORMAT}; got {fmt}")

        try:
            self._apply_pixel_format(fmt)
            logger.info("Pixel format set to %s", self._pixel_format)
        except Exception as e:
            self._last_error = str(e)
            logger.error("Failed to set pixel format: %s", e)
            raise

    def _apply_pixel_format(self, fmt: str) -> None:
        """Set and read back the camera pixel format before acquisition."""
        if fmt != DEFAULT_PIXEL_FORMAT:
            raise ValueError(
                f"This application requires {DEFAULT_PIXEL_FORMAT}; got {fmt}")
        if self._remote_feature is None:
            self._pixel_format = fmt
            return

        feature = self._remote_feature.get_enum_feature("PixelFormat")
        feature.set(fmt)
        _, actual_format = feature.get()
        if actual_format != fmt:
            raise RuntimeError(
                f"Camera rejected pixel format {fmt}; actual format is "
                f"{actual_format}")
        self._pixel_format = actual_format

    def _apply_sensor_bit_depth(self) -> None:
        """Configure and verify the camera's 12-bit sensor ADC mode."""
        if self._remote_feature is None:
            return

        feature_name = "SensorBitDepth"
        try:
            if not self._remote_feature.is_implemented(feature_name):
                logger.info(
                    "%s is not exposed; relying on PixelFormat=Mono12",
                    feature_name,
                )
                return

            feature = self._remote_feature.get_enum_feature(feature_name)
            if self._remote_feature.is_writable(feature_name):
                feature.set(12)

            actual_depth, actual_symbolic = feature.get()
            if int(actual_depth) != 12:
                raise RuntimeError(
                    f"Camera SensorBitDepth is {actual_symbolic} "
                    f"({actual_depth}), expected 12-bit")
            logger.info("Sensor ADC bit depth set to 12-bit")
        except Exception:
            # A camera that exposes this node but cannot be confirmed at
            # 12-bit must not enter acquisition with an unknown ADC mode.
            raise

    def get_pixel_format(self) -> str:
        """Return the camera's actual format when the device is connected."""
        if self._remote_feature is not None:
            try:
                _, actual_format = (
                    self._remote_feature
                    .get_enum_feature("PixelFormat")
                    .get()
                )
                self._pixel_format = actual_format
            except Exception as e:
                logger.debug("Could not read camera pixel format: %s", e)
        return self._pixel_format

    def get_frame_shape(self) -> tuple[int, int]:
        if self._remote_feature:
            try:
                width = self._remote_feature.get_int_feature("Width").get()
                height = self._remote_feature.get_int_feature("Height").get()
                return (height, width)
            except Exception:
                pass
        return (1024, 1280)  # Default for MER3-138-136G3M-P-SWIR

    def get_exposure(self) -> float:
        return self._exposure_us

    def get_gain(self) -> float:
        return self._gain_db

    def get_temperature(self) -> float | None:
        """Read the camera temperature from the optional Daheng feature.

        Not every camera model or firmware exposes ``DeviceTemperature``;
        keep that case non-fatal so the rest of the device remains usable.
        """
        if self._remote_feature is None:
            return None

        try:
            feature_name = "DeviceTemperature"
            if not self._remote_feature.is_implemented(feature_name):
                return None
            if not self._remote_feature.is_readable(feature_name):
                return None
            return float(self._remote_feature.get_float_feature(feature_name).get())
        except Exception as e:
            logger.debug("Could not read camera temperature: %s", e)
            return None

    def _capture_callback(self, raw_image) -> None:
        """SDK capture callback — extract raw mono numpy array and emit."""
        if raw_image is None or not self._running:
            return

        try:
            # Check frame status
            if raw_image.get_status() != 0:
                logger.warning("Frame status error: %d", raw_image.get_status())
                if self._running and self._trigger_cmd:
                    self._trigger_cmd.send_command()
                return

            # Get actual dimensions from frame
            height = raw_image.get_height()
            width = raw_image.get_width()
            pixel_format = raw_image.get_pixel_format()

            # The production path is intentionally strict: Mono12 is the
            # format configured during initialize(), and packed formats need a
            # separate unpacking path that this raw-frame pipeline does not use.
            if pixel_format != GxPixelFormatEntry.MONO12:
                logger.error(
                    "Unexpected camera pixel format %s; expected Mono12",
                    pixel_format,
                )
                if self._running and self._trigger_cmd:
                    self._trigger_cmd.send_command()
                return

            numpy_array = raw_image.get_numpy_array()
            if numpy_array is None:
                logger.warning("Failed to get numpy array for Mono12 frame")
                if self._running and self._trigger_cmd:
                    self._trigger_cmd.send_command()
                return
            if numpy_array.size != height * width:
                logger.error(
                    "Unexpected Mono12 buffer size: got %d samples, expected %d",
                    numpy_array.size,
                    height * width,
                )
                if self._running and self._trigger_cmd:
                    self._trigger_cmd.send_command()
                return
            frame = numpy_array.reshape(height, width).astype(np.uint16, copy=False)

            metadata = {
                "frame_id": raw_image.get_frame_id(),
                "timestamp": time.time(),
                "pixel_format": DEFAULT_PIXEL_FORMAT,
                "exposure_us": self._exposure_us,
                "gain_db": self._gain_db,
                "width": width,
                "height": height,
            }
            self._frame_id_counter += 1

            self.frame_acquired.emit(frame, metadata)

            # Send next software trigger to continue the chain
            if self._running and self._trigger_cmd:
                self._trigger_cmd.send_command()

        except Exception as e:
            logger.error("Capture callback error: %s", e)
            if self._running and self._trigger_cmd:
                self._trigger_cmd.send_command()
