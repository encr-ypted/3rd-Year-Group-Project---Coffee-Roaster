"""
Landscape LCD dashboard for the coffee roaster.

Run the main roaster API first:
    python backend/api/main.py

Then run this display client on the Raspberry Pi:
    python backend/hardware/lcd_dashboard.py

For the hardware bench server:
    python backend/hardware/lcd_dashboard.py --mode bench
"""

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import time

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("LCD dashboard needs Pillow. Try: pip install Pillow") from exc

try:
    from websocket import (
        WebSocketConnectionClosedException,
        WebSocketTimeoutException,
        create_connection,
    )
except ImportError as exc:
    raise SystemExit(
        "LCD dashboard needs websocket-client. Try: pip install websocket-client"
    ) from exc

from lcd_st7796_test import LCD_CS, SPI_BUS, SPI_DEVICE, ST7796Display, image_to_rgb565


DEFAULT_WS_URLS = {
    "roast": "ws://127.0.0.1:8000/ws/telemetry",
    "bench": "ws://127.0.0.1:8001/ws/bench",
}

BG = (18, 16, 14)
CARD = (28, 24, 20)
CARD_ALT = (22, 20, 18)
BORDER = (54, 45, 36)
TEXT = (246, 241, 232)
MUTED = (146, 136, 123)
DIM = (86, 78, 68)
GOLD = (212, 162, 78)
AMBER = (245, 158, 11)
ORANGE = (249, 115, 22)
EMERALD = (52, 211, 153)
SKY = (56, 189, 248)
RED = (239, 68, 68)


@dataclass
class DashboardState:
    connected: bool = False
    mode: str = "roast"
    temp: float | None = None
    target: float | None = None
    ror: float = 0.0
    heater_pwm: float = 0.0
    fan_pwm: float = 0.0
    state: str = "IDLE"
    elapsed_s: float = 0.0
    error: str = ""
    last_update: float = 0.0
    samples: deque = field(default_factory=lambda: deque(maxlen=120))


def clamp(value, low, high):
    return max(low, min(high, value))


def as_float(value, fallback=None):
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def load_font(size, bold=False):
    family = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    paths = (
        f"/usr/share/fonts/truetype/dejavu/{family}",
        f"/usr/share/fonts/dejavu/{family}",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    )
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def load_fonts():
    return {
        "title": load_font(20, bold=True),
        "label": load_font(11, bold=True),
        "small": load_font(10),
        "body": load_font(13),
        "body_bold": load_font(13, bold=True),
        "metric": load_font(22, bold=True),
        "temp": load_font(58, bold=True),
        "state": load_font(16, bold=True),
    }


def text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_card(draw, box, fill=CARD):
    draw.rounded_rectangle(box, radius=8, fill=fill, outline=BORDER, width=1)


def draw_right_text(draw, x, y, text, font, fill):
    width, _ = text_size(draw, text, font)
    draw.text((x - width, y), text, font=font, fill=fill)


def state_color(state):
    return {
        "IDLE": DIM,
        "PREHEAT": AMBER,
        "ROASTING": ORANGE,
        "COOLING": SKY,
        "ERROR": RED,
        "BENCH": SKY,
        "BENCH IDLE": DIM,
    }.get(state, GOLD)


def fmt_number(value, digits=1, empty="--"):
    if value is None:
        return empty
    return f"{value:.{digits}f}"


def fmt_elapsed(seconds):
    seconds = int(max(0, seconds))
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def draw_progress(draw, box, percent, color):
    x0, y0, x1, y1 = box
    percent = clamp(float(percent or 0), 0, 100)
    draw.rounded_rectangle(box, radius=4, fill=(42, 37, 32))
    if percent > 0:
        filled = int(x0 + ((x1 - x0) * percent / 100))
        draw.rounded_rectangle((x0, y0, filled, y1), radius=4, fill=color)


def draw_temperature_card(draw, state, fonts):
    draw_card(draw, (10, 50, 230, 218))
    draw.text((24, 64), "CURRENT TEMP", font=fonts["label"], fill=MUTED)

    temp_text = fmt_number(state.temp, 1)
    draw.text((22, 86), temp_text, font=fonts["temp"], fill=TEXT)
    unit_x = 22 + text_size(draw, temp_text, fonts["temp"])[0] + 5
    draw.text((unit_x, 128), "C", font=fonts["metric"], fill=MUTED)

    temp_min = 20
    temp_max = 230
    temp_value = state.temp if state.temp is not None else temp_min
    progress = clamp(((temp_value - temp_min) / (temp_max - temp_min)) * 100, 0, 100)
    draw_progress(draw, (24, 180, 216, 190), progress, GOLD)
    draw.text((24, 197), "20 C", font=fonts["small"], fill=DIM)
    draw_right_text(draw, 216, 197, "230 C", fonts["small"], DIM)


