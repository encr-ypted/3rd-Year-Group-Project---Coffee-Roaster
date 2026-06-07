# Raspberry Pi GPIO pinout — Coffee Roaster

Wiring reference for the **40-pin Raspberry Pi header**. All GPIO numbers are **BCM** (Broadcom), not board/WiringPi numbering.

Physical pin numbers match the standard Pi pinout (pin 1 = 3.3 V at the corner near the SD card, odd pins on the left column).

Config source: `config.py` (heater, fan, thermocouple) and `hardware/display/st7796.py` (LCD).

---

## Quick reference — all used pins

| Component | Signal | BCM GPIO | Physical pin | SPI / bus |
|-----------|--------|----------|--------------|-----------|
| **Heater** | SSR control | **23** | **16** | — |
| **Fan** | PWM speed | **12** | **32** | — |
| **Thermocouple** | CS (CE1) | **7** | **26** | SPI0 |
| **Thermocouple** | SCLK | **11** | **23** | SPI0 |
| **Thermocouple** | MISO (DO) | **9** | **21** | SPI0 |
| **Thermocouple** | MOSI | **10** | **19** | SPI0 (shared; MAX31855 reads via MISO) |
| **LCD** | CS | **17** | **11** | SPI1 (`/dev/spidev1.0`) |
| **LCD** | MOSI (SDI) | **20** | **38** | SPI1 |
| **LCD** | SCLK (SCK) | **21** | **40** | SPI1 |
| **LCD** | MISO (SDO) | **19** | **35** | SPI1 (optional) |
| **LCD** | DC / RS | **25** | **22** | — |
| **LCD** | RESET / RST | **24** | **18** | — |
| **LCD** | Backlight (BL) | **22** | **15** | — |
| **Power** | 3.3 V (sensors, LCD) | — | **1** or **17** | — |
| **Power** | 5 V (if module needs it) | — | **2** or **4** | — |
| **Ground** | Common GND | — | **6**, **9**, **14**, **20**, **25**, **30**, **34**, **39** | — |

**12 GPIO lines used** (7, 9, 10, 11, 12, 17, 20, 21, 22, 23, 24, 25). MISO on GPIO 19 is optional for the LCD.

---

## Do not use (conflicts)

| BCM GPIO | Physical pin | Why |
|----------|--------------|-----|
| **18** | **12** | Default SPI1 CE0 — remapped to GPIO 17 for this project |
| **8** | **24** | SPI0 CE0 — thermocouple uses **CE1** (GPIO 7) instead |

Do not move the heater to GPIO 18; firmware and docs assume **GPIO 23** (pin 16). LCD backlight is **GPIO 22** (pin 15), not 23.

---

## Heater (SSR)

Solid-state relay driven by time-proportional software (`hardware/devices/heater.py`).

| From | To | BCM GPIO | Physical pin |
|------|-----|----------|--------------|
| Pi GPIO | SSR control input (+) | **23** | **16** |
| Pi GND | SSR control input (−) / module GND | — | e.g. **6**, **14**, **20** |

| Property | Value |
|----------|-------|
| `config.py` | `HEATER_GPIO = 23` |
| Logic | Active **high** — GPIO high = heater on for the current PWM window |
| Control | ~1 s window, duty 0–100% (`HEATER_CONTROL_WINDOW_S`) |

Use an SSR rated for your heater load. Keep mains wiring separate from low-voltage Pi wiring.

---

## Fan (PWM)

Drum / cooling fan via PWM (`hardware/devices/motor.py`).

| From | To | BCM GPIO | Physical pin |
|------|-----|----------|--------------|
| Pi PWM output | Fan driver (MOSFET gate / PWM input) | **12** | **32** |
| Pi GND | Driver GND | — | any GND |

| Property | Value |
|----------|-------|
| `config.py` | `FAN_PWM_GPIO = 12`, `FAN_PWM_FREQUENCY_HZ = 1000` |
| Logic | `active_high=False` — software uses inverted PWM; verify spin direction/speed on the bench |
| Default | 100% when on (`FAN_DEFAULT_SPEED = 1.0`) |

GPIO 12 supports hardware PWM (PWM0). Use a suitable transistor or MOSFET if the fan draws more than a few milliamps from the Pi.

---

## Bean temperature (MAX31855 thermocouple)

SPI0 + chip select on CE1 (`hardware/devices/thermocouple.py`, Adafruit MAX31855 library).

### Module → Pi

| MAX31855 label | Pi signal | BCM GPIO | Physical pin |
|----------------|-----------|----------|--------------|
| VIN / VCC | 3.3 V | — | **1** or **17** |
| GND | GND | — | e.g. **9**, **14** |
| SCK / CLK | SPI0 SCLK | **11** | **23** |
| CS | SPI0 CE1 | **7** | **26** |
| SO / DO (data out) | SPI0 MISO | **9** | **21** |

