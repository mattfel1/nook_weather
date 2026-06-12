#!/usr/bin/env python3
"""
NookFrame weather server (Python edition)
-----------------------------------------

Serves a 600x800 weather PNG over plain HTTP for the Nook Simple Touch.
Uses only Pillow (which ships preinstalled on Raspberry Pi OS) and the
Python stdlib. No npm, no canvas, no compile.

Run:
    python3 weather-server.py

Then point WeatherActivity.IMAGE_URL at:
    http://<this-pi-ip>:8080/weather.png

Toggle layouts in the browser:
    http://<pi>:8080/weather.png?o=portrait
    http://<pi>:8080/weather.png?o=landscape
    http://<pi>:8080/weather.png?o=landscape-preview   (un-rotated, for PC viewing)

Change DEFAULT_ORIENTATION below to pick what the Nook gets by default.
"""

import io
import json
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

PANEL_W, PANEL_H = 600, 800             # physical Nook panel

# WMO weather code -> short label
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

# Try to find a decent TrueType font. Pi OS ships DejaVu by default.
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
    # Last resort: built-in bitmap font (small, but won't crash)
    return ImageFont.load_default()


def text_w(draw, text, font):
    """Width of text in pixels. Pillow has changed this API a few times."""
    if hasattr(draw, "textbbox"):
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l
    return draw.textsize(text, font=font)[0]


def draw_text_centered(draw, x, y, text, font):
    draw.text((x - text_w(draw, text, font) / 2, y), text, fill=0, font=font)


def draw_icon(draw, code, cx, cy, r):
    """Hand-drawn monochrome weather icons. Crisp on e-ink at any size."""
    width = 3
    if code in (0, 1):
        # sun: circle + rays
        draw.ellipse((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5),
                     outline=0, width=width)
        import math
        for i in range(8):
            a = (i / 8) * math.pi * 2
            x1, y1 = cx + math.cos(a) * r * 0.65, cy + math.sin(a) * r * 0.65
            x2, y2 = cx + math.cos(a) * r * 0.9,  cy + math.sin(a) * r * 0.9
            draw.line((x1, y1, x2, y2), fill=0, width=width)
    elif 71 <= code <= 86:
        # snow: 6-point asterisk
        import math
        for i in range(6):
            a = (i / 6) * math.pi * 2
            x2, y2 = cx + math.cos(a) * r * 0.8, cy + math.sin(a) * r * 0.8
            draw.line((cx, cy, x2, y2), fill=0, width=width)
    elif (51 <= code <= 67) or (80 <= code <= 82) or code >= 95:
        # cloud + rain
        _cloud(draw, cx, cy - r * 0.2, r * 0.7, width)
        for i in (-1, 0, 1):
            x1 = cx + i * r * 0.35
            draw.line((x1, cy + r * 0.35, x1 - r * 0.12, cy + r * 0.7),
                      fill=0, width=width)
    else:
        # plain cloud
        _cloud(draw, cx, cy, r * 0.8, width)


def _cloud(draw, cx, cy, r, width):
    # Three overlapping arcs sketch a cloud silhouette.
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
        "wind_speed_10m,relative_humidity_2m"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
        "precipitation_probability_max"
        "&forecast_days=4&timezone=auto"
    )
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def day_name(date_str, idx):
    if idx == 0:
        return "Today"
    if idx == 1:
        return "Tmrw"
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")


# ---------- portrait: 600x800, current on top, 3-day strip below ----------
def render_portrait(data):
    c, d = data["current"], data["daily"]
    W, H = 600, 800
    img = Image.new("L", (W, H), 255)   # 8-bit grayscale, white bg
    draw = ImageDraw.Draw(img)

    draw_text_centered(draw, W / 2, 30, LABEL, load_font(44, bold=True))

    draw_icon(draw, c["weather_code"], W / 2 - 170, 180, 60)
    draw_text_centered(draw, W / 2 + 30, 110,
                       f"{round(c['temperature_2m'])}\u00B0",
                       load_font(150, bold=True))
    draw_text_centered(draw, W / 2, 270,
                       WMO.get(c["weather_code"], f"Code {c['weather_code']}"),
                       load_font(38))
    draw_text_centered(
        draw, W / 2, 330,
        f"Feels {round(c['apparent_temperature'])}\u00B0   "
        f"Hum {c['relative_humidity_2m']}%   "
        f"Wind {round(c['wind_speed_10m'])} km/h",
        load_font(28),
    )

    draw.rectangle((40, 390, W - 40, 393), fill=0)

    col_w = W / 3
    for i in range(3):
        cx = col_w * i + col_w / 2
        draw_text_centered(draw, cx, 420, day_name(d["time"][i], i),
                           load_font(32, bold=True))
        draw_icon(draw, d["weather_code"][i], cx, 530, 42)
        draw_text_centered(draw, cx, 600,
                           f"{round(d['temperature_2m_max'][i])}\u00B0",
                           load_font(36, bold=True))
        draw_text_centered(draw, cx, 645,
                           f"{round(d['temperature_2m_min'][i])}\u00B0",
                           load_font(30))
        prob = d["precipitation_probability_max"][i] or 0
        draw_text_centered(draw, cx, 695, f"{prob}% precip", load_font(24))

    draw_text_centered(
        draw, W / 2, 760,
        f"Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        load_font(20),
    )
    return img


# ---------- landscape: 800x600, current left, 3-day stack right -----------
def render_landscape(data):
    c, d = data["current"], data["daily"]
    W, H = 800, 600
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)

    lx = 210
    draw_text_centered(draw, lx, 30, LABEL, load_font(40, bold=True))
    draw_icon(draw, c["weather_code"], lx, 170, 65)
    draw_text_centered(draw, lx, 260,
                       f"{round(c['temperature_2m'])}\u00B0",
                       load_font(130, bold=True))
    draw_text_centered(draw, lx, 400,
                       WMO.get(c["weather_code"], f"Code {c['weather_code']}"),
                       load_font(34))
    draw_text_centered(
        draw, lx, 450,
        f"Feels {round(c['apparent_temperature'])}\u00B0   "
        f"Hum {c['relative_humidity_2m']}%",
        load_font(26),
    )
    draw_text_centered(draw, lx, 490,
                       f"Wind {round(c['wind_speed_10m'])} km/h",
                       load_font(26))

    draw.rectangle((420, 40, 423, H - 40), fill=0)

    rx = 430
    row_h = (H - 80) / 3
    for i in range(3):
        cy = 60 + row_h * i + row_h / 2
        draw.text((rx + 20, cy - 50), day_name(d["time"][i], i),
                  fill=0, font=load_font(30, bold=True))
        draw_icon(draw, d["weather_code"][i], rx + 60, cy + 25, 32)
        draw.text((rx + 130, cy - 15),
                  f"{round(d['temperature_2m_max'][i])}\u00B0 / "
                  f"{round(d['temperature_2m_min'][i])}\u00B0",
                  fill=0, font=load_font(32, bold=True))
        prob = d["precipitation_probability_max"][i] or 0
        draw.text((rx + 130, cy + 25), f"{prob}% precip",
                  fill=0, font=load_font(22))

    draw_text_centered(
        draw, W / 2, H - 30,
        f"Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        load_font(18),
    )
    return img


def rotate_into_panel(landscape_img):
    """Rotate the 800x600 landscape image into the 600x800 panel."""
    if LANDSCAPE_ROTATION == "cw":
        return landscape_img.rotate(-90, expand=True)   # PIL is counter-clockwise
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
        # Quieter default log
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
