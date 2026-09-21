#!/usr/bin/env python3
"""
NookFrame weather server (Python edition)
-----------------------------------------

Serves a 600x800 weather PNG over plain HTTP for the Nook Simple Touch.

Run:
    python3 weather-server.py

Then point WeatherActivity.IMAGE_URL at:
    http://<this-pi-ip>:8080/weather.png

Toggle layouts in the browser:
    http://<pi>:8080/weather.png?o=portrait
    http://<pi>:8080/weather.png?o=landscape
    http://<pi>:8080/weather.png?o=landscape-preview   (un-rotated, for PC viewing)
"""

import io
import json
import math
import urllib.request
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from PIL import Image, ImageDraw, ImageFont

# -------- CONFIG ----------------------------------------------------------
PORT = 8080
LAT = 45.406254
LON = -75.729517
LABEL = "Ottawa"

DEFAULT_ORIENTATION = "portrait"        # 'portrait' | 'landscape'
LANDSCAPE_ROTATION = "cw"               # 'cw' | 'ccw'

HOURLY_HOURS = 8                        # how many hours to chart

PANEL_W, PANEL_H = 600, 800             # physical Nook panel

WMO = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Frz drizzle", 57: "Frz drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "T-storm + hail", 99: "T-storm + hail",
}

# --------------------------------------------------------------------------

def load_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def text_w(draw, text, font):
    if hasattr(draw, "textbbox"):
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l
    return draw.textsize(text, font=font)[0]


def draw_text_centered(draw, x, y, text, font):
    draw.text((x - text_w(draw, text, font) / 2, y), text, fill=0, font=font)


def draw_icon(draw, code, cx, cy, r):
    width = 3
    if code in (0, 1):
        draw.ellipse((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5),
                     outline=0, width=width)
        for i in range(8):
            a = (i / 8) * math.pi * 2
            x1, y1 = cx + math.cos(a) * r * 0.65, cy + math.sin(a) * r * 0.65
            x2, y2 = cx + math.cos(a) * r * 0.9,  cy + math.sin(a) * r * 0.9
            draw.line((x1, y1, x2, y2), fill=0, width=width)
    elif 71 <= code <= 86:
        for i in range(6):
            a = (i / 6) * math.pi * 2
            x2, y2 = cx + math.cos(a) * r * 0.8, cy + math.sin(a) * r * 0.8
            draw.line((cx, cy, x2, y2), fill=0, width=width)
    elif (51 <= code <= 67) or (80 <= code <= 82) or code >= 95:
        _cloud(draw, cx, cy - r * 0.2, r * 0.7, width)
        for i in (-1, 0, 1):
            x1 = cx + i * r * 0.35
            draw.line((x1, cy + r * 0.35, x1 - r * 0.12, cy + r * 0.7),
                      fill=0, width=width)
    else:
        _cloud(draw, cx, cy, r * 0.8, width)


def _cloud(draw, cx, cy, r, width):
    draw.arc((cx - r * 0.95, cy - r * 0.45, cx - r * 0.05, cy + r * 0.45),
             90, 270, fill=0, width=width)
    draw.arc((cx - r * 0.55, cy - r * 0.8, cx + r * 0.35, cy + r * 0.1),
             180, 342, fill=0, width=width)
    draw.arc((cx + r * 0.05, cy - r * 0.5, cx + r * 0.85, cy + r * 0.3),
             216, 90, fill=0, width=width)


def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code,"
        "relative_humidity_2m,uv_index"
        "&hourly=temperature_2m,precipitation_probability"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
        "precipitation_probability_max"
        "&forecast_days=3&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def day_name(date_str, idx):
    if idx == 0:
        return "Today"
    if idx == 1:
        return "Tmrw"
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")


def time_now_str():
    now = datetime.now()
    return now.strftime("%I:%M%p").lstrip("0").lower()


def current_hour_index(hourly_times):
    """Find the index in hourly arrays closest to current local time."""
    now = datetime.now()
    target = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H")
    for i, t in enumerate(hourly_times):
        if t.startswith(target):
            return i
    return 0