| Property | Value |
|----------|-------|
| `config.py` | `THERMOCOUPLE_CS_GPIO = 7` |
| Device node | Uses `board.SPI()` → `/dev/spidev0.0` with manual CS on GPIO 7 |
| Probe | K-type (or match your breakout board) |

After wiring, confirm SPI0:

```bash
ls /dev/spidev0.0
```

Enable with `dtparam=spi=on` in `/boot/firmware/config.txt` (or `/boot/config.txt` on older OS).

---

## LCD (ST7796, 3.5″ SPI)

Separate **SPI1** bus so LCD traffic does not share SPI0 with the thermocouple (`hardware/display/st7796.py`).

### Required boot config

In `/boot/firmware/config.txt` (Bookworm) or `/boot/config.txt`:

```text
dtparam=spi=on
dtoverlay=spi1-1cs,cs0_pin=17
```

Reboot, then check:

```bash
ls /dev/spidev1.0
```

### LCD module → Pi

| LCD label | Pi signal | BCM GPIO | Physical pin | Notes |
|-----------|-----------|----------|--------------|-------|
| VCC | 3.3 V | — | **1** or **17** | Use 5 V only if your module docs require it |
| GND | GND | — | e.g. **6**, **9** | |
| CS / LCD_CS | SPI1 CS (remapped) | **17** | **11** | **Not** pin 12 (GPIO 18) |
| RESET / RST | GPIO out | **24** | **18** | |
| DC / RS | GPIO out | **25** | **22** | Data vs command |
| SDI / MOSI | SPI1 MOSI | **20** | **38** | |
| SCK / SCLK | SPI1 SCLK | **21** | **40** | |
| LED / BL | Backlight | **22** | **15** | PWM brightness in software |
| SDO / MISO | SPI1 MISO | **19** | **35** | Optional for display-only |
| Touch (T_*) | — | — | — | Not connected |
| SD card (SD_*) | — | — | — | Not connected |

| Property | Value |
|----------|-------|
| SPI | Bus **1**, device **0** → `/dev/spidev1.0` |
| Rotation | 90° landscape (default in driver) |

Smoke test: `python hardware/display/st7796.py` (from `backend/` with venv). See also `docs/lcd_st7796_test.md`.

---

## SPI bus summary

```
SPI0 (/dev/spidev0.0)          SPI1 (/dev/spidev1.0)
├── SCLK  GPIO 11  pin 23      ├── SCLK  GPIO 21  pin 40
├── MOSI  GPIO 10  pin 19      ├── MOSI  GPIO 20  pin 38
├── MISO  GPIO  9  pin 21      ├── MISO  GPIO 19  pin 35
├── CE0   GPIO  8  pin 24  (unused)
└── CE1   GPIO  7  pin 26  ← MAX31855 CS
                               └── CS    GPIO 17  pin 11  ← LCD (overlay remap)
```

---

## 40-pin header map (used pins only)

Odd pins (left) and even pins (right), top to bottom:

```
     3.3V [ 1] [ 2] 5V
          [ 3] [ 4] 5V
          [ 5] [ 6] GND
          [ 7] [ 8]
  LCD CS [11] [12] GPIO 18 — do not use for LCD CS
          [13] [14] GND
LCD BL  [15] [16] HEATER GPIO 23
   3.3V [17] [18] LCD RST GPIO 24
TC MOSI [19] [20] GND
TC MISO [21] [22] LCD DC GPIO 25
TC SCLK [23] [24] SPI0 CE0 (unused)
      GND [25] [26] TC CS GPIO 7
          [27] [28]
      GND [29] [30] GND
          [31] [32] FAN PWM GPIO 12
          [33] [34] GND
LCD MISO [35] [36]
          [37] [38] SPI1 MOSI GPIO 20
      GND [39] [40] SPI1 SCLK GPIO 21
```

---

## Changing pins in software

| Setting | File | Key |
|---------|------|-----|
| Heater | `config.py` | `HEATER_GPIO` |
| Fan | `config.py` | `FAN_PWM_GPIO` |
| Thermocouple CS | `config.py` | `THERMOCOUPLE_CS_GPIO` |
| LCD CS, RST, DC, BL | `hardware/display/st7796.py` | `LCD_CS`, `LCD_RST`, `LCD_RS`, `LCD_LED` |

If you change LCD CS, update `dtoverlay=spi1-1cs,cs0_pin=...` to match and reboot.

---

## Permissions

The `pi` user (or whichever user runs the service) should be in the `gpio` and `spi` groups:

```bash
sudo usermod -aG gpio,spi pi
```

Reboot or re-login after adding groups.

---

## Related docs

- LCD bring-up: `lcd_st7796_test.md`
- Deploy on Pi: `../deploy/README.md`
- Backend overview: `../README.md`
