import asyncio
import time

from gpiozero import DigitalOutputDevice

from config import HEATER_CONTROL_WINDOW_S, HEATER_GPIO


class RoasterHeater:
    def __init__(self, gpio=HEATER_GPIO, control_window_s=HEATER_CONTROL_WINDOW_S):
        self._relay = DigitalOutputDevice(gpio, active_high=True, initial_value=False)
        self._control_window_s = control_window_s
        self._output = 0.0
        self._halt = False

    def halt(self):
        self._halt = True
        self._relay.off()
        self._output = 0.0

    def clear_halt(self):
        self._halt = False

    @property
    def halted(self):
        return self._halt

    def off(self):
        """Relay off without safety latch (normal idle / cooling)."""
        self._relay.off()
        self._output = 0.0

    def stop(self):
        self.halt()

    #Sleep function but sleeps in intervals of 50ms allowing heater to be turned off by emergency stop during current running window
    async def _sleep_interruptible(self, seconds):
        if seconds <= 0:
            return not self._halt

        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._halt:
                self._relay.off()
                return False
            await asyncio.sleep(min(0.05, end - time.monotonic()))
        return not self._halt

    async def apply_output(self, percent=0.0):
        if self._halt:
            return 0.0

        percent = max(0.0, min(100.0, percent))
        self._output = round(percent, 1)

        window = self._control_window_s
        on_time = window * (percent / 100.0)
        off_time = window - on_time

        if percent > 0:
            self._relay.on()
            if not await self._sleep_interruptible(on_time):
                return 0.0
            self._relay.off()
            if not await self._sleep_interruptible(off_time):
                return 0.0
        else:
            self._relay.off()
            if not await self._sleep_interruptible(window):
                return 0.0

        return 0.0 if self._halt else self._output

    def read_output(self):
        return self._output

    def read_output_percent(self):
        return round(self._output)
