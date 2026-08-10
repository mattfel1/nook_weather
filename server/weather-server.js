// NookFrame weather server — v3: portrait or landscape, toggleable
// -----------------------------------------------------------------
// The Nook panel is physically 600x800 portrait. For landscape we design
// on an 800x600 canvas and rotate it 90deg into the 600x800 output, so the
// device just shows it sideways. Hang the Nook rotated on the wall and done.
//
// Toggle:
//   DEFAULT_ORIENTATION below ('portrait' | 'landscape')  <- what the Nook gets
//   URL override for comparing in your browser:
//     http://localhost:8080/weather.png?o=portrait
//     http://localhost:8080/weather.png?o=landscape
//
// Setup: npm install express canvas ; node weather-server.js

const express = require('express');
const { createCanvas } = require('canvas');

const app = express();
const PORT = 8080;

const DEFAULT_ORIENTATION = 'landscape';   // <-- flip to 'landscape' when you decide

// Rotation direction for landscape (which way you'll hang the device):
//  'cw'  = top of the layout ends up on the LEFT edge of the portrait panel
//  'ccw' = top of the layout ends up on the RIGHT edge
const LANDSCAPE_ROTATION = 'cw';

// Ottawa
const LAT = 45.3624;
const LON = -75.7217;
const LABEL = 'Ottawa';

const PANEL_W = 600, PANEL_H = 800;       // physical panel (portrait)

const WMO = {
  0: 'Clear', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Rime fog',
  51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
  56: 'Frz drizzle', 57: 'Frz drizzle',
  61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
  66: 'Freezing rain', 67: 'Freezing rain',
  71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains',
  80: 'Showers', 81: 'Showers', 82: 'Heavy showers',
  85: 'Snow showers', 86: 'Snow showers',
  95: 'Thunderstorm', 96: 'T-storm + hail', 99: 'T-storm + hail'
};

function drawIcon(ctx, code, cx, cy, r) {
  ctx.save();
  ctx.strokeStyle = '#000';
  ctx.fillStyle = '#000';
  ctx.lineWidth = 3;
  if (code === 0 || code === 1) {
    ctx.beginPath(); ctx.arc(cx, cy, r * 0.5, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r * 0.65, cy + Math.sin(a) * r * 0.65);
      ctx.lineTo(cx + Math.cos(a) * r * 0.9, cy + Math.sin(a) * r * 0.9);
      ctx.stroke();
    }
  } else if (code >= 71 && code <= 86) {
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(a) * r * 0.8, cy + Math.sin(a) * r * 0.8);
      ctx.stroke();
    }
  } else if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code >= 95) {
    cloud(ctx, cx, cy - r * 0.2, r * 0.7);
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      ctx.moveTo(cx + i * r * 0.35, cy + r * 0.35);
      ctx.lineTo(cx + i * r * 0.35 - r * 0.12, cy + r * 0.7);
      ctx.stroke();
    }
  } else {
    cloud(ctx, cx, cy, r * 0.8);
  }
  ctx.restore();
}

function cloud(ctx, cx, cy, r) {
  ctx.beginPath();
  ctx.arc(cx - r * 0.5, cy, r * 0.45, Math.PI * 0.5, Math.PI * 1.5);
  ctx.arc(cx - r * 0.1, cy - r * 0.35, r * 0.45, Math.PI, Math.PI * 1.9);
  ctx.arc(cx + r * 0.45, cy - r * 0.1, r * 0.4, Math.PI * 1.2, Math.PI * 0.5);
  ctx.closePath();
  ctx.stroke();
}

