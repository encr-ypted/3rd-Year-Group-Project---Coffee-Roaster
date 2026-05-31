"""
Persist roast sessions for offline analysis and ML.

Each session writes:
  logs/roast_<id>.csv       — time-series samples (~2 Hz while session active)
  logs/roast_<id>_meta.json — session labels and summary stats
  logs/roasts_index.csv     — one row per session
"""

import csv
import json
import os
import time
from datetime import datetime, timezone

from config import LOG_FOLDER, LOG_INDEX_FILE

SAMPLE_COLUMNS = [
    "roast_id",
    "unix_ts",
    "elapsed_s",
    "profile_id",
    "temp_c",
    "temp_raw_c",
    "target_c",
    "temp_error_c",
    "heater_pwm",
    "fan_pwm",
    "ror_c_per_min",
    "state",
    "event",
]

INDEX_COLUMNS = [
    "roast_id",
    "profile_id",
    "target_c",
    "hardware",
    "started_at",
    "ended_at",
    "duration_s",
    "outcome",
    "sample_count",
    "max_temp_c",
    "final_temp_c",
    "csv_path",
]


def list_sessions():
    """Read roasts_index.csv; returns list of dicts (newest last)."""
    index_path = os.path.join(LOG_FOLDER, LOG_INDEX_FILE)
    if not os.path.exists(index_path):
        return []
    with open(index_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class RoastDataLogger:
    def __init__(self, hardware_mode="pi"):
        self.hardware_mode = hardware_mode
        self._active = False
        self._roast_id = ""
        self._profile_id = ""
        self._target_c = 0.0
        self._started_at = ""
        self._csv_path = ""
        self._csv_file = None
        self._writer = None
        self._sample_count = 0
        self._max_temp = None
        self._last_state = ""
        self._start_unix = 0.0

    @property
    def is_active(self):
        return self._active

    @property
    def roast_id(self):
        return self._roast_id

    @property
    def csv_path(self):
        return self._csv_path

    def start_session(self, profile_id, target_temp_c):
        if self._active:
            self.end_session("replaced")

        os.makedirs(LOG_FOLDER, exist_ok=True)

        self._roast_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._profile_id = profile_id
        self._target_c = float(target_temp_c)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._start_unix = time.time()
        self._sample_count = 0
        self._max_temp = None
        self._last_state = ""

        self._csv_path = os.path.join(LOG_FOLDER, f"roast_{self._roast_id}.csv")
        self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._csv_file)
        self._writer.writerow(SAMPLE_COLUMNS)
        self._active = True
        return self._roast_id

    def log_sample(
        self,
        *,
        elapsed_s,
        temp_c,
        target_c,
        heater_pwm,
        fan_pwm,
        ror_c_per_min,
        state,
        temp_raw_c=None,
        event="",
    ):
        if not self._active or not self._writer:
            return

        if self._max_temp is None or temp_c > self._max_temp:
            self._max_temp = temp_c

        self._writer.writerow(
            [
                self._roast_id,
                datetime.now(timezone.utc).timestamp(),
                round(elapsed_s, 2),
                self._profile_id,
                round(temp_c, 2),
                "" if temp_raw_c is None else round(temp_raw_c, 2),
                round(target_c, 2),
                round(target_c - temp_c, 2),
                round(heater_pwm, 1),
                int(fan_pwm),
                round(ror_c_per_min, 2),
                state,
                event,
            ]
        )
        self._csv_file.flush()
        self._sample_count += 1
        self._last_state = state

    def end_session(self, outcome, final_temp_c=None):
        if not self._active:
            return None

        ended_at = datetime.now(timezone.utc).isoformat()
        duration_s = round(time.time() - self._start_unix, 1) if self._start_unix else 0.0

        if self._csv_file:
            self._csv_file.close()
        self._csv_file = None
        self._writer = None
        self._active = False

        meta_path = self._csv_path.replace(".csv", "_meta.json")
        meta = {
            "roast_id": self._roast_id,
            "profile_id": self._profile_id,
            "target_temp_c": self._target_c,
            "hardware": self.hardware_mode,
            "started_at": self._started_at,
            "ended_at": ended_at,
            "duration_s": duration_s,
            "outcome": outcome,
            "sample_count": self._sample_count,
            "max_temp_c": self._max_temp,
            "final_temp_c": final_temp_c,
            "csv_path": self._csv_path,
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        self._append_index(meta, final_temp_c)
        return meta_path

    def _append_index(self, meta, final_temp_c):
        index_path = os.path.join(LOG_FOLDER, LOG_INDEX_FILE)
        write_header = not os.path.exists(index_path)

        with open(index_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(INDEX_COLUMNS)
            writer.writerow(
                [
                    meta["roast_id"],
                    meta["profile_id"],
                    meta["target_temp_c"],
                    meta["hardware"],
                    meta["started_at"],
                    meta["ended_at"],
                    meta["duration_s"],
                    meta["outcome"],
                    meta["sample_count"],
                    meta["max_temp_c"],
                    "" if final_temp_c is None else final_temp_c,
                    meta["csv_path"],
                ]
            )
