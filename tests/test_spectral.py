"""Tests for SpectralAnalyzer."""

import numpy as np
import pytest

from src.analysis.spectral import SpectralAnalyzer


@pytest.fixture
def analyzer():
    return SpectralAnalyzer()


@pytest.fixture
def frame():
    """Create a test frame (1024, 1280) with known values."""
    f = np.zeros((1024, 1280), dtype=np.uint16)
    # Row gradient: row i has value i
    for i in range(1024):
        f[i, :] = i
    return f


class TestNearSpatial:
    def test_center(self, analyzer, frame):
        indices, values = analyzer.near_spatial(frame, x=640, y=512)
        assert len(indices) == 21  # ±10 + center
        assert indices[10] == 640
        # All values should be 512 (row value)
        assert np.all(values == 512)

    def test_left_boundary(self, analyzer, frame):
        indices, values = analyzer.near_spatial(frame, x=3, y=0)
        assert indices[0] == 0
        assert len(indices) == 14  # 0..13

    def test_right_boundary(self, analyzer, frame):
        indices, values = analyzer.near_spatial(frame, x=1275, y=0)
        assert indices[-1] == 1279
        assert len(indices) == 15  # 1265..1279


class TestNearSpectral:
    def test_center(self, analyzer, frame):
        indices, values = analyzer.near_spectral(frame, x=640, y=512)
        assert len(indices) == 21
        assert indices[10] == 512
        # Values should be 502..522 (row values)
        expected = np.arange(502, 523)
        np.testing.assert_array_equal(values, expected)

    def test_top_boundary(self, analyzer, frame):
        indices, values = analyzer.near_spectral(frame, x=0, y=3)
        assert indices[0] == 0
        assert len(indices) == 14

    def test_bottom_boundary(self, analyzer, frame):
        indices, values = analyzer.near_spectral(frame, x=0, y=1020)
        assert indices[-1] == 1023


class TestFullSpatial:
    def test_full_row(self, analyzer, frame):
        indices, values = analyzer.full_spatial(frame, y=100)
        assert len(indices) == 1280
        assert indices[0] == 0
        assert indices[-1] == 1279
        assert np.all(values == 100)


class TestFullSpectral:
    def test_full_column(self, analyzer, frame):
        indices, values = analyzer.full_spectral(frame, x=500)
        assert len(indices) == 1024
        assert indices[0] == 0
        assert indices[-1] == 1023
        # Values should be 0..1023 (row gradient)
        np.testing.assert_array_equal(values, np.arange(1024))


class TestEdgeCases:
    def test_invalid_frame_shape(self, analyzer):
        bad_frame = np.zeros((100, 100), dtype=np.uint8)
        # Should still work — no hard-coded shape requirement in spectral
        indices, values = analyzer.near_spatial(bad_frame, x=50, y=50)
        assert len(indices) > 0

    def test_out_of_bounds_y(self, analyzer, frame):
        with pytest.raises(IndexError):
            analyzer.near_spatial(frame, x=0, y=2000)

    def test_out_of_bounds_x(self, analyzer, frame):
        with pytest.raises(IndexError):
            analyzer.near_spectral(frame, x=5000, y=0)
