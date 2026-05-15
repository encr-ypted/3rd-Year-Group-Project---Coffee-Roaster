"""MAX31855 thermocouple reader with EMA smoothing."""

import time

import board
import digitalio
import adafruit_max31855


class RoasterThermocouple:
    """Bean temperature via MAX31855 on SPI (CS on GPIO 8 by default)."""

    def __init__(self, cs_pin=board.D8, alpha = 0.2):
        self.spi = board.SPI()
        self.cs = digitalio.DigitalInOut(cs_pin)
        self.sensor = adafruit_max31855.MAX31855(self.spi, self.cs)
        self.alpha = alpha
        self.filtered_temp: float | None = None
        time.sleep(0.5)

    def read_raw_temperature(self):
        return self.sensor.temperature


    def read_filtered_temperature(self) -> float | None:
        try:
            raw = self.sensor.temperature

            if self.filtered_temp is None:
                self.filtered_temp = raw
            else:
                self.filtered_temp = (
                    self.alpha * raw + (1 - self.alpha) * self.filtered_temp
                )
            return round(self.filtered_temp, 2)
        except RuntimeError:
            return None
