# ST7796 SPI LCD Test

This note is for the LCDWiki 3.5 inch IPS SPI Module using the ST7796 driver:
https://www.lcdwiki.com/zh/3.5inch_IPS_SPI_Module_ST7796

The project already uses Raspberry Pi SPI0 for the MAX31855 thermocouple:

- SPI0 SCLK: BCM GPIO 11, physical pin 23
- SPI0 MISO: BCM GPIO 9, physical pin 21
- SPI0 MOSI: BCM GPIO 10, physical pin 19
- Thermocouple CS: BCM GPIO 8, physical pin 24, SPI0 CE0

Use SPI1 for the LCD smoke test so high-volume image transfers do not share the
thermocouple SPI0 bus. SPI1 normally puts CE0 on BCM GPIO 18, but this project
already uses GPIO 18 for the heater SSR. Remap SPI1 CS to BCM GPIO 17 before
running the test.

## Pins Already Used By The Roaster

| Function | BCM GPIO | Physical pin |
| --- | ---: | ---: |
| Heater SSR | GPIO 18 | 12 |
| Fan PWM | GPIO 12 | 32 |
| MAX31855 CS | GPIO 8 / CE0 | 24 |
| SPI0 MOSI | GPIO 10 | 19 |
| SPI0 MISO | GPIO 9 | 21 |
| SPI0 SCLK | GPIO 11 | 23 |
| SPI1 default CE0, do not use | GPIO 18 | 12 |

## LCD Wiring

Power the LCD from the Raspberry Pi 3.3 V rail for the first test unless your
specific module documentation says its VCC pin must use 5 V. Keep all SPI and
control signals at 3.3 V logic.

The LCD test script uses `/dev/spidev1.0` and manually drives the LCD CS pin on
BCM GPIO 17. The default display orientation is landscape, rotated 90 degrees
clockwise from the original portrait wiring.

| LCD pin | Raspberry Pi signal | BCM GPIO | Physical pin | Notes |
| --- | --- | ---: | ---: | --- |
| VCC | 3.3 V | - | 1 or 17 | Module power |
| GND | GND | - | 6, 9, 14, 20, 25, 30, 34, or 39 | Common ground |
| CS / LCD_CS | SPI1 CS remapped | GPIO 17 | 11 | Avoids SSR GPIO 18 |
| RESET / RST | LCD reset | GPIO 24 | 18 | Free GPIO |
| DC / RS | Data/command | GPIO 25 | 22 | Free GPIO |
| SDI / MOSI | SPI1 MOSI | GPIO 20 | 38 | Dedicated LCD SPI bus |
| SCK / SCLK | SPI1 SCLK | GPIO 21 | 40 | Dedicated LCD SPI bus |
| LED / BL | Backlight enable | GPIO 23 | 16 | Driven high for test |
| SDO / MISO | SPI1 MISO | GPIO 19 | 35 | Optional for LCD-only test |
| T_CLK, T_CS, T_DIN, T_DO, T_IRQ | Not connected | - | - | Touch ignored |
| SD_CS, SD_MOSI, SD_MISO, SD_SCK | Not connected | - | - | SD slot ignored |

## Raspberry Pi Setup

Enable SPI and add the SPI1 overlay. On Raspberry Pi OS Bookworm, edit:

```bash
sudo nano /boot/firmware/config.txt
```

On older Raspberry Pi OS releases, the file may be `/boot/config.txt` instead.
Add these lines:

```text
dtparam=spi=on
dtoverlay=spi1-1cs,cs0_pin=17
```

Do not use plain `dtoverlay=spi1-1cs` for this project, because its default CE0
pin is GPIO 18, which is already the heater SSR control pin. Reboot after
changing the config:

```bash
sudo reboot
```

After reboot, check that SPI1 is available:

```bash
ls /dev/spidev1.0
```

If that file does not exist, the Python script will fail before talking to the
LCD. Check all visible SPI device nodes:

```bash
ls -l /dev/spidev*
```

Also check that the overlay line is in the active boot config and is not
commented out with `#`:

```bash
grep -n "spi" /boot/firmware/config.txt
```

If `/boot/firmware/config.txt` does not exist on your Raspberry Pi OS image,
use `/boot/config.txt` instead.

Install/update the backend dependencies:

```bash
cd backend
python -m pip install -r requirements.txt
```

Run the LCD smoke test from the repository root:

```bash
python backend/hardware/lcd_st7796_test.py
```

You should see a full-screen 480 x 320 landscape color test card with a border
and center cross.
Leave the main roasting backend stopped for this first test. The LCD uses SPI1,
while the MAX31855 thermocouple stays on SPI0.

Optional image test:

```bash
python backend/hardware/lcd_st7796_test.py --image path/to/test.jpg
```

If you need to compare orientations:

```bash
python backend/hardware/lcd_st7796_test.py --rotation 0
python backend/hardware/lcd_st7796_test.py --rotation 90
python backend/hardware/lcd_st7796_test.py --rotation 180
python backend/hardware/lcd_st7796_test.py --rotation 270
```

## Runtime LCD Dashboard

After the smoke test works, the LCD can run as a small realtime dashboard. It
does not read the thermocouple or control GPIO directly. Instead, it connects to
the existing backend WebSocket and displays the same kind of telemetry used by
the web frontend: temperature, target temperature, rate of rise, heater output,
fan speed, roast state, and a small temperature trend chart.

For the normal roast backend, start the API first:

```bash
python backend/api/main.py
```

Then start the LCD dashboard from another terminal:

```bash
python backend/hardware/lcd_dashboard.py
```

For the hardware bench server, start:

```bash
python backend/api/hardware_test.py
```

Then run:

```bash
python backend/hardware/lcd_dashboard.py --mode bench
```

The default dashboard WebSocket URLs are:

| Mode | WebSocket URL |
| --- | --- |
| Roast | `ws://127.0.0.1:8000/ws/telemetry` |
| Bench | `ws://127.0.0.1:8001/ws/bench` |

Override the URL if the backend is on another host:

```bash
python backend/hardware/lcd_dashboard.py --ws-url ws://10.64.26.141:8000/ws/telemetry
```

If the dashboard is upside down or rotated the wrong way, change the rotation:

```bash
python backend/hardware/lcd_dashboard.py --rotation 270
```

If the screen stays white or black:

- Check that SPI1 is enabled and `/dev/spidev1.0` exists.
- Check that LCD `CS` is on physical pin 11, not physical pin 12.
- Check that `dtoverlay=spi1-1cs,cs0_pin=17` is in the active boot config.
- If Python raises `FileNotFoundError` or says it cannot find `/dev/spidev1.0`,
  fix the SPI1 overlay first; it is not an LCD wiring problem yet.
- Try a slower SPI clock: `python backend/hardware/lcd_st7796_test.py --speed 8000000`.
- For the dashboard, try: `python backend/hardware/lcd_dashboard.py --speed 8000000`.
- If colors look swapped, the LCD works; the `MADCTL` color-order byte in the
  script may need changing for that exact panel revision.
