"""Tests for raw frame writer and storage manager combinations."""

import json
from pathlib import Path

import numpy as np

from src.data.raw_writer import RawWriter
from src.data.storage import StorageManager


class TestRawWriter:
    def test_raw_only_writes_dat_and_json(self, tmp_path):
        """Raw-only output should create .dat data and a JSON sidecar."""
        base = str(tmp_path / "raw_only")
        frame = np.random.randint(0, 4096, (1024, 1280), dtype=np.uint16)

        writer = RawWriter()
        writer.open(base, "Mono12")
        writer.write_frame(frame)
        writer.close()

        dat_path = Path(base + ".dat")
        json_path = Path(base + ".json")

        assert dat_path.exists()
        assert json_path.exists()
        assert not Path(base + ".raw").exists()
        assert dat_path.stat().st_size == frame.size * frame.dtype.itemsize

        raw_data = np.fromfile(dat_path, dtype=np.uint16).reshape(1024, 1280)
        np.testing.assert_array_equal(raw_data, frame)

        sidecar = json.loads(json_path.read_text(encoding="utf-8"))
        assert sidecar["frame_count"] == 1
        assert sidecar["data_file"] == "raw_only.dat"

    def test_metadata_only_mode_writes_json_without_duplicate_dat(self, tmp_path):
        """Metadata-only mode should skip binary output and still record JSON."""
        base = str(tmp_path / "meta_only")
        frame = np.random.randint(0, 256, (1024, 1280), dtype=np.uint8)

        writer = RawWriter()
        writer.open(base, "Mono8", write_binary=False)
        writer.write_frame(frame)
        writer.close()

        assert not Path(base + ".dat").exists()
        json_path = Path(base + ".json")
        assert json_path.exists()

        sidecar = json.loads(json_path.read_text(encoding="utf-8"))
        assert sidecar["frame_count"] == 1
        assert sidecar["data_file"] == "meta_only.dat"


class TestStorageManager:
    def test_envi_and_raw_share_single_dat_file(self, tmp_path):
        """ENVI + raw should produce one .dat, one .hdr, and one .json."""
        mgr = StorageManager()
        frame = np.random.randint(0, 4096, (1024, 1280), dtype=np.uint16)

        mgr.start_envi(str(tmp_path), "session", "Mono12")
        mgr.start_raw(str(tmp_path), "session", "Mono12")
        mgr.write_frame(frame)
        mgr.stop()

        dat_path = tmp_path / "session.dat"
        hdr_path = tmp_path / "session.hdr"
        json_path = tmp_path / "session.json"

        assert dat_path.exists()
        assert hdr_path.exists()
        assert json_path.exists()
        assert not (tmp_path / "session.raw").exists()
        assert dat_path.stat().st_size == frame.size * frame.dtype.itemsize

        sidecar = json.loads(json_path.read_text(encoding="utf-8"))
        assert sidecar["frame_count"] == 1
        assert sidecar["data_file"] == "session.dat"
