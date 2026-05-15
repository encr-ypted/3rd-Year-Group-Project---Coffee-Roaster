import time
import board
import digitalio
import adafruit_max31855


class RoasterThermocouple:
    def __init__(self, cs_pin=board.D8, alpha = 0.2):
        self.spi = board.SPI()
        self.cs = digitalio.DigitalInOut(cs_pin)
        self.sensor = adafruit_max31855.MAX31855(self.spi, self.cs)
        self.alpha = alpha
        self.filtered_temp = None
        time.sleep(0.5)

    def read_raw_temperature(self):
        return self.sensor.temperature


    def read_filtered_temperature(self):
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
