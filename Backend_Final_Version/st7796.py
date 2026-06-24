"""
ST7796 SPI LCD driver for the coffee roaster Raspberry Pi.

Uses SPI1 so transfers do not share SPI0 with the MAX31855 thermocouple.
Heater SSR is GPIO 23. Enable SPI1 with:

    dtoverlay=spi1-1cs,cs0_pin=17

Wiring smoke test (optional):
    python backend/hardware/display/st7796.py
    python backend/hardware/display/st7796.py --image test.jpg
"""

import argparse
import os
import time

try:
    import RPi.GPIO as GPIO
    import spidev
except ImportError as exc:
    raise SystemExit(
        "LCD driver must run on the Raspberry Pi with RPi.GPIO and spidev "
        "installed. Try: pip install spidev RPi.GPIO"
    ) from exc


LCD_NATIVE_WIDTH = 320
LCD_NATIVE_HEIGHT = 480
LCD_ROTATION = 90

SPI_BUS = 1
SPI_DEVICE = 0  # /dev/spidev1.0, with SPI1 CS remapped to BCM GPIO 17

LCD_CS = 17
LCD_RS = 25
LCD_RST = 24
LCD_LED = 22  # GPIO 23 reserved for heater SSR (config.HEATER_GPIO)

LCD_BACKLIGHT_BRIGHTNESS = 1.0  # 0.0–1.0 PWM duty on the backlight pin
LCD_PIXEL_BRIGHTNESS = 1.25  # software boost for images and dashboard frames


