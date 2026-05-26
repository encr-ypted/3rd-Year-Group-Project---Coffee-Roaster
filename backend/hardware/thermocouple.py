import time

import board
import digitalio
import adafruit_max31855

from config import (
    THERMOCOUPLE_CS_GPIO,
    THERMOCOUPLE_EMA_ALPHA,
    THERMOCOUPLE_STARTUP_DELAY_S,
)


def _cs_pin(gpio=THERMOCOUPLE_CS_GPIO):
    return getattr(board, f"D{gpio}")


class RoasterThermocouple:
    def __init__(self, cs_pin=None, alpha=THERMOCOUPLE_EMA_ALPHA):
        cs_pin = _cs_pin() if cs_pin is None else cs_pin
        self.spi = board.SPI()
        self.cs = digitalio.DigitalInOut(cs_pin)
        self.sensor = adafruit_max31855.MAX31855(self.spi, self.cs)
        self.alpha = alpha
        self.filtered_temp = None
        self.last_fault: str | None = None
        time.sleep(THERMOCOUPLE_STARTUP_DELAY_S)

    def read_temperatures(self) -> tuple[float | None, float | None, str | None]:
        """Single SPI read — (raw °C, filtered °C, fault message)."""
        try:
            raw = self.sensor.temperature
            self.last_fault = None
        except RuntimeError as exc:
            self.last_fault = str(exc)
            return None, None, self.last_fault

        if self.filtered_temp is None:
            self.filtered_temp = raw
        else:
            self.filtered_temp = (
                self.alpha * raw + (1 - self.alpha) * self.filtered_temp
            )
        return raw, round(self.filtered_temp, 2), None

    def read_raw_temperature(self):
        raw, _, _ = self.read_temperatures()
        return raw

    def read_filtered_temperature(self):
        _, filtered, _ = self.read_temperatures()
        return filtered
