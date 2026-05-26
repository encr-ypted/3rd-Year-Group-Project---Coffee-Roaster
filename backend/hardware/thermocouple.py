import time

import board
import digitalio
import adafruit_max31855

from config import THERMOCOUPLE_CS_GPIO, THERMOCOUPLE_STARTUP_DELAY_S


def _cs_pin(gpio=THERMOCOUPLE_CS_GPIO):
    return getattr(board, f"D{gpio}")


_SPI_HELP = (
    "SPI is not enabled on this Pi (needed for MAX31855).\n"
    "  1. sudo raspi-config → Interface Options → SPI → Enable\n"
    "  2. sudo reboot\n"
    "  3. ls /dev/spidev*   (expect spidev0.0 and spidev0.1)\n"
    "  4. sudo usermod -aG spi,gpio $USER  (log out/in after)"
)


class RoasterThermocouple:
    def __init__(self, cs_pin=None):
        cs_pin = _cs_pin() if cs_pin is None else cs_pin
        try:
            self.spi = board.SPI()
        except OSError as exc:
            if "spidev" in str(exc).lower():
                raise OSError(f"{exc}\n\n{_SPI_HELP}") from exc
            raise
        self.cs = digitalio.DigitalInOut(cs_pin)
        self.sensor = adafruit_max31855.MAX31855(self.spi, self.cs)
        self.last_fault: str | None = None
        time.sleep(THERMOCOUPLE_STARTUP_DELAY_S)

    def read_temperature(self) -> tuple[float | None, str | None]:
        """Returns (raw °C from MAX31855, fault message)."""
        try:
            raw = self.sensor.temperature
            self.last_fault = None
            return round(raw, 2), None
        except RuntimeError as exc:
            self.last_fault = str(exc)
            return None, self.last_fault

    def read_temperatures(self) -> tuple[float | None, float | None, str | None]:
        """Legacy API: (raw, raw, fault). Prefer read_temperature()."""
        temp, fault = self.read_temperature()
        return temp, temp, fault


def read_thermocouple(tc: RoasterThermocouple) -> tuple[float | None, str | None]:
    """Raw °C + fault; supports read_temperature() or legacy read_temperatures()."""
    read = getattr(tc, "read_temperature", None)
    if callable(read):
        return read()
    legacy = getattr(tc, "read_temperatures", None)
    if callable(legacy):
        raw, _filtered, fault = legacy()
        return raw, fault
    raise AttributeError(
        f"{type(tc).__name__} has no read_temperature or read_temperatures"
    )
