import json
import os
import subprocess
import sys
import time

STATE_FILE = "grayscale_state.json"
INTERVAL_S = 0.25

CAPTURE_TIMEOUT_S = 4.0
RETRY_AFTER_TIMEOUT_S = 10.0


def write_state(payload):
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w") as file:
        json.dump(payload, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp_file, STATE_FILE)


def run_one_capture():
    code = r"""
import json
from pi_ai_detector import SmartRoastAIDetector

detector = SmartRoastAIDetector()
detector.open()
result = detector.infer_once(save_crop=False)
gray = float(result.mean_grayscale)
detector.close()

print(json.dumps({"mean_grayscale": gray}))
"""

    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=CAPTURE_TIMEOUT_S,
    )


def main():
    while True:
        try:
            result = run_one_capture()

            if result.returncode != 0:
                error_text = result.stderr.strip() or result.stdout.strip()

                print(f"Grayscale worker subprocess failed: {error_text}")

                write_state({
                    "timestamp": time.time(),
                    "mean_grayscale": None,
                    "ok": False,
                    "error": error_text,
                })

                time.sleep(RETRY_AFTER_TIMEOUT_S)
                continue

            lines = result.stdout.strip().splitlines()
            json_line = lines[-1]
            payload = json.loads(json_line)
            gray = float(payload["mean_grayscale"])

            write_state({
                "timestamp": time.time(),
                "mean_grayscale": gray,
                "ok": True,
                "error": None,
            })

            print(f"Grayscale worker: {gray:.2f}")
            time.sleep(INTERVAL_S)

        except subprocess.TimeoutExpired:
            print(
                "Grayscale worker timeout: camera/libcamera hung. "
                "Killing capture subprocess and retrying."
            )

            write_state({
                "timestamp": time.time(),
                "mean_grayscale": None,
                "ok": False,
                "error": "camera/libcamera capture timeout",
            })

            time.sleep(RETRY_AFTER_TIMEOUT_S)

        except KeyboardInterrupt:
            print("Grayscale worker stopped")
            break

        except Exception as exc:
            print(f"Grayscale worker error: {repr(exc)}")

            write_state({
                "timestamp": time.time(),
                "mean_grayscale": None,
                "ok": False,
                "error": repr(exc),
            })

            time.sleep(RETRY_AFTER_TIMEOUT_S)


if __name__ == "__main__":
    main()