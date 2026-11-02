# Water Tank Monitoring Dashboard (Frontend)

## Overview
This folder contains the web-based real-time dashboard for the IoT Water Tank Monitoring System.

## Architecture
- **Tech Stack:** HTML5, CSS3, JavaScript (Vanilla ES6+), and Chart.js.
- **Data Source:** Connects directly to the FastAPI cloud backend (REST API: `/api/readings/latest` and `/api/readings/history`).
- **Features Planned:**
  - Real-time animated water level visual indicator.
  - Probe contact status pills (25%, 50%, 75%, 100%).
  - Water level history chart using Chart.js.
  - Tank empty / tank overflow warning badges.
  - Responsive design for mobile and desktop screens.
