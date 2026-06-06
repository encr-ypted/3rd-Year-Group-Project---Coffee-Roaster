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
import math
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

from lcd_st7796_test import (
    LCD_BACKLIGHT_BRIGHTNESS,
    LCD_CS,
    LCD_PIXEL_BRIGHTNESS,
    SPI_BUS,
    SPI_DEVICE,
    ST7796Display,
    image_to_rgb565,
)
from roast_ramp import effective_setpoint


DEFAULT_WS_URLS = {
    "roast": "ws://127.0.0.1:8000/ws/telemetry",
    "bench": "ws://127.0.0.1:8001/ws/bench",
}

BG = (30, 28, 24)
CARD = (42, 38, 32)
CARD_ALT = (34, 32, 28)
BORDER = (72, 62, 50)
TEXT = (255, 252, 245)
MUTED = (178, 168, 152)
DIM = (118, 108, 94)
GOLD = (212, 162, 78)
AMBER = (245, 158, 11)
ORANGE = (249, 115, 22)
EMERALD = (52, 211, 153)
SKY = (56, 189, 248)
RED = (239, 68, 68)
PROFILE_MAX = (110, 105, 100)
CHART_BG = (20, 18, 16)

TEMP_MIN = 20
TEMP_MAX = 230

STATE_LABELS = {
    "IDLE": "Idle",
    "PREHEAT": "Preheating",
    "ROASTING": "Roasting",
    "COOLING": "Cooling",
    "ERROR": "Error",
    "BENCH": "Bench",
    "BENCH IDLE": "Bench idle",
}


@dataclass
class DashboardState:
    connected: bool = False
    mode: str = "roast"
    temp: float | None = None
    target: float | None = None
    setpoint: float | None = None
    start_temp: float | None = None
    ramp_midpoint_min: float = 2.0
    ramp_steepness: float = 1.0
    sensor_fault: str | None = None
    heater_pwm: float = 0.0
    fan_pwm: float = 0.0
    state: str = "IDLE"
    elapsed_s: float = 0.0
    error: str = ""
    last_update: float = 0.0
    samples: deque = field(default_factory=lambda: deque(maxlen=180))


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


def state_label(state):
    return STATE_LABELS.get(state, state.replace("_", " ").title())


def is_roasting(state):
    return state.state in ("PREHEAT", "ROASTING")


