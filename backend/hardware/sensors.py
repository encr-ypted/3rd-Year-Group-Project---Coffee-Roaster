"""
Dual MAX31855 inputs: bean (profile) + air/chamber (heater control).

Both share SPI0; each chip needs its own CS GPIO.
"""

from hardware.thermocouple import RoasterThermocouple, read_thermocouple
import config as cfg


class RoasterSensors:
    def __init__(self):
        self.bean = RoasterThermocouple(cs_gpio=cfg.THERMOCOUPLE_BEAN_CS_GPIO)
        self.air = RoasterThermocouple(cs_gpio=cfg.THERMOCOUPLE_AIR_CS_GPIO)

    def read(self):
        bean_temp, bean_fault = read_thermocouple(self.bean)
        air_temp, air_fault = read_thermocouple(self.air)
        return {
            "bean_temp": bean_temp,
            "bean_fault": bean_fault,
            "air_temp": air_temp,
            "air_fault": air_fault,
        }
