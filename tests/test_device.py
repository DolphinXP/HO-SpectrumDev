"""Tests for MockDevice."""

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from src.device.mock_device import MockDevice


@pytest.fixture(scope="module")
def app():
    """Ensure a QCoreApplication exists for signal/slot tests."""
    a = QCoreApplication.instance()
    if a is None:
        a = QCoreApplication([])
    return a


class TestMockDevice:
    def test_initialize(self, app):
        dev = MockDevice()
        assert dev.initialize() is True

    def test_frame_shape(self, app):
        dev = MockDevice()
        assert dev.get_frame_shape() == (1024, 1280)

    def test_default_parameters(self, app):
        dev = MockDevice()
        assert dev.get_exposure() == 10000.0
        assert dev.get_gain() == 0.0
        assert dev.get_pixel_format() == "Mono12"

    def test_set_exposure(self, app):
        dev = MockDevice()
        dev.set_exposure(5000.0)
        assert dev.get_exposure() == 5000.0

    def test_set_gain(self, app):
        dev = MockDevice()
        dev.set_gain(12.5)
        assert dev.get_gain() == 12.5

    def test_set_pixel_format(self, app):
        dev = MockDevice()
        dev.set_pixel_format("Mono12")
        assert dev.get_pixel_format() == "Mono12"

    def test_frame_emission(self, app, qtbot):
        """Verify that frames are emitted after start()."""
        dev = MockDevice()
        dev.set_pixel_format("Mono8")
        dev.initialize()

        received = []
        dev.frame_acquired.connect(lambda f, m: received.append((f, m)))

        dev.start()
        qtbot.wait(150)  # Wait for a few frames
        dev.stop()

        assert len(received) > 0

        frame, meta = received[0]
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (1024, 1280)
        assert frame.dtype == np.uint8
        assert "frame_id" in meta
        assert "timestamp" in meta
        assert meta["width"] == 1280
        assert meta["height"] == 1024

    def test_mono12_frame_dtype(self, app, qtbot):
        dev = MockDevice()
        dev.set_pixel_format("Mono12")
        dev.initialize()

        received = []
        dev.frame_acquired.connect(lambda f, m: received.append(f))

        dev.start()
        qtbot.wait(100)
        dev.stop()

        assert len(received) > 0
        assert received[0].dtype == np.uint16

    def test_stop_no_frames(self, app, qtbot):
        dev = MockDevice()
        dev.initialize()

        received = []
        dev.frame_acquired.connect(lambda f, m: received.append(f))

        dev.start()
        dev.stop()

        # Frames emitted from the mock thread before stop() are delivered
        # as queued events — flush them before taking the baseline count.
        qtbot.wait(50)
        count_at_stop = len(received)

        qtbot.wait(100)
        assert len(received) == count_at_stop  # No new frames after stop