def draw_status_card(draw, state, fonts):
    draw_card(draw, (240, 50, 470, 96), fill=CARD_ALT)
    color = EMERALD if state.connected else RED
    label = "ONLINE" if state.connected else "OFFLINE"
    draw.ellipse((254, 65, 264, 75), fill=color)
    draw.text((272, 61), label, font=fonts["label"], fill=color)

    current_state = state.state or "IDLE"
    pill_color = state_color(current_state)
    draw.rounded_rectangle((356, 58, 458, 88), radius=8, fill=(36, 31, 27))
    draw_right_text(draw, 448, 64, current_state[:11], fonts["body_bold"], pill_color)


def draw_metric_card(draw, box, label, value, unit, color, fonts):
    draw_card(draw, box)
    x0, y0, x1, y1 = box
    draw.text((x0 + 12, y0 + 10), label, font=fonts["label"], fill=MUTED)
    value_text = str(value)
    draw.text((x0 + 12, y0 + 27), value_text, font=fonts["metric"], fill=color)
    draw.text(
        (x0 + 15 + text_size(draw, value_text, fonts["metric"])[0], y0 + 35),
        unit,
        font=fonts["small"],
        fill=MUTED,
    )
    draw.line((x0 + 12, y1 - 10, x1 - 12, y1 - 10), fill=(46, 39, 33))


def draw_output_card(draw, state, fonts):
    draw_card(draw, (240, 166, 470, 218))
    draw.text((252, 176), "OUTPUTS", font=fonts["label"], fill=MUTED)

    draw.text((252, 194), "Fan", font=fonts["small"], fill=MUTED)
    draw_progress(draw, (286, 197, 388, 205), state.fan_pwm, SKY)
    draw_right_text(draw, 454, 191, f"{state.fan_pwm:.0f}%", fonts["body_bold"], SKY)

    draw.text((252, 208), "Heat", font=fonts["small"], fill=MUTED)
    draw_progress(draw, (286, 211, 388, 217), state.heater_pwm, ORANGE)
    draw_right_text(draw, 454, 205, f"{state.heater_pwm:.0f}%", fonts["body_bold"], ORANGE)


