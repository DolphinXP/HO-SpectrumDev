"""Tests for ENVI BIL writer."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.data.envi_writer import EnviWriter


class TestEnviWriter:
    def test_write_and_read_mono8(self, tmp_path):
        """Write Mono8 frames and verify header + binary layout."""
        base = str(tmp_path / "test_session")
        n_frames = 3

        writer = EnviWriter()
        writer.open(base, "Mono8")

        frames = []
        for i in range(n_frames):
            frame = np.random.randint(0, 256, (1024, 1280), dtype=np.uint8)
            writer.write_line(frame)
            frames.append(frame)

        assert writer.lines_written == n_frames
        writer.close()

        # Verify header
        hdr_path = Path(base + ".hdr")
        assert hdr_path.exists()
        hdr_text = hdr_path.read_text(encoding="utf-8")

        assert "ENVI" in hdr_text
        assert "samples = 1280" in hdr_text
        assert f"lines = {n_frames}" in hdr_text
        assert "bands = 1024" in hdr_text
        assert "data type = 1" in hdr_text
        assert "interleave = bil" in hdr_text
        assert "byte order = 0" in hdr_text

        # Verify binary data
        dat_path = Path(base + ".dat")
        assert dat_path.exists()
        expected_bytes = n_frames * 1024 * 1280 * 1  # uint8
        assert dat_path.stat().st_size == expected_bytes

        # Read back and verify content
        raw_data = np.fromfile(str(dat_path), dtype=np.uint8)
        raw_data = raw_data.reshape(n_frames, 1024, 1280)
        for i in range(n_frames):
            np.testing.assert_array_equal(raw_data[i], frames[i])

    def test_write_mono12(self, tmp_path):
        """Write Mono12 frames and verify dtype/size."""
        base = str(tmp_path / "test_12bit")
        writer = EnviWriter()
        writer.open(base, "Mono12")

        frame = np.random.randint(0, 4096, (1024, 1280), dtype=np.uint16)
        writer.write_line(frame)
        writer.close()

        hdr_text = Path(base + ".hdr").read_text()
        assert "data type = 12" in hdr_text

        dat_path = Path(base + ".dat")
        expected_bytes = 1024 * 1280 * 2  # uint16
        assert dat_path.stat().st_size == expected_bytes

    def test_context_manager(self, tmp_path):
        """Verify context manager properly closes files."""
        base = str(tmp_path / "ctx_test")
        with EnviWriter() as writer:
            writer.open(base, "Mono8")
            frame = np.zeros((1024, 1280), dtype=np.uint8)
            writer.write_line(frame)

        # After __exit__, header should have final line count
        hdr_text = Path(base + ".hdr").read_text()
        assert "lines = 1" in hdr_text

    def test_header_omits_wavelengths(self, tmp_path):
        """Verify wavelength information is not written to the header."""
        base = str(tmp_path / "wl_test")

        writer = EnviWriter()
        writer.open(base, "Mono8")
        writer.close()

        hdr_text = Path(base + ".hdr").read_text()
        assert "wavelength = {" not in hdr_text
        assert "wavelength units = nm" not in hdr_text

    def test_wrong_frame_shape_raises(self, tmp_path):
        """Writing a frame with wrong shape should raise ValueError."""
        base = str(tmp_path / "bad_shape")
        writer = EnviWriter()
        writer.open(base, "Mono8")
        writer.write_line(np.zeros((1024, 1280), dtype=np.uint8))

        with pytest.raises(ValueError, match="Frame shape"):
            writer.write_line(np.zeros((512, 640), dtype=np.uint8))

        writer.close()

    def test_double_open_raises(self, tmp_path):
        """Opening twice without close should raise RuntimeError."""
        base = str(tmp_path / "double_open")
        writer = EnviWriter()
        writer.open(base, "Mono8")

        with pytest.raises(RuntimeError, match="already open"):
            writer.open(base + "_2", "Mono8")

        writer.close()

    def test_binned_geometry_and_metadata_are_written(self, tmp_path):
        """A binned acquisition uses its actual frame geometry in the header."""
        base = str(tmp_path / "bin2x2")
        frame = np.full((512, 640), 123, dtype=np.uint16)
        metadata = {
            "width": 640,
            "height": 512,
            "binning_x": 2,
            "binning_y": 2,
            "binning": "2x2",
            "original_width": 1280,
            "original_height": 1024,
        }
        writer = EnviWriter()
        writer.open(base, "Mono12", metadata=metadata)
        writer.write_line(frame)
        writer.close()

        header = Path(base + ".hdr").read_text(encoding="utf-8")
        assert "samples = 640" in header
        assert "bands = 512" in header
        assert "binning horizontal = 2" in header
        assert "binning vertical = 2" in header
        assert "binning = 2x2" in header
        assert Path(base + ".dat").stat().st_size == frame.nbytes