def draw_hourly_chart(draw, x, y, w, h, hourly, start_idx, hours):
    """Temperature line with per-hour value labels + precip probability bars
    along the bottom. Time on the x-axis as 12h am/pm."""
    temps = hourly["temperature_2m"][start_idx : start_idx + hours]
    probs = hourly["precipitation_probability"][start_idx : start_idx + hours]
    times = hourly["time"][start_idx : start_idx + hours]

    temps = [t if t is not None else 0 for t in temps]
    probs = [p if p is not None else 0 for p in probs]

    if len(temps) < 2:
        draw_text_centered(draw, x + w / 2, y + h / 2,
                           "No hourly data", load_font(16))
        return

    pad_left, pad_right = 28, 28
    pad_top, pad_bottom = 18, 26
    bar_band_h = 22
    plot_x0 = x + pad_left
    plot_x1 = x + w - pad_right
    plot_y0 = y + pad_top
    plot_y1 = y + h - pad_bottom
    plot_w = plot_x1 - plot_x0

    tmin, tmax = min(temps), max(temps)
    if tmax - tmin < 4:
        mid = (tmax + tmin) / 2
        tmin, tmax = mid - 2, mid + 2

    line_band_y0 = plot_y0
    line_band_y1 = plot_y1 - bar_band_h - 2

    def temp_to_y(t):
        frac = (t - tmin) / (tmax - tmin)
        return line_band_y1 - frac * (line_band_y1 - line_band_y0)

    n = len(temps)
    step = plot_w / (n - 1)

    # Precip bars
    bar_w = step * 0.55
    for i, p in enumerate(probs):
        cx = plot_x0 + i * step
        bh = (p / 100.0) * bar_band_h
        if bh < 1:
            continue
        bx0 = cx - bar_w / 2
        bx1 = cx + bar_w / 2
        by0 = plot_y1 - bh
        by1 = plot_y1
        draw.rectangle((bx0, by0, bx1, by1), fill=0)

    draw.line((plot_x0, plot_y1, plot_x1, plot_y1), fill=0, width=1)

    # Temp line + dots
    pts = [(plot_x0 + i * step, temp_to_y(t)) for i, t in enumerate(temps)]
    for i in range(len(pts) - 1):
        draw.line((pts[i], pts[i + 1]), fill=0, width=3)
    for px, py in pts:
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=0)

    # Per-hour temperature + precip % labels
    f_val = load_font(12, bold=True)
    f_precip = load_font(11)
    for i, (px, py) in enumerate(pts):
        t_label = f"{round(temps[i])}\u00B0"
        tw = text_w(draw, t_label, f_val)
        draw.text((px - tw / 2, py - 18), t_label, fill=0, font=f_val)
        p = probs[i]
        if p and p >= 1:
            p_label = f"{int(p)}%"
            pw = text_w(draw, p_label, f_precip)
            bh = (p / 100.0) * bar_band_h
            draw.text((px - pw / 2, plot_y1 - bh - 13),
                      p_label, fill=0, font=f_precip)

    # Hour labels along the bottom (12h am/pm) with collision avoidance
    f_hr = load_font(13)

    def fmt_hour(hh24):
        h_ = hh24 % 12 or 12
        return f"{h_}{'a' if hh24 < 12 else 'p'}"

    def lbl(i):
        s = fmt_hour(int(times[i][11:13]))
        return s, text_w(draw, s, f_hr)

    n_labels = len(times)
    min_gap = 6
    last_text, last_w = lbl(n_labels - 1)
    last_left = (plot_x0 + (n_labels - 1) * step) - last_w / 2

    chosen = []
    last_right_drawn = -1e9
    for i in range(n_labels - 1):
        text, lw = lbl(i)
        cx = plot_x0 + i * step
        left = cx - lw / 2
        right = left + lw
        if i == 0:
            chosen.append((left, text))
            last_right_drawn = right
        elif left > last_right_drawn + min_gap and right + min_gap < last_left:
            chosen.append((left, text))
            last_right_drawn = right
    chosen.append((last_left, last_text))

    for left, text in chosen:
        draw.text((left, plot_y1 + 4), text, fill=0, font=f_hr)