async function getWeather() {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}`
    + `&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m`
    + `&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max`
    + `&forecast_days=4&timezone=auto`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('open-meteo ' + r.status);
  return r.json();
}

function dayName(dateStr, idx) {
  if (idx === 0) return 'Today';
  if (idx === 1) return 'Tmrw';
  return new Date(dateStr + 'T12:00:00').toLocaleDateString('en-CA', { weekday: 'short' });
}

// ---------- portrait layout: 600x800, current on top, 3-day strip below ----
function renderPortrait(data) {
  const c = data.current, d = data.daily;
  const W = 600, H = 800;
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#000'; ctx.textAlign = 'center';

  ctx.font = 'bold 44px sans-serif';
  ctx.fillText(LABEL, W / 2, 70);

  drawIcon(ctx, c.weather_code, W / 2 - 170, 180, 60);

  ctx.font = 'bold 150px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(Math.round(c.temperature_2m) + '\u00B0', W / 2 - 70, 230);

  ctx.textAlign = 'center';
  ctx.font = '38px sans-serif';
  ctx.fillText(WMO[c.weather_code] || ('Code ' + c.weather_code), W / 2, 300);

  ctx.font = '28px sans-serif';
  ctx.fillText(
    'Feels ' + Math.round(c.apparent_temperature) + '\u00B0   ' +
    'Hum ' + c.relative_humidity_2m + '%   ' +
    'Wind ' + Math.round(c.wind_speed_10m) + ' km/h',
    W / 2, 350);

  ctx.fillRect(40, 390, W - 80, 3);

  const colW = W / 3;
  for (let i = 0; i < 3; i++) {
    const cx = colW * i + colW / 2;
    ctx.font = 'bold 32px sans-serif';
    ctx.fillText(dayName(d.time[i], i), cx, 450);
    drawIcon(ctx, d.weather_code[i], cx, 530, 42);
    ctx.font = 'bold 36px sans-serif';
    ctx.fillText(Math.round(d.temperature_2m_max[i]) + '\u00B0', cx, 630);
    ctx.font = '30px sans-serif';
    ctx.fillText(Math.round(d.temperature_2m_min[i]) + '\u00B0', cx, 670);
    ctx.font = '24px sans-serif';
    ctx.fillText((d.precipitation_probability_max[i] ?? 0) + '% precip', cx, 710);
  }

  ctx.font = '20px sans-serif';
  ctx.fillText('Updated ' + new Date().toLocaleString('en-CA'), W / 2, 775);

  return canvas;
}

// ---------- landscape layout: 800x600, current on left, 3-day on right ----
function renderLandscape(data) {
  const c = data.current, d = data.daily;
  const W = 800, H = 600;
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#000'; ctx.textAlign = 'center';

  // Left panel: current conditions (0..420 wide)
  const LX = 210; // center of left panel
  ctx.font = 'bold 40px sans-serif';
  ctx.fillText(LABEL, LX, 70);

  drawIcon(ctx, c.weather_code, LX, 170, 65);

  ctx.font = 'bold 130px sans-serif';
  ctx.fillText(Math.round(c.temperature_2m) + '\u00B0', LX, 360);

  ctx.font = '34px sans-serif';
  ctx.fillText(WMO[c.weather_code] || ('Code ' + c.weather_code), LX, 420);

  ctx.font = '26px sans-serif';
  ctx.fillText('Feels ' + Math.round(c.apparent_temperature) + '\u00B0   Hum ' + c.relative_humidity_2m + '%', LX, 470);
  ctx.fillText('Wind ' + Math.round(c.wind_speed_10m) + ' km/h', LX, 510);

  // vertical divider
  ctx.fillRect(420, 40, 3, H - 80);

  // Right panel: 3 stacked day rows (430..800)
  const RX = 430;
  const rowH = (H - 80) / 3;
  for (let i = 0; i < 3; i++) {
    const cy = 60 + rowH * i + rowH / 2;

    ctx.textAlign = 'left';
    ctx.font = 'bold 30px sans-serif';
    ctx.fillText(dayName(d.time[i], i), RX + 20, cy - 25);

    drawIcon(ctx, d.weather_code[i], RX + 60, cy + 25, 32);

    ctx.font = 'bold 32px sans-serif';
    ctx.fillText(Math.round(d.temperature_2m_max[i]) + '\u00B0 / ' + Math.round(d.temperature_2m_min[i]) + '\u00B0', RX + 130, cy + 15);

    ctx.font = '22px sans-serif';
    ctx.fillText((d.precipitation_probability_max[i] ?? 0) + '% precip', RX + 130, cy + 50);
  }

  ctx.textAlign = 'center';
  ctx.font = '18px sans-serif';
  ctx.fillText('Updated ' + new Date().toLocaleString('en-CA'), W / 2, H - 15);

  return canvas;
}

// Rotate an 800x600 landscape canvas into the 600x800 portrait panel.
function rotateIntoPanel(landscapeCanvas) {
  const out = createCanvas(PANEL_W, PANEL_H);
  const ctx = out.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, PANEL_W, PANEL_H);
  if (LANDSCAPE_ROTATION === 'cw') {
    ctx.translate(PANEL_W, 0);
    ctx.rotate(Math.PI / 2);
  } else {
    ctx.translate(0, PANEL_H);
    ctx.rotate(-Math.PI / 2);
  }
  ctx.drawImage(landscapeCanvas, 0, 0);
  return out;
}

app.get('/weather.png', async (req, res) => {
  try {
    const data = await getWeather();
    const o = (req.query.o || DEFAULT_ORIENTATION).toLowerCase();

    let canvas;
    if (o === 'landscape') {
      canvas = rotateIntoPanel(renderLandscape(data));
    } else if (o === 'landscape-preview') {
      // un-rotated, for comfortable viewing in your PC browser
      canvas = renderLandscape(data);
    } else {
      canvas = renderPortrait(data);
    }

    res.set('Content-Type', 'image/png');
    res.set('Cache-Control', 'no-store');
    res.send(canvas.toBuffer('image/png'));
  } catch (e) {
    console.error(e);
    res.status(500).send('error: ' + e.message);
  }
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`NookFrame weather server v3: http://0.0.0.0:${PORT}/weather.png`);
  console.log('  ?o=portrait | ?o=landscape | ?o=landscape-preview');
});