def draw_chart(draw, state, fonts):
    box = (10, 230, 470, 310)
    draw_card(draw, box, fill=(20, 18, 16))
    x0, y0, x1, y1 = box
    draw.text((x0 + 12, y0 + 8), "TEMPERATURE TREND", font=fonts["label"], fill=MUTED)
    draw_right_text(draw, x1 - 12, y0 + 8, fmt_elapsed(state.elapsed_s), fonts["body_bold"], GOLD)

    chart = (x0 + 12, y0 + 28, x1 - 12, y1 - 10)
    cx0, cy0, cx1, cy1 = chart
    draw.rectangle(chart, outline=(43, 36, 31))
    for i in range(1, 4):
        y = cy0 + ((cy1 - cy0) * i // 4)
        draw.line((cx0, y, cx1, y), fill=(33, 29, 25))

    values = [sample for sample in state.samples if sample is not None]
    if len(values) < 2:
        draw.text((cx0 + 12, cy0 + 18), "Waiting for telemetry", font=fonts["body"], fill=DIM)
        return

    low = min(values)
    high = max(values)
    if state.target:
        low = min(low, state.target)
        high = max(high, state.target)
    if high - low < 5:
        high += 2.5
        low -= 2.5

    def point(index, value):
        x = cx0 + int((cx1 - cx0) * index / max(1, len(values) - 1))
        y = cy1 - int((cy1 - cy0) * (value - low) / (high - low))
        return x, y

    if state.target:
        target_y = point(0, state.target)[1]
        draw.line((cx0, target_y, cx1, target_y), fill=(92, 69, 42), width=1)

    points = [point(index, value) for index, value in enumerate(values)]
    draw.line(points, fill=GOLD, width=2)
    draw.ellipse((points[-1][0] - 3, points[-1][1] - 3, points[-1][0] + 3, points[-1][1] + 3), fill=TEXT)


def render_dashboard(state, width, height, fonts):
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    for x in range(width):
        blend = x / max(1, width - 1)
        color = (
            int(GOLD[0] * (1 - blend) + ORANGE[0] * blend),
            int(GOLD[1] * (1 - blend) + ORANGE[1] * blend),
            int(GOLD[2] * (1 - blend) + ORANGE[2] * blend),
        )
        draw.line((x, 0, x, 3), fill=color)

    draw.text((14, 14), "Smart Roaster", font=fonts["title"], fill=TEXT)
    subtitle = state.error if state.error else "LCD Roast Monitor"
    draw.text((164, 19), subtitle[:42], font=fonts["small"], fill=MUTED)
    draw_right_text(draw, width - 12, 17, time.strftime("%H:%M:%S"), fonts["body_bold"], MUTED)

    draw_temperature_card(draw, state, fonts)
    draw_status_card(draw, state, fonts)

    target = fmt_number(state.target, 0)
    draw_metric_card(draw, (240, 106, 352, 156), "TARGET", target, "C", GOLD, fonts)

    ror = f"{state.ror:+.1f}"
    ror_color = EMERALD if state.ror >= 0 else SKY
    draw_metric_card(draw, (358, 106, 470, 156), "ROR", ror, "C/min", ror_color, fonts)

    draw_output_card(draw, state, fonts)
    draw_chart(draw, state, fonts)
    return image


def update_state_from_message(state, message):
    msg_type = message.get("type")
    state.last_update = time.monotonic()
    state.error = ""

    if msg_type == "telemetry":
        state.temp = as_float(message.get("temp"), state.temp)
        state.target = as_float(message.get("target"), state.target)
        state.ror = as_float(message.get("ror"), state.ror) or 0.0
        state.heater_pwm = clamp(as_float(message.get("heater_pwm"), state.heater_pwm) or 0, 0, 100)
        state.fan_pwm = clamp(as_float(message.get("fan_pwm"), state.fan_pwm) or 0, 0, 100)
        state.elapsed_s = as_float(message.get("timestamp"), state.elapsed_s) or 0.0
        state.state = str(message.get("state", state.state))
    elif msg_type == "bench_telemetry":
        state.temp = as_float(message.get("temp"), state.temp)
        state.target = None
        state.ror = 0.0
        state.heater_pwm = clamp(as_float(message.get("heater_pwm"), state.heater_pwm) or 0, 0, 100)
        state.fan_pwm = clamp(as_float(message.get("fan_pwm"), state.fan_pwm) or 0, 0, 100)
        state.state = "BENCH" if message.get("session_active") else "BENCH IDLE"
    elif msg_type == "bench_result" and "sensors" in message:
        sensors = message["sensors"]
        state.temp = as_float(sensors.get("temp_c"), state.temp)
        state.heater_pwm = clamp(as_float(sensors.get("heater_pwm"), state.heater_pwm) or 0, 0, 100)
        state.fan_pwm = clamp(as_float(sensors.get("fan_pwm"), state.fan_pwm) or 0, 0, 100)
        state.state = "BENCH" if sensors.get("session_active") else "BENCH IDLE"
    elif msg_type == "system_state":
        state.state = str(message.get("state", state.state))
    elif msg_type == "error":
        state.state = "ERROR"
        state.error = str(message.get("msg", "Hardware error"))[:42]

    if state.temp is not None and msg_type in ("telemetry", "bench_telemetry", "bench_result"):
        state.samples.append(state.temp)


def connect_ws(url, mode):
    ws = create_connection(url, timeout=1.0)
    ws.settimeout(0.05)
    if mode == "roast":
        ws.send(json.dumps({"action": "GET_STATE"}))
    return ws


def run_dashboard(args):
    ws_url = args.ws_url or DEFAULT_WS_URLS[args.mode]
    state = DashboardState(mode=args.mode)
    fonts = load_fonts()

    lcd = ST7796Display(
        rotation=args.rotation,
        bus=args.bus,
        device=args.device,
        cs_pin=args.cs_pin,
        speed_hz=args.speed,
    )
    ws = None
    frame_interval = 1 / max(0.2, args.fps)
    next_frame = 0.0

    try:
        lcd.initialize()
        while True:
            if ws is None:
                state.connected = False
                state.error = f"Connecting to {ws_url}"
                lcd.draw_rgb565(image_to_rgb565(render_dashboard(state, lcd.width, lcd.height, fonts)))
                try:
                    ws = connect_ws(ws_url, args.mode)
                    state.connected = True
                    state.error = ""
                except Exception as exc:
                    state.error = f"Offline: {exc.__class__.__name__}"
                    lcd.draw_rgb565(image_to_rgb565(render_dashboard(state, lcd.width, lcd.height, fonts)))
                    time.sleep(args.reconnect_delay)
                    continue

            try:
                raw = ws.recv()
                update_state_from_message(state, json.loads(raw))
                state.connected = True
            except WebSocketTimeoutException:
                pass
            except (WebSocketConnectionClosedException, OSError, json.JSONDecodeError) as exc:
                state.connected = False
                state.error = f"Disconnected: {exc.__class__.__name__}"
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None

            now = time.monotonic()
            if now >= next_frame:
                image = render_dashboard(state, lcd.width, lcd.height, fonts)
                lcd.draw_rgb565(image_to_rgb565(image))
                next_frame = now + frame_interval
    except KeyboardInterrupt:
        pass
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        lcd.close()


def main():
    parser = argparse.ArgumentParser(description="ST7796 landscape roaster dashboard")
    parser.add_argument("--mode", choices=("roast", "bench"), default="roast")
    parser.add_argument("--ws-url", help="Override WebSocket URL")
    parser.add_argument("--fps", type=float, default=2.0, help="LCD refresh rate")
    parser.add_argument("--reconnect-delay", type=float, default=2.0)
    parser.add_argument("--speed", type=int, default=16_000_000, help="SPI speed in Hz")
    parser.add_argument("--bus", type=int, default=SPI_BUS, help="SPI bus number")
    parser.add_argument(
        "--device", type=int, default=SPI_DEVICE, help="SPI device/chip select number"
    )
    parser.add_argument("--cs-pin", type=int, default=LCD_CS, help="LCD CS BCM GPIO")
    parser.add_argument(
        "--rotation",
        type=int,
        default=90,
        choices=(0, 90, 180, 270),
        help="Display rotation in degrees",
    )
    args = parser.parse_args()
    run_dashboard(args)


if __name__ == "__main__":
    main()
