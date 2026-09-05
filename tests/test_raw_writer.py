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

    def test_binning_metadata_is_persisted(self, tmp_path):
        base = str(tmp_path / "raw_binned")
        frame = np.zeros((512, 640), dtype=np.uint16)
        writer = RawWriter()
        writer.open(
            base,
            "Mono12",
            metadata={
                "width": 640,
                "height": 512,
                "binning_x": 2,
                "binning_y": 2,
                "binning": "2x2",
                "original_width": 1280,
                "original_height": 1024,
            },
        )
        writer.write_frame(frame)
        writer.close()

        sidecar = json.loads(Path(base + ".json").read_text(encoding="utf-8"))
        assert sidecar["width"] == 640
        assert sidecar["height"] == 512
        assert sidecar["binning"] == "2x2"
        assert sidecar["binning_x"] == 2
        assert sidecar["binning_y"] == 2

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

    def test_async_storage_drains_and_copies_frames(self, tmp_path):
        """Queued storage should finish on stop and preserve frame contents."""
        mgr = StorageManager()
        frame = np.full((1024, 1280), 7, dtype=np.uint16)

        mgr.start_raw(str(tmp_path), "queued", "Mono12")
        mgr.write_frame(frame)
        frame.fill(99)
        mgr.stop()

        dat_path = tmp_path / "queued.dat"
        stored = np.fromfile(dat_path, dtype=np.uint16).reshape(1024, 1280)
        assert np.all(stored == 7)

    def test_bounded_storage_queue_drops_frames_instead_of_growing(self, tmp_path):
        """A full queue should cap memory usage and report dropped frames."""
        mgr = StorageManager(max_pending_frames=1)
        frame = np.full((1024, 1280), 3, dtype=np.uint16)

        mgr.start_raw(str(tmp_path), "bounded", "Mono12")
        mgr.write_frame(frame)
        for _ in range(8):
            mgr.write_frame(frame)
        mgr.stop()

        assert mgr.dropped_frames > 0