def temp_progress_percent(temp):
    if temp is None:
        return 0.0
    return clamp(((temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * 100, 0, 100)


def estimate_roast_duration_sec(start_temp, target_temp, midpoint_min, steepness=1.0):
    if start_temp is None or target_temp is None or target_temp <= start_temp:
        return 12 * 60
    for sec in range(0, 30 * 60 + 1, 15):
        if (
            effective_setpoint(start_temp, target_temp, sec, midpoint_min, steepness)
            >= target_temp - 0.5
        ):
            return sec
    return 12 * 60


def build_planned_curve(state, step_sec=20):
    target = state.target
    start = state.start_temp
    if target is None or start is None or target <= 0:
        return []

    duration = estimate_roast_duration_sec(
        start, target, state.ramp_midpoint_min, state.ramp_steepness
    )
    points = []
    for sec in range(0, duration + 1, step_sec):
        points.append(
            (
                sec,
                effective_setpoint(
                    start,
                    target,
                    sec,
                    state.ramp_midpoint_min,
                    state.ramp_steepness,
                ),
            )
        )
    return points


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


def draw_dashed_polyline(draw, points, fill, width=1, dash=5, gap=4):
    if len(points) < 2:
        return
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        length = math.hypot(x1 - x0, y1 - y0)
        if length == 0:
            continue
        dx = (x1 - x0) / length
        dy = (y1 - y0) / length
        pos = 0.0
        draw_on = True
        while pos < length:
            segment = dash if draw_on else gap
            end = min(pos + segment, length)
            if draw_on:
                draw.line(
                    (x0 + dx * pos, y0 + dy * pos, x0 + dx * end, y0 + dy * end),
                    fill=fill,
                    width=width,
                )
            pos = end
            draw_on = not draw_on


def draw_dashed_hline(draw, x0, x1, y, fill, width=1, dash=6, gap=4):
    draw_dashed_polyline(draw, [(x0, y), (x1, y)], fill, width=width, dash=dash, gap=gap)


def draw_centered_text(draw, box, text, font, fill, y_offset=0):
    x0, y0, x1, y1 = box
    width, height = text_size(draw, text, font)
    x = x0 + ((x1 - x0) - width) // 2
    y = y0 + ((y1 - y0) - height) // 2 + y_offset
    draw.text((x, y), text, font=font, fill=fill)


def draw_temperature_card(draw, state, fonts):
    draw_card(draw, (10, 50, 230, 210))
    draw.text((24, 62), "Temperature", font=fonts["label"], fill=MUTED)

    temp_text = fmt_number(state.temp, 1)
    draw.text((22, 82), temp_text, font=fonts["temp"], fill=TEXT)
    unit_x = 22 + text_size(draw, temp_text, fonts["temp"])[0] + 5
    draw.text((unit_x, 124), "°C", font=fonts["metric"], fill=MUTED)

    if state.sensor_fault:
        fault = f"TC: {state.sensor_fault}"[:30]
        draw.text((24, 158), fault, font=fonts["small"], fill=AMBER)

    progress = temp_progress_percent(state.temp)
    draw_progress(draw, (24, 172, 216, 182), progress, GOLD)
    pct_text = f"{progress:.0f}%"
    pct_w, _ = text_size(draw, pct_text, fonts["body_bold"])
    draw.text((120 - pct_w // 2, 186), pct_text, font=fonts["body_bold"], fill=TEXT)
    draw.text((24, 186), f"{TEMP_MIN}°", font=fonts["small"], fill=DIM)
    draw_right_text(draw, 216, 186, f"{TEMP_MAX}°", fonts["small"], DIM)


def draw_connection_badge(draw, state, fonts):
    draw_card(draw, (240, 50, 470, 92), fill=CARD_ALT)
    color = EMERALD if state.connected else RED
    label = "Online" if state.connected else "Offline"
    draw.ellipse((256, 68, 264, 76), fill=color)
    draw.text((272, 63), label, font=fonts["label"], fill=color)


def draw_mini_stat_card(draw, box, label, value, unit, value_color, fonts):
    draw_card(draw, box)
    x0, y0, x1, y1 = box
    label_w, _ = text_size(draw, label, fonts["small"])
    draw.text((x0 + ((x1 - x0) - label_w) // 2, y0 + 8), label, font=fonts["small"], fill=MUTED)
    value_text = str(value)
    draw_centered_text(draw, (x0, y0 + 18, x1, y1 - 14), value_text, fonts["metric"], value_color)
    unit_w, _ = text_size(draw, unit, fonts["small"])
    draw.text((x0 + ((x1 - x0) - unit_w) // 2, y1 - 18), unit, font=fonts["small"], fill=MUTED)


def draw_state_stat_card(draw, box, state, fonts):
    draw_card(draw, box)
    x0, y0, x1, y1 = box
    label_w, _ = text_size(draw, "State", fonts["small"])
    draw.text((x0 + ((x1 - x0) - label_w) // 2, y0 + 8), "State", font=fonts["small"], fill=MUTED)

    current = state.state or "IDLE"
    label = state_label(current)
    pill_color = state_color(current)
    pill_box = (x0 + 8, y0 + 30, x1 - 8, y1 - 10)
    draw.rounded_rectangle(pill_box, radius=8, fill=(36, 31, 27))
    draw_centered_text(draw, pill_box, label[:12], fonts["small"], pill_color, y_offset=1)


def roast_target_stat(state):
    if is_roasting(state):
        value = fmt_number(state.setpoint, 0)
        target = state.target
        setpoint = state.setpoint
        if target and setpoint and target > setpoint:
            unit = f"°C → {target:.0f}"
        else:
            unit = "°C"
        return "Setpoint", value, unit
    return "Target", fmt_number(state.target, 0), "°C"


def draw_roast_mini_stats(draw, state, fonts):
    label, value, unit = roast_target_stat(state)
    draw_mini_stat_card(draw, (240, 100, 316, 172), label, value, unit, GOLD, fonts)
    draw_mini_stat_card(
        draw,
        (318, 100, 394, 172),
        "Heater",
        f"{state.heater_pwm:.0f}",
        "%",
        TEXT,
        fonts,
    )
    draw_state_stat_card(draw, (396, 100, 470, 172), state, fonts)


def draw_bench_mini_stats(draw, state, fonts):
    draw_mini_stat_card(
        draw,
        (240, 100, 316, 172),
        "Heater",
        f"{state.heater_pwm:.0f}",
        "%",
        ORANGE,
        fonts,
    )
    draw_mini_stat_card(
        draw,
        (318, 100, 394, 172),
        "Fan",
        f"{state.fan_pwm:.0f}",
        "%",
        SKY,
        fonts,
    )
    draw_state_stat_card(draw, (396, 100, 470, 172), state, fonts)


def draw_bench_outputs(draw, state, fonts):
    draw_card(draw, (240, 178, 470, 214))
    draw.text((252, 186), "Outputs", font=fonts["small"], fill=MUTED)
    draw.text((252, 198), "Fan", font=fonts["small"], fill=MUTED)
    draw_progress(draw, (286, 201, 388, 207), state.fan_pwm, SKY)
    draw_right_text(draw, 454, 195, f"{state.fan_pwm:.0f}%", fonts["body_bold"], SKY)
    draw.text((252, 208), "Heat", font=fonts["small"], fill=MUTED)
    draw_progress(draw, (286, 211, 388, 217), state.heater_pwm, ORANGE)
    draw_right_text(draw, 454, 205, f"{state.heater_pwm:.0f}%", fonts["body_bold"], ORANGE)


def chart_y_range(state, live_temps, planned_temps):
    values = [temp for temp in live_temps if temp is not None]
    values.extend(planned_temps)
    if state.target:
        values.append(state.target)
    if not values:
        return 20.0, 230.0
    low = min(values)
    high = max(values)
    if high - low < 8:
        mid = (high + low) / 2
        low = mid - 4
        high = mid + 4
    low -= 2
    high += 2
    return low, high


def draw_chart(draw, state, fonts):
    chart_top = 178 if state.mode == "roast" else 220
    box = (10, chart_top, 470, 310)
    draw_card(draw, box, fill=CHART_BG)
    x0, y0, x1, y1 = box
    if state.mode == "bench":
        draw.text((x0 + 12, y0 + 8), "Temperature", font=fonts["label"], fill=MUTED)
        draw.text((x0 + 12, y0 + 20), "Live trace", font=fonts["small"], fill=DIM)
    else:
        draw.text((x0 + 12, y0 + 8), "Roast Profile", font=fonts["label"], fill=MUTED)
        draw.text((x0 + 12, y0 + 20), "Planned & live", font=fonts["small"], fill=DIM)
    draw_right_text(draw, x1 - 12, y0 + 10, fmt_elapsed(state.elapsed_s), fonts["body_bold"], GOLD)

    chart = (x0 + 12, y0 + 34, x1 - 12, y1 - 10)
    cx0, cy0, cx1, cy1 = chart
    draw.rectangle(chart, outline=(43, 36, 31))
    for i in range(1, 4):
        y = cy0 + ((cy1 - cy0) * i // 4)
        draw.line((cx0, y, cx1, y), fill=(33, 29, 25))

    live = [(t, temp) for t, temp in state.samples if temp is not None]
    planned = build_planned_curve(state) if state.mode == "roast" else []

    if len(live) < 2 and not planned:
        draw.text((cx0 + 12, cy0 + 20), "Waiting for telemetry", font=fonts["body"], fill=DIM)
        return

    t_max = state.elapsed_s + 30
    if live:
        t_max = max(t_max, live[-1][0])
    if planned:
        t_max = max(t_max, planned[-1][0])
    t_max = max(60.0, t_max)

    live_temps = [temp for _, temp in live]
    planned_temps = [temp for _, temp in planned]
    low, high = chart_y_range(state, live_temps, planned_temps)

    def chart_point(t_sec, temp_c):
        x = cx0 + int((cx1 - cx0) * t_sec / t_max)
        y = cy1 - int((cy1 - cy0) * (temp_c - low) / (high - low))
        return x, y

    if state.mode == "roast" and state.target:
        target_y = chart_point(0, state.target)[1]
        draw_dashed_hline(draw, cx0, cx1, target_y, PROFILE_MAX, width=1)

    if planned:
        planned_points = [chart_point(t, temp) for t, temp in planned]
        draw_dashed_polyline(draw, planned_points, GOLD, width=2, dash=6, gap=4)

    if len(live) >= 2:
        live_points = [chart_point(t, temp) for t, temp in live]
        draw.line(live_points, fill=ORANGE, width=2)
        last_x, last_y = live_points[-1]
        draw.ellipse((last_x - 3, last_y - 3, last_x + 3, last_y + 3), fill=TEXT)


def header_subtitle(state):
    if state.error:
        return state.error[:42]
    if state.mode == "bench":
        return "Bench Monitor"
    return "Roast Monitor"


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
    draw.text((164, 19), header_subtitle(state), font=fonts["small"], fill=MUTED)
    draw_right_text(draw, width - 12, 17, time.strftime("%H:%M:%S"), fonts["body_bold"], MUTED)

    draw_temperature_card(draw, state, fonts)
    draw_connection_badge(draw, state, fonts)

    if state.mode == "bench":
        draw_bench_mini_stats(draw, state, fonts)
        draw_bench_outputs(draw, state, fonts)
    else:
        draw_roast_mini_stats(draw, state, fonts)

    draw_chart(draw, state, fonts)
    return image


def update_state_from_message(state, message):
    msg_type = message.get("type")
    state.last_update = time.monotonic()
    state.error = ""

    if msg_type == "telemetry":
        prev_state = state.state
        new_state = str(message.get("state", state.state))
        if prev_state == "IDLE" and new_state in ("PREHEAT", "ROASTING"):
            state.samples.clear()
            if state.temp is not None:
                state.start_temp = state.temp
        if new_state == "IDLE":
            state.start_temp = None

        state.temp = as_float(message.get("temp"), state.temp)
        state.target = as_float(message.get("target"), state.target)
        state.setpoint = as_float(message.get("setpoint"), state.setpoint)
        state.ramp_midpoint_min = (
            as_float(message.get("ramp_midpoint_min"), state.ramp_midpoint_min) or 2.0
        )
        state.ramp_steepness = (
            as_float(message.get("ramp_steepness"), state.ramp_steepness) or 1.0
        )
        fault = message.get("sensor_fault")
        state.sensor_fault = str(fault) if fault else None
        state.heater_pwm = clamp(as_float(message.get("heater_pwm"), state.heater_pwm) or 0, 0, 100)
        state.fan_pwm = clamp(as_float(message.get("fan_pwm"), state.fan_pwm) or 0, 0, 100)
        state.elapsed_s = as_float(message.get("timestamp"), state.elapsed_s) or 0.0
        state.state = new_state

        if state.start_temp is None and state.temp is not None and new_state != "IDLE":
            state.start_temp = state.temp
    elif msg_type == "bench_telemetry":
        state.temp = as_float(message.get("temp"), state.temp)
        state.target = None
        state.setpoint = None
        state.sensor_fault = None
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
        if msg_type == "telemetry":
            state.samples.append((state.elapsed_s, state.temp))
        else:
            state.samples.append((len(state.samples), state.temp))


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

    pixel_brightness = args.pixel_brightness

    lcd = ST7796Display(
        rotation=args.rotation,
        bus=args.bus,
        device=args.device,
        cs_pin=args.cs_pin,
        speed_hz=args.speed,
        backlight_brightness=args.backlight,
        display_inversion=not args.no_inversion,
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
                lcd.draw_rgb565(
                    image_to_rgb565(
                        render_dashboard(state, lcd.width, lcd.height, fonts),
                        pixel_brightness=pixel_brightness,
                    )
                )
                try:
                    ws = connect_ws(ws_url, args.mode)
                    state.connected = True
                    state.error = ""
                except Exception as exc:
                    state.error = f"Offline: {exc.__class__.__name__}"
                    lcd.draw_rgb565(
                        image_to_rgb565(
                            render_dashboard(state, lcd.width, lcd.height, fonts),
                            pixel_brightness=pixel_brightness,
                        )
                    )
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
                lcd.draw_rgb565(image_to_rgb565(image, pixel_brightness=pixel_brightness))
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
        help="Software brightness boost for dashboard frames (1.0 = unchanged)",
    )
    parser.add_argument(
        "--no-inversion",
        action="store_true",
        help="Disable display inversion (try if the panel looks washed out)",
    )
    args = parser.parse_args()
    run_dashboard(args)


if __name__ == "__main__":
    main()