class ST7796Display:
    def __init__(
        self,
        width=None,
        height=None,
        rotation=LCD_ROTATION,
        bus=SPI_BUS,
        device=SPI_DEVICE,
        cs_pin=LCD_CS,
        dc_pin=LCD_RS,
        rst_pin=LCD_RST,
        bl_pin=LCD_LED,
        speed_hz=16_000_000,
        backlight_brightness=LCD_BACKLIGHT_BRIGHTNESS,
        display_inversion=True,
    ):
        self.rotation = rotation % 360
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("rotation must be one of 0, 90, 180, or 270")

        if width is None or height is None:
            if self.rotation in (90, 270):
                self.width = LCD_NATIVE_HEIGHT
                self.height = LCD_NATIVE_WIDTH
            else:
                self.width = LCD_NATIVE_WIDTH
                self.height = LCD_NATIVE_HEIGHT
        else:
            self.width = width
            self.height = height

        self.cs_pin = cs_pin
        self.dc_pin = dc_pin
        self.rst_pin = rst_pin
        self.bl_pin = bl_pin
        self._backlight = max(0.0, min(1.0, float(backlight_brightness)))
        self._display_inversion = display_inversion
        self._bl_pwm = None
        self._bl_pwm_started = False

        dev_path = f"/dev/spidev{bus}.{device}"
        if not os.path.exists(dev_path):
            raise SystemExit(
                f"Cannot find {dev_path}.\n"
                "Enable SPI1 and remap its CS pin away from the heater SSR:\n"
                "  dtparam=spi=on\n"
                "  dtoverlay=spi1-1cs,cs0_pin=17\n"
                "Add those lines to /boot/firmware/config.txt on Raspberry Pi OS "
                "Bookworm, or /boot/config.txt on older releases, then reboot.\n"
                "After reboot, check with: ls -l /dev/spidev*"
            )

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for pin in (self.cs_pin, self.dc_pin, self.rst_pin):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.bl_pin, GPIO.OUT)
        self._bl_pwm = GPIO.PWM(self.bl_pin, 1000)

        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0
        self.spi.no_cs = True

    def set_backlight(self, duty):
        duty = max(0.0, min(1.0, float(duty)))
        self._backlight = duty
        if self._bl_pwm is None:
            return
        if not self._bl_pwm_started:
            self._bl_pwm.start(duty * 100)
            self._bl_pwm_started = True
        else:
            self._bl_pwm.ChangeDutyCycle(duty * 100)

    def close(self):
        if self._bl_pwm is not None and self._bl_pwm_started:
            self._bl_pwm.stop()
        GPIO.output(self.bl_pin, GPIO.LOW)
        self.spi.close()
        GPIO.cleanup((self.cs_pin, self.dc_pin, self.rst_pin, self.bl_pin))

    def reset(self):
        GPIO.output(self.rst_pin, GPIO.HIGH)
        time.sleep(0.05)
        GPIO.output(self.rst_pin, GPIO.LOW)
        time.sleep(0.12)
        GPIO.output(self.rst_pin, GPIO.HIGH)
        time.sleep(0.12)

    def write_command(self, command, data=None):
        GPIO.output(self.cs_pin, GPIO.LOW)
        GPIO.output(self.dc_pin, GPIO.LOW)
        self.spi.xfer2([command])
        if data:
            GPIO.output(self.dc_pin, GPIO.HIGH)
            self._write_bytes(data)
        GPIO.output(self.cs_pin, GPIO.HIGH)

    def _write_bytes(self, data, chunk_size=4096):
        for start in range(0, len(data), chunk_size):
            self.spi.xfer2(data[start : start + chunk_size])

    def initialize(self):
        madctl_by_rotation = {
            0: 0x48,
            90: 0x28,
            180: 0x88,
            270: 0xE8,
        }

        self.reset()
        self.write_command(0x11)  # Sleep out
        time.sleep(0.12)
        self.write_command(0x3A, [0x55])  # 16-bit RGB565 pixels
        self.write_command(0x36, [madctl_by_rotation[self.rotation]])
        if self._display_inversion:
            self.write_command(0x21)  # Display inversion on, common for IPS panels
        else:
            self.write_command(0x20)
        self.write_command(0x29)  # Display on
        self.set_backlight(self._backlight)
        time.sleep(0.05)

    def set_window(self, x0, y0, x1, y1):
        self.write_command(0x2A, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self.write_command(0x2B, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self.write_command(0x2C)

    def draw_rgb565(self, pixel_bytes):
        expected = self.width * self.height * 2
        if len(pixel_bytes) != expected:
            raise ValueError(f"Expected {expected} RGB565 bytes, got {len(pixel_bytes)}")

        self.set_window(0, 0, self.width - 1, self.height - 1)
        GPIO.output(self.cs_pin, GPIO.LOW)
        GPIO.output(self.dc_pin, GPIO.HIGH)
        self._write_bytes(pixel_bytes)
        GPIO.output(self.cs_pin, GPIO.HIGH)


def rgb565(red, green, blue):
    value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
    return value >> 8, value & 0xFF


def rgb888_bytes_to_rgb565(raw_bytes):
    data = bytearray((len(raw_bytes) // 3) * 2)
    offset = 0
    for src in range(0, len(raw_bytes), 3):
        hi, lo = rgb565(raw_bytes[src], raw_bytes[src + 1], raw_bytes[src + 2])
        data[offset] = hi
        data[offset + 1] = lo
        offset += 2
    return data


def image_to_rgb565(image, pixel_brightness=LCD_PIXEL_BRIGHTNESS):
    img = image.convert("RGB")
    if pixel_brightness != 1.0:
        try:
            from PIL import ImageEnhance

            img = ImageEnhance.Brightness(img).enhance(pixel_brightness)
        except ImportError:
            raw = img.tobytes()
            boosted = bytearray(len(raw))
            for index in range(0, len(raw), 3):
                for channel in range(3):
                    boosted[index + channel] = min(
                        255, int(raw[index + channel] * pixel_brightness)
                    )
            return rgb888_bytes_to_rgb565(boosted)
    return rgb888_bytes_to_rgb565(img.tobytes())


def make_test_card(width, height):
    colors = (
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
        (255, 255, 255),
        (0, 0, 0),
    )
    data = bytearray(width * height * 2)
    offset = 0

    for y in range(height):
        for x in range(width):
            band = min(len(colors) - 1, x * len(colors) // width)
            red, green, blue = colors[band]

            if x < 6 or y < 6 or x >= width - 6 or y >= height - 6:
                red, green, blue = 255, 255, 255
            elif abs(x - width // 2) < 2 or abs(y - height // 2) < 2:
                red, green, blue = 0, 0, 0
            elif (x + y) % 64 < 8:
                red = (red + 80) // 2
                green = (green + 80) // 2
                blue = (blue + 80) // 2

            hi, lo = rgb565(red, green, blue)
            data[offset] = hi
            data[offset + 1] = lo
            offset += 2

    return data


def load_image(path, width, height, pixel_brightness=LCD_PIXEL_BRIGHTNESS):
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Image loading needs Pillow. Try: pip install Pillow") from exc

    image = Image.open(path).convert("RGB")
    image.thumbnail((width, height))

    canvas = Image.new("RGB", (width, height), (20, 20, 20))
    left = (width - image.width) // 2
    top = (height - image.height) // 2
    canvas.paste(image, (left, top))

    return image_to_rgb565(canvas, pixel_brightness=pixel_brightness)


def main():
    parser = argparse.ArgumentParser(description="ST7796 SPI LCD wiring smoke test")
    parser.add_argument("--image", help="Optional image file to display")
    parser.add_argument("--speed", type=int, default=16_000_000, help="SPI speed in Hz")
    parser.add_argument("--bus", type=int, default=SPI_BUS, help="SPI bus number")
    parser.add_argument(
        "--device", type=int, default=SPI_DEVICE, help="SPI device/chip select number"
    )
    parser.add_argument("--cs-pin", type=int, default=LCD_CS, help="LCD CS BCM GPIO")
    parser.add_argument(
        "--rotation",
        type=int,
        default=LCD_ROTATION,
        choices=(0, 90, 180, 270),
        help="Display rotation in degrees",
    )
    parser.add_argument(
        "--backlight",
        type=float,
        default=LCD_BACKLIGHT_BRIGHTNESS,
        help="Backlight PWM duty from 0.0 to 1.0 (default: full brightness)",
    )
    parser.add_argument(
        "--pixel-brightness",
        type=float,
        default=LCD_PIXEL_BRIGHTNESS,
        help="Software brightness boost for displayed pixels (1.0 = unchanged)",
    )
    parser.add_argument(
        "--no-inversion",
        action="store_true",
        help="Disable display inversion (try if the panel looks washed out)",
    )
    args = parser.parse_args()

    lcd = ST7796Display(
        rotation=args.rotation,
        bus=args.bus,
        device=args.device,
        cs_pin=args.cs_pin,
        speed_hz=args.speed,
        backlight_brightness=args.backlight,
        display_inversion=not args.no_inversion,
    )
    try:
        lcd.initialize()
        pixels = (
            load_image(
                args.image,
                lcd.width,
                lcd.height,
                pixel_brightness=args.pixel_brightness,
            )
            if args.image
            else make_test_card(lcd.width, lcd.height)
        )
        lcd.draw_rgb565(pixels)
        print("LCD test image displayed. Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        lcd.close()


if __name__ == "__main__":
    main()