"""Tests for binning-aware NUC coefficient handling."""

import numpy as np

from src.data.nuc import NUCProcessor


def test_nuc_applies_binned_coefficients_when_shapes_match(tmp_path):
    """2x2 NUC coefficients are applied to the 512x640 camera output."""
    shape = (512, 640)
    a_path = tmp_path / "gain_2x2.npy"
    b_path = tmp_path / "offset_2x2.npy"
    np.save(a_path, np.full(shape, 2.0, dtype=np.float32))
    np.save(b_path, np.full(shape, 3.0, dtype=np.float32))

    nuc = NUCProcessor()
    nuc.load(str(a_path), str(b_path), expected_shape=shape)
    nuc.enabled = True

    corrected = nuc.apply(np.full(shape, 10, dtype=np.uint16))
    assert corrected.shape == shape
    assert corrected.dtype == np.float32
    assert np.all(corrected == 23.0)


def test_nuc_skips_coefficients_that_do_not_match_active_binning(tmp_path):
    """A 2x2 coefficient pair is never applied to a full-resolution frame."""
    binned_shape = (512, 640)
    a_path = tmp_path / "gain_2x2.npy"
    b_path = tmp_path / "offset_2x2.npy"
    np.save(a_path, np.ones(binned_shape, dtype=np.float32))
    np.save(b_path, np.zeros(binned_shape, dtype=np.float32))

    nuc = NUCProcessor()
    nuc.load(str(a_path), str(b_path), expected_shape=binned_shape)
    nuc.enabled = True

    full_resolution = np.full((1024, 1280), 99, dtype=np.uint16)
    assert nuc.apply(full_resolution) is full_resolution
