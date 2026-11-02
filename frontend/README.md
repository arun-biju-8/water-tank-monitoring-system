# Water Tank Monitoring Dashboard (Frontend)

## Overview
A modern, responsive, real-time cloud-based web dashboard for the ESP32 IoT Smart Water Tank Monitoring System.

## Live Cloud Integration
- **Target Backend:** `https://tankpulse-2sq4.onrender.com`
- **Latest Reading Endpoint:** `GET /api/readings/latest`
- **Historical Telemetry Endpoint:** `GET /api/readings/history?limit=30`
- **System Health Probe:** `GET /health`
- **Polling Interval:** Automatically refreshes live telemetry every 5 seconds with a visual countdown and manual force-refresh button.

## Key Features
1. **Prominent Water Level Display**: High-impact digital percentage display (0%, 25%, 50%, 75%, 100%) with dynamic status badges (Empty, Low, Medium, Normal, Full).
2. **Animated Liquid Tank Visualizer**: Smooth HTML5 Canvas wave animation with physics-based interpolation, height scale ticks, and probe contact markers.
3. **Discrete Probe Sensor Status**: Individual monitoring cards for all 4 contact probes (25% GPIO 5, 50% GPIO 4, 75% GPIO 16, 100% GPIO 17) strictly adhering to **Filled** / **Empty** terminology.
4. **Hardware Buzzer & Alarm Indicator**: Real-time display of alarm conditions (triggered at 0% and 100%) and hardware buzzer mute state.
5. **Firmware LED Bar Simulation**: Visual representation of the ESP32 hardware LEDs (GPIOs 13, 22, 21, 19, 18), including synchronized blinking during 100% full alert conditions.
6. **Indian Standard Time (IST) Displays**: All timestamps formatted in `Asia/Kolkata` (UTC+05:30) with dynamic relative time indicators ("Just now", "12s ago").
7. **Interactive Trend Chart**: Real-time historical line chart rendered via Chart.js with gradient fill, custom tooltips, and fixed 0–100% Y-axis.
8. **Historical Log Table**: Paginated telemetry table showing record IDs, IST timestamps, percentage, probe states, and alarm flags.
9. **Responsive Design**: Mobile-first CSS grid and flexbox layout optimized for desktop monitors, tablets, and smartphones.
10. **Zero External Build Tooling**: Vanilla HTML5, CSS3, and ES6+ JavaScript. Chart.js is bundled locally with automatic CDN fallback.

## Running the Dashboard
Simply open `index.html` in any modern web browser:
```bash
# Option 1: Direct file launch
start frontend/index.html

# Option 2: Using Python local HTTP server
python -m http.server 3000 --directory frontend
# Open http://localhost:3000 in your browser
```
