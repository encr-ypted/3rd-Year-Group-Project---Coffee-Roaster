import time

import board
import digitalio
import adafruit_max31855

from config import (
    THERMOCOUPLE_BEAN_CS_GPIO,
    THERMOCOUPLE_STARTUP_DELAY_S,
)


class RoasterThermocouple:
    def __init__(self, cs_gpio=None):
        pin = cs_gpio if cs_gpio is not None else THERMOCOUPLE_BEAN_CS_GPIO
        cs = getattr(board, f"D{pin}")
        self.spi = board.SPI()
        self.cs = digitalio.DigitalInOut(cs)
        self.sensor = adafruit_max31855.MAX31855(self.spi, self.cs)
        self.last_fault = None
        time.sleep(THERMOCOUPLE_STARTUP_DELAY_S)

    def read_temperature(self):
        try:
            raw = self.sensor.temperature
            self.last_fault = None
            return round(raw, 2), None
        except RuntimeError as exc:
            self.last_fault = str(exc)
            return None, self.last_fault


def read_thermocouple(tc):
    return tc.read_temperature()
