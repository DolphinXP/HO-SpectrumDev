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
        """Verify frames flow from device through worker."""
        dev = MockDevice()
        dev.initialize()
        worker = AcquisitionWorker(dev)

        received = []
        worker.frame_ready.connect(lambda f, m: received.append((f, m)))

        dev.start()
        worker.start()
        qtbot.wait(300)
        worker.stop()
        dev.stop()

        assert len(received) > 0
        frame, meta = received[0]
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
        qtbot.wait(300)
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

        received = []
        worker.frame_ready.connect(lambda f, m: received.append(f))

        dev.start()
        worker.start()
        qtbot.wait(200)
        worker.stop()
        dev.stop()

        assert len(received) > 0
        # NUC not loaded → frame is float32 (identity transform)
        assert received[0].dtype == np.float32
