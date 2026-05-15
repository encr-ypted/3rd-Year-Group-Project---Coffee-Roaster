"""SSR relay heater with time-proportional control."""

import asyncio

from gpiozero import DigitalOutputDevice


class RoasterHeater:
    def __init__(self, gpio=18, control_window_s=2.0):
        self._relay = DigitalOutputDevice(gpio, active_high=True, initial_value=False)
        self._control_window_s = control_window_s
        self._output = 0.0

    async def apply_output(self, percent=0.0):
        percent = max(0.0, min(100.0, percent))
        self._output = round(percent, 1)

        window = self._control_window_s
        on_time = window * (percent / 100.0)
        off_time = window - on_time

        if percent > 0:
            self._relay.on()
            await asyncio.sleep(on_time)
            self._relay.off()
            await asyncio.sleep(off_time)
        else:
            self._relay.off()
            await asyncio.sleep(window)

        return self._output

    def stop(self):
        self._relay.off()
        self._output = 0.0

    def read_output(self):
        return self._output

    def read_output_percent(self):
        return round(self._output)
