"""Tests for AcquisitionWorker."""

import time

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication

from src.device.mock_device import MockDevice
from src.data.acquisition import AcquisitionWorker


@pytest.fixture(scope="module")
def app():
    a = QCoreApplication.instance()
    if a is None:
        a = QCoreApplication([])
    return a


class TestAcquisitionWorker:
    def test_frame_flow(self, app, qtbot):
        """Verify frames flow from device through worker into ping-pong buffer."""
        dev = MockDevice()
        dev.initialize()
        worker = AcquisitionWorker(dev)

        dev.start()
        worker.start()
        qtbot.wait(300)

        # Poll the ping-pong buffer — at least one frame should be available
        result = worker.frame_buffer.pong()
        worker.stop()
        dev.stop()

        assert result is not None
        frame, meta = result
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (1024, 1280)

    def test_stats_emitted(self, app, qtbot):
        """Verify stats are emitted."""
        dev = MockDevice()
        dev.initialize()
        worker = AcquisitionWorker(dev)

        stats_list = []
        worker.stats_updated.connect(lambda s: stats_list.append(s))

        dev.start()
        worker.start()
        qtbot.wait(500)
        worker.stop()
        dev.stop()

        assert len(stats_list) > 0
        stats = stats_list[-1]
        assert "fps" in stats
        assert "frame_count" in stats
        assert stats["frame_count"] > 0

    def test_nuc_identity(self, app, qtbot):
        """Without NUC loaded, frames should pass through as float32."""
        dev = MockDevice()
        dev.initialize()
        worker = AcquisitionWorker(dev)

        assert not worker.nuc.is_loaded()

        dev.start()
        worker.start()
        qtbot.wait(200)

        result = worker.frame_buffer.pong()
        worker.stop()
        dev.stop()

        assert result is not None
        frame, _ = result
        # NUC not loaded → frame is float32 (identity transform)
        assert frame.dtype == np.float32
