import json
import os
import time

from pi_ai_detector import SmartRoastAIDetector

STATE_FILE = "grayscale_state.json"
INTERVAL_S = 0.25

NORMAL_RETRY_AFTER_ERROR_S = 5.0
CAMERA_TIMEOUT_RETRY_AFTER_S = 20.0
MAX_FAST_ERRORS_BEFORE_LONG_COOLDOWN = 3
LONG_COOLDOWN_S = 60.0


def write_state(payload):
    tmp_file = STATE_FILE + ".tmp"
    with open(tmp_file, "w") as file:
        json.dump(payload, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp_file, STATE_FILE)


def is_camera_timeout_error(exc):
    text = repr(exc).lower()

    return (
        "camera frontend has timed out" in text
        or "camera sensor connector" in text
        or "dequeue timer" in text
        or "camera __init__ sequence did not complete" in text
        or "failed to queue buffer" in text
        or "invalid argument" in text
        or "camera in running state" in text
    )


def close_detector(detector):
    if detector is None:
        return None

    try:
        detector.close()
    except Exception as exc:
        print(f"Grayscale worker: detector close ignored: {repr(exc)}")

    return None


def main():
    detector = None
    error_count = 0

    while True:
        try:
            if detector is None:
                detector = SmartRoastAIDetector()
                detector.open()
                error_count = 0
                print("Grayscale worker: detector ready")

            result = detector.infer_once(save_crop=False)
            gray = float(result.mean_grayscale)

            write_state({
                "timestamp": time.time(),
                "mean_grayscale": gray,
                "ok": True,
                "error": None,
            })

            print(f"Grayscale worker: {gray:.2f}")
            time.sleep(INTERVAL_S)

        except KeyboardInterrupt:
            break

        except Exception as exc:
            error_count += 1
            error_text = repr(exc)

            print(f"Grayscale worker error: {error_text}")

            write_state({
                "timestamp": time.time(),
                "mean_grayscale": None,
                "ok": False,
                "error": error_text,
            })

            detector = close_detector(detector)

            if error_count >= MAX_FAST_ERRORS_BEFORE_LONG_COOLDOWN:
                wait_s = LONG_COOLDOWN_S
                error_count = 0
                print(f"Grayscale worker: too many errors, cooling down for {wait_s}s")

            elif is_camera_timeout_error(exc):
                wait_s = CAMERA_TIMEOUT_RETRY_AFTER_S
                print(f"Grayscale worker: camera timeout/state error, retrying in {wait_s}s")

            else:
                wait_s = NORMAL_RETRY_AFTER_ERROR_S
                print(f"Grayscale worker: retrying in {wait_s}s")

            time.sleep(wait_s)

    detector = close_detector(detector)
    print("Grayscale worker stopped")


if __name__ == "__main__":
    main()