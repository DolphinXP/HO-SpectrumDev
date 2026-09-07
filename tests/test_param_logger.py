"""Tests for per-second parameter CSV logging."""

import csv
import time

import numpy as np

from src.data.param_logger import CsvParamLogger
from src.data.storage import StorageManager


def _sampler_factory():
    return lambda: {
        "exposure_us": 10000.0,
        "frame_rate_fps": 72.4,
        "gain_db": 0.0,
        "adc_bit_depth": 12,
        "temperature_c": 35.6,
    }


class TestCsvParamLogger:
    def test_writes_header_and_rows(self, tmp_path):
        logger = CsvParamLogger(
            str(tmp_path / "session.dat"),
            _sampler_factory(),
            interval_s=0.05,
        )
        logger.start()
        time.sleep(0.2)
        logger.stop()

        csv_path = tmp_path / "session.csv"
        assert csv_path.exists()

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert rows[0] == [
            "时间戳",
            "录制时长 (s)",
            "曝光时间 (µs)",
            "帧率 (fps)",
            "增益 (dB)",
            "ADC 位深 (bit)",
            "探测器温度 (°C)",
        ]
        data_rows = rows[1:]
        assert len(data_rows) >= 2
        assert logger.rows_written == len(data_rows)

        row = data_rows[0]
        assert row[2] == "10000.0"      # exposure_us
        assert row[3] == "72.4"         # frame_rate_fps
        assert row[4] == "0.0"          # gain_db
        assert row[5] == "12"           # adc_bit_depth
        assert row[6] == "35.6"         # temperature_c

    def test_sampler_exception_yields_empty_cells(self, tmp_path):
        def bad_sampler():
            raise RuntimeError("device gone")

        logger = CsvParamLogger(str(tmp_path / "bad"), bad_sampler, interval_s=0.05)
        logger.start()
        time.sleep(0.12)
        logger.stop()

        with open(tmp_path / "bad.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2
        # Parameter cells are empty but the row still exists
        assert rows[1][2:] == ["", "", "", "", ""]

    def test_stop_without_start_is_safe(self, tmp_path):
        logger = CsvParamLogger(str(tmp_path / "never"), _sampler_factory())
        logger.stop()  # must not raise


class TestStorageManagerParamCsv:
    def test_csv_created_alongside_recording(self, tmp_path):
        mgr = StorageManager()
        frame = np.zeros((1024, 1280), dtype=np.uint16)

        mgr.start_raw(
            str(tmp_path),
            "session",
            "Mono12",
            metadata={"param_sampler": _sampler_factory()},
        )
        # Give the logger thread a moment to write its first row
        time.sleep(1.2)
        mgr.write_frame(frame)
        mgr.stop()

        csv_path = tmp_path / "session.csv"
        assert csv_path.exists()
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2

    def test_no_csv_without_sampler(self, tmp_path):
        mgr = StorageManager()
        frame = np.zeros((1024, 1280), dtype=np.uint16)

        mgr.start_raw(str(tmp_path), "plain", "Mono12")
        mgr.write_frame(frame)
        mgr.stop()

        assert not (tmp_path / "plain.csv").exists()

    def test_envi_and_raw_share_one_csv(self, tmp_path):
        mgr = StorageManager()
        frame = np.zeros((1024, 1280), dtype=np.uint16)

        mgr.start_envi(
            str(tmp_path),
            "combo",
            "Mono12",
            metadata={"param_sampler": _sampler_factory()},
        )
        mgr.start_raw(
            str(tmp_path),
            "combo",
            "Mono12",
            metadata={"param_sampler": _sampler_factory()},
        )
        time.sleep(1.2)
        mgr.write_frame(frame)
        mgr.stop()

        csv_path = tmp_path / "combo.csv"
        assert csv_path.exists()
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) >= 2