# ---------- portrait: 600x800 ---------------------------------------------
def render_portrait(data):
    c, h, d = data["current"], data["hourly"], data["daily"]
    W, H = 600, 800
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)

    # City tiny top-left, time top-right
    draw.text((6, 4), LABEL, fill=0, font=load_font(20))
    ts = time_now_str()
    f_time = load_font(36, bold=True)
    tw = text_w(draw, ts, f_time)
    draw.text((W - tw - 8, 2), ts, fill=0, font=f_time)

    # --- Current conditions block ---
    draw_icon(draw, c["weather_code"], W / 2 - 200, 155, 55)
    draw_text_centered(draw, W / 2 + 30, 60,
                       f"{round(c['temperature_2m'])}\u00B0",
                       load_font(170, bold=True))
    draw_text_centered(draw, W / 2, 225,
                       WMO.get(c["weather_code"], f"Code {c['weather_code']}"),
                       load_font(32))
    draw_text_centered(
        draw, W / 2, 275,
        f"Feels {round(c['apparent_temperature'])}\u00B0   "
        f"Hum {c['relative_humidity_2m']}%",
        load_font(26),
    )
    uv = c.get("uv_index", 0) or 0
    draw_text_centered(draw, W / 2, 315,
                       f"UV {uv:.0f}",
                       load_font(38, bold=True))

    # --- Hourly chart ---
    start = current_hour_index(h["time"])
    draw_hourly_chart(draw, 20, 370, W - 40, 175, h, start, HOURLY_HOURS)

    # Divider between today (chart is same day) and 2-day forecast
    draw.rectangle((40, 560, W - 40, 562), fill=0)

    # --- 3-day forecast ---
    col_w = W / 3
    for i in range(3):
        cx = col_w * i + col_w / 2
        draw_text_centered(draw, cx, 580, day_name(d["time"][i], i),
                           load_font(28, bold=True))
        draw_icon(draw, d["weather_code"][i], cx, 660, 36)
        draw_text_centered(draw, cx, 712,
                           f"{round(d['temperature_2m_max'][i])}\u00B0",
                           load_font(32, bold=True))
        draw_text_centered(draw, cx, 755,
                           f"{round(d['temperature_2m_min'][i])}\u00B0",
                           load_font(24))
        prob = d["precipitation_probability_max"][i] or 0
        draw_text_centered(draw, cx, 785, f"{prob}% precip", load_font(16))

    return img


# ---------- landscape: 800x600 --------------------------------------------
def render_landscape(data):
    c, h, d = data["current"], data["hourly"], data["daily"]
    W, H = 800, 600
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)

    # City tiny top-left, time top-right
    draw.text((6, 4), LABEL, fill=0, font=load_font(20))
    ts = time_now_str()
    f_time = load_font(36, bold=True)
    tw = text_w(draw, ts, f_time)
    draw.text((W - tw - 8, 2), ts, fill=0, font=f_time)

    # --- LEFT: current conditions ---
    lx = 155
    draw_icon(draw, c["weather_code"], lx, 100, 45)
    draw_text_centered(draw, lx, 155,
                       f"{round(c['temperature_2m'])}\u00B0",
                       load_font(140, bold=True))
    draw_text_centered(draw, lx, 320,
                       WMO.get(c["weather_code"], f"Code {c['weather_code']}"),
                       load_font(26))
    draw_text_centered(
        draw, lx, 365,
        f"Feels {round(c['apparent_temperature'])}\u00B0   "
        f"Hum {c['relative_humidity_2m']}%",
        load_font(22),
    )
    uv = c.get("uv_index", 0) or 0
    draw_text_centered(draw, lx, 410,
                       f"UV {uv:.0f}",
                       load_font(34, bold=True))

    # Divider between left/middle
    draw.rectangle((310, 55, 312, H - 30), fill=0)

    # --- MIDDLE: hourly chart ---
    start = current_hour_index(h["time"])
    draw_hourly_chart(draw, 320, 55, 300, H - 90, h, start, HOURLY_HOURS)

    # Divider middle/right
    draw.rectangle((630, 55, 632, H - 30), fill=0)

    # --- RIGHT: 3-day forecast ---
    rx = 640
    rw = W - rx - 5
    row_h = (H - 90) / 3
    for i in range(3):
        cy = 55 + row_h * i + row_h / 2
        draw.text((rx + 5, cy - 55), day_name(d["time"][i], i),
                  fill=0, font=load_font(24, bold=True))
        draw_icon(draw, d["weather_code"][i], rx + rw - 25, cy - 25, 20)
        draw.text((rx + 5, cy - 25),
                  f"{round(d['temperature_2m_max'][i])}\u00B0/"
                  f"{round(d['temperature_2m_min'][i])}\u00B0",
                  fill=0, font=load_font(26, bold=True))
        prob = d["precipitation_probability_max"][i] or 0
        draw.text((rx + 5, cy + 15), f"{prob}% precip",
                  fill=0, font=load_font(16))

    return img


def rotate_into_panel(landscape_img):
    if LANDSCAPE_ROTATION == "cw":
        return landscape_img.rotate(-90, expand=True)
    return landscape_img.rotate(90, expand=True)


def render(orientation):
    data = fetch_weather()
    if orientation == "landscape":
        return rotate_into_panel(render_landscape(data))
    if orientation == "landscape-preview":
        return render_landscape(data)
    return render_portrait(data)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/weather.png":
            self.send_response(404)
            self.end_headers()
            return
        q = urllib.parse.parse_qs(parsed.query)
        orient = (q.get("o", [DEFAULT_ORIENTATION])[0]).lower()
        try:
            img = render(orient)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            print("error:", e)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"NookFrame weather server: http://0.0.0.0:{PORT}/weather.png")
    print("  ?o=portrait | ?o=landscape | ?o=landscape-preview")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
