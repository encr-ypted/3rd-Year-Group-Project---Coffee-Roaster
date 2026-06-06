"""
Dual MAX31855 inputs: bean (profile) + air/chamber (heater control).

Bean uses SPI1; air uses SPI0. Each chip has its own CS GPIO.
"""

from hardware.thermocouple import RoasterThermocouple, read_thermocouple
import config as cfg
import time


class RoasterSensors:
    def __init__(self):
        self.bean = RoasterThermocouple(
            cs_gpio=cfg.THERMOCOUPLE_BEAN_CS_GPIO,
            spi_bus=cfg.THERMOCOUPLE_BEAN_SPI_BUS,
        )
        self.air = RoasterThermocouple(
            cs_gpio=cfg.THERMOCOUPLE_AIR_CS_GPIO,
            spi_bus=cfg.THERMOCOUPLE_AIR_SPI_BUS,
        )

    def read(self):
        bean_temp, bean_fault = read_thermocouple(self.bean)
        # time.sleep(1)
        air_temp, air_fault = read_thermocouple(self.air)
        return {
            "bean_temp": bean_temp,
            "bean_fault": bean_fault,
            "air_temp": air_temp,
            "air_fault": air_fault,
        }
