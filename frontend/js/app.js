/**
 * TankPulse IoT - Smart Water Tank Cloud Monitoring Dashboard
 * Client Application integrating with FastAPI + PostgreSQL on Render.
 * 
 * Features:
 * - Real-time animated liquid water tank visualizer
 * - Prominent bidirectional remote buzzer silence control (GPIO 23)
 * - REALTIME LEVEL activity timeline modal with human-readable consumer events
 * - Indian Standard Time (IST, UTC+05:30) serialization
 * - Historical trends via Chart.js
 * 
 * Target Backend: https://tankpulse-2sq4.onrender.com
 */

(function () {
  "use strict";

  // ============================================================================
  // 1. Cloud API Configuration & Endpoints
  // ============================================================================
  const CLOUD_API_BASE = "https://tankpulse-2sq4.onrender.com";

  // Use the cloud base URL unless running from the same origin on Render
  const API_BASE = window.location.origin.includes("onrender.com")
    ? window.location.origin
    : CLOUD_API_BASE;

  const ENDPOINTS = {
    latest: `${API_BASE}/api/readings/latest`,
    history: `${API_BASE}/api/readings/history?limit=30`,
    health: `${API_BASE}/health`,
    muteCommand: `${API_BASE}/api/commands/mute`,
    commandStatus: (id) => `${API_BASE}/api/commands/status/${id}`,
    commandHistory: `${API_BASE}/api/commands/history?limit=20`,
  };

  const REFRESH_INTERVAL_MS = 5000; // Auto-refresh telemetry every 5 seconds
  const STORAGE_KEY_TOKEN = "tankpulse_operator_token";

  // ============================================================================
  // 2. Application State
  // ============================================================================
  const state = {
    latestReading: null,
    previousReading: null,
    history: [],
    commandHistory: [],
    activeFilter: "all",
    isConnected: false,
    lastSuccessfulFetch: null,
    fetchInFlight: false,
    countdownSeconds: 5,
    consecutiveErrors: 0,
    visualLevel: 0, // Animated interpolation value for the canvas tank
    commandInFlight: false,
    pendingCommandId: null,
    operatorToken: localStorage.getItem(STORAGE_KEY_TOKEN) || "",
  };

  // ============================================================================
  // 3. DOM Elements Cache
  // ============================================================================
  const el = {
    // Header & Navigation
    btnOpenTimeline: document.getElementById("btnOpenTimeline"),
    connectionPill: document.getElementById("connectionPill"),
    connectionText: document.getElementById("connectionText"),
    btnManualRefresh: document.getElementById("btnManualRefresh"),
    refreshCircle: document.getElementById("refreshCircle"),
    countdownText: document.getElementById("countdownText"),
    btnOpenSettings: document.getElementById("btnOpenSettings"),

    // Global Alert Banner
    alertBanner: document.getElementById("alertBanner"),
    alertHeading: document.getElementById("alertHeading"),
    alertDetail: document.getElementById("alertDetail"),
    alertIcon: document.getElementById("alertIcon"),
    alertDismiss: document.getElementById("alertDismiss"),

    // PART 1: Prominent Alarm Control Bar
    alarmStatusContainer: document.querySelector(".alarm-status-container"),
    alarmHeroIndicator: document.getElementById("alarmHeroIndicator"),
    alarmHeroStateText: document.getElementById("alarmHeroStateText"),
    muteHeroSubbadge: document.getElementById("muteHeroSubbadge"),
    alarmHeroDetailText: document.getElementById("alarmHeroDetailText"),
    btnSilenceAlarm: document.getElementById("btnSilenceAlarm"),
    btnSilenceText: document.getElementById("btnSilenceText"),
    btnSilenceSpinner: document.querySelector(".btn-silence-spinner"),
    commandFeedbackText: document.getElementById("commandFeedbackText"),

    // Card 1: Tank & Level Visualizer
    levelConditionBadge: document.getElementById("levelConditionBadge"),
    trendBadge: document.getElementById("trendBadge"),
    tankCanvas: document.getElementById("tankCanvas"),
    heroPercentage: document.getElementById("heroPercentage"),
    heroStatusText: document.getElementById("heroStatusText"),
    timestampIST: document.getElementById("timestampIST"),
    relativeTime: document.getElementById("relativeTime"),
    readingId: document.getElementById("readingId"),
    hardwareLinkStatus: document.getElementById("hardwareLinkStatus"),

    // Card 2: Probes
    probeCard25: document.getElementById("probeCard25"),
    probeCard50: document.getElementById("probeCard50"),
    probeCard75: document.getElementById("probeCard75"),
    probeCard100: document.getElementById("probeCard100"),
    probeState25: document.getElementById("probeState25"),
    probeState50: document.getElementById("probeState50"),
    probeState75: document.getElementById("probeState75"),
    probeState100: document.getElementById("probeState100"),

    // Card 3: Hardware System Status
    muteStatusBadge: document.getElementById("muteStatusBadge"),
    muteIconBox: document.getElementById("muteIconBox"),
    buzzerPhysicalStateDesc: document.getElementById("buzzerPhysicalStateDesc"),
    channelStatusBadge: document.getElementById("channelStatusBadge"),
    led1: document.getElementById("led1"),
    led2: document.getElementById("led2"),
    led3: document.getElementById("led3"),
    led4: document.getElementById("led4"),
    led5: document.getElementById("led5"),

    // Card 4: Historical Chart
    historyChart: document.getElementById("historyChart"),
    chartLoadingOverlay: document.getElementById("chartLoadingOverlay"),

    // Card 5: Telemetry Table
    recordsCountBadge: document.getElementById("recordsCountBadge"),
    telemetryTableBody: document.getElementById("telemetryTableBody"),

    // PART 3: Modals
    timelineModal: document.getElementById("timelineModal"),
    btnCloseTimeline: document.getElementById("btnCloseTimeline"),
    btnCloseTimelineFooter: document.getElementById("btnCloseTimelineFooter"),
    timelineList: document.getElementById("timelineList"),
    filterTabs: document.querySelectorAll(".filter-tab"),

    // Settings Modal
    settingsModal: document.getElementById("settingsModal"),
    btnCloseSettings: document.getElementById("btnCloseSettings"),
    inputOperatorToken: document.getElementById("inputOperatorToken"),
    btnSaveToken: document.getElementById("btnSaveToken"),
    btnClearToken: document.getElementById("btnClearToken"),
  };

  let chartInstance = null;
  let refreshTimer = null;
  let countdownTimer = null;
  let waveOffset = 0;

  // ============================================================================
  // 4. Timezone & Formatting Utilities (Asia/Kolkata - IST)
  // ============================================================================

  /**
   * Formats an ISO 8601 string or Date into Indian Standard Time (IST, UTC+05:30).
   * Example: "02 Nov 2026, 09:12:27 PM IST"
   */
  function formatIST(isoDateString) {
    if (!isoDateString) return "--:--:-- IST";
    try {
      const date = new Date(isoDateString);
      if (isNaN(date.getTime())) return "--:--:-- IST";

      const options = {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      };

      return `${new Intl.DateTimeFormat("en-IN", options).format(date)} IST`;
    } catch (e) {
      return isoDateString;
    }
  }

  /**
   * Formats a short time string in IST for chart ticks and timeline items.
   * Example: "09:12 PM" or "09:12:27 PM"
   */
  function formatISTShort(isoDateString, includeSeconds = true) {
    if (!isoDateString) return "--:--:--";
    try {
      const date = new Date(isoDateString);
      if (isNaN(date.getTime())) return "--:--:--";

      return new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: includeSeconds ? "2-digit" : undefined,
        hour12: true,
      }).format(date);
    } catch (e) {
      return isoDateString;
    }
  }

  /**
   * Calculates human-friendly relative time string.
   */
  function formatRelativeTime(isoDateString) {
    if (!isoDateString) return "--";
    const date = new Date(isoDateString);
    if (isNaN(date.getTime())) return "--";

    const elapsedSeconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (elapsedSeconds < 5) return "Just now";
    if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;
    const minutes = Math.floor(elapsedSeconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  }

  /**
   * Resolves friendly condition label and CSS badge class based on level percentage.
   */
  function getLevelCondition(level) {
    if (level === 0) return { label: "Empty", badgeClass: "badge-empty", desc: "Tank is completely empty (0%)" };
    if (level === 25) return { label: "Low", badgeClass: "badge-low", desc: "Water at minimum 25% reserve" };
    if (level === 50) return { label: "Medium", badgeClass: "badge-medium", desc: "Water at half capacity (50%)" };
    if (level === 75) return { label: "Normal", badgeClass: "badge-normal", desc: "Optimal water capacity (75%)" };
    if (level === 100) return { label: "Full", badgeClass: "badge-full", desc: "Tank is 100% full (Overfill Warning)" };
    return { label: `${level}%`, badgeClass: "badge-medium", desc: `Water at ${level}% capacity` };
  }

  // ============================================================================
  // 5. Canvas Liquid Water Tank Animation
  // ============================================================================
  function initTankCanvas() {
    const canvas = el.tankCanvas;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    function renderFrame() {
      const targetLevel = state.latestReading ? state.latestReading.water_level : 0;
      state.visualLevel += (targetLevel - state.visualLevel) * 0.08;
      waveOffset += 0.05;

      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      // Tank Geometry
      const padX = 26;
      const padY = 22;
      const tankW = width - padX * 2;
      const tankH = height - padY * 2;
      const cornerR = 20;

      // Outer Tank Container
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(padX, padY, tankW, tankH, cornerR);
      ctx.fillStyle = "rgba(15, 23, 42, 0.78)";
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#334155";
      ctx.stroke();
      ctx.clip(); // Clip contents strictly inside tank

      // Water Level Dimensions
      const fillHeight = (Math.max(0, Math.min(100, state.visualLevel)) / 100) * tankH;
      const waterY = padY + tankH - fillHeight;

      if (fillHeight > 1) {
        // Draw Animated Liquid with Surface Sine Waves
        ctx.beginPath();
        ctx.moveTo(padX, padY + tankH);

        const waveAmp = fillHeight < 5 || fillHeight > tankH - 5 ? 0.8 : 3.5;
        const waveFreq = (Math.PI * 2.5) / tankW;

        for (let x = 0; x <= tankW; x += 4) {
          const wave = Math.sin(x * waveFreq + waveOffset) * waveAmp;
          ctx.lineTo(padX + x, waterY + wave);
        }

        ctx.lineTo(padX + tankW, padY + tankH);
        ctx.closePath();

        // Water Gradient Fill
        const waterGrad = ctx.createLinearGradient(0, waterY, 0, padY + tankH);
        if (targetLevel === 0) {
          waterGrad.addColorStop(0, "rgba(244, 63, 94, 0.65)");
          waterGrad.addColorStop(1, "rgba(225, 29, 72, 0.85)");
        } else if (targetLevel === 100) {
          waterGrad.addColorStop(0, "#38bdf8");
          waterGrad.addColorStop(1, "#0284c7");
        } else {
          waterGrad.addColorStop(0, "#38bdf8");
          waterGrad.addColorStop(1, "#0369a1");
        }

        ctx.fillStyle = waterGrad;
        ctx.fill();

        // Wave crest highlight line
        ctx.beginPath();
        for (let x = 0; x <= tankW; x += 4) {
          const wave = Math.sin(x * waveFreq + waveOffset) * waveAmp;
          if (x === 0) ctx.moveTo(padX + x, waterY + wave);
          else ctx.lineTo(padX + x, waterY + wave);
        }
        ctx.strokeStyle = targetLevel === 0 ? "rgba(253, 164, 175, 0.6)" : "rgba(186, 230, 253, 0.7)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      ctx.restore();

      // Measurement Gauge Ticks and Probe Height Indicators
      const marks = [
        { pct: 100, probeKey: "probe_100", label: "100%" },
        { pct: 75, probeKey: "probe_75", label: "75%" },
        { pct: 50, probeKey: "probe_50", label: "50%" },
        { pct: 25, probeKey: "probe_25", label: "25%" },
      ];

      marks.forEach((mark) => {
        const markY = padY + tankH - (mark.pct / 100) * tankH;
        const isProbeFilled = state.latestReading ? Boolean(state.latestReading[mark.probeKey]) : false;

        // Horizontal Tick Line
        ctx.beginPath();
        ctx.moveTo(padX + tankW - 14, markY);
        ctx.lineTo(padX + tankW - 2, markY);
        ctx.lineWidth = 2;
        ctx.strokeStyle = isProbeFilled ? "#38bdf8" : "#475569";
        ctx.stroke();

        // Tick Label
        ctx.fillStyle = isProbeFilled ? "#7dd3fc" : "#64748b";
        ctx.font = "bold 9px 'JetBrains Mono', monospace";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        ctx.fillText(mark.label, padX + tankW - 18, markY);

        // Probe sensor contact node on left wall
        ctx.beginPath();
        ctx.arc(padX + 8, markY, isProbeFilled ? 4.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = isProbeFilled ? "#38bdf8" : "#334155";
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = isProbeFilled ? "#bae6fd" : "#475569";
        ctx.stroke();

        if (isProbeFilled) {
          ctx.beginPath();
          ctx.arc(padX + 8, markY, 7, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(56, 189, 248, 0.4)";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      // Bottom 0% Mark
      ctx.beginPath();
      ctx.moveTo(padX + tankW - 14, padY + tankH - 2);
      ctx.lineTo(padX + tankW - 2, padY + tankH - 2);
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#64748b";
      ctx.font = "bold 9px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText("0%", padX + tankW - 18, padY + tankH - 2);

      requestAnimationFrame(renderFrame);
    }

    requestAnimationFrame(renderFrame);
  }

  // ============================================================================
  // 6. PART 1: Prominent Silence Alarm Control Logic
  // ============================================================================

  /**
   * Updates the Prominent Silence Alarm Button states:
   * 1. Active & unmuted: Red, "SILENCE ALARM", enabled.
   * 2. Active & silenced: Amber, "ALARM SILENCED (BUZZER OFF)", disabled.
   * 3. Inactive: Slate, "ALARM INACTIVE", disabled.
   * 4. In-flight command: Cyan spinner, "COMMAND SENT / WAITING FOR ESP32...", disabled.
   */
  function updateAlarmControlUI() {
    if (!el.btnSilenceAlarm) return;

    // If a remote command is currently in flight waiting for ESP32 ack
    if (state.commandInFlight) {
      el.btnSilenceAlarm.className = "btn-silence-alarm btn-state-loading";
      el.btnSilenceAlarm.disabled = true;
      if (el.btnSilenceSpinner) el.btnSilenceSpinner.classList.remove("hidden");
      el.btnSilenceText.textContent = "COMMAND SENT — WAITING FOR ESP32...";
      el.alarmHeroStateText.textContent = "SILENCE COMMAND IN FLIGHT";
      el.alarmHeroDetailText.textContent = "Command sent to cloud. Polling ESP32 acknowledgment...";
      return;
    }

    if (el.btnSilenceSpinner) el.btnSilenceSpinner.classList.add("hidden");

    const reading = state.latestReading;
    if (!reading) {
      el.btnSilenceAlarm.className = "btn-silence-alarm btn-state-inactive";
      el.btnSilenceAlarm.disabled = true;
      el.btnSilenceText.textContent = "AWAITING TELEMETRY";
      return;
    }

    const isAlarmActive = Boolean(reading.alarm);
    const isMuted = Boolean(reading.muted);

    // State 1: Alarm is actively sounding on GPIO 23
    if (isAlarmActive && !isMuted) {
      el.alarmStatusContainer.className = "alarm-status-container container-alarm-active";
      el.alarmHeroIndicator.className = "alarm-indicator-bulb active";
      el.muteHeroSubbadge.classList.add("hidden");

      el.alarmHeroStateText.textContent = reading.water_level === 0 ? "CRITICAL: TANK EMPTY (0%)" : "ALERT: TANK FULL (100%)";
      el.alarmHeroDetailText.textContent = "Physical buzzer is actively sounding on GPIO 23! Click below to silence.";

      el.btnSilenceAlarm.className = "btn-silence-alarm btn-state-active";
      el.btnSilenceAlarm.disabled = false;
      el.btnSilenceText.textContent = "SILENCE ALARM";
    }
    // State 2: Alarm condition met, but physically silenced/muted
    else if (isAlarmActive && isMuted) {
      el.alarmStatusContainer.className = "alarm-status-container";
      el.alarmHeroIndicator.className = "alarm-indicator-bulb silenced";
      el.muteHeroSubbadge.classList.remove("hidden");
      el.muteHeroSubbadge.textContent = "BUZZER MUTED";

      el.alarmHeroStateText.textContent = "ALARM SILENCED (MUTED)";
      el.alarmHeroDetailText.textContent = "Physical buzzer on GPIO 23 is silenced. Alarm will automatically re-arm if water level changes.";

      el.btnSilenceAlarm.className = "btn-silence-alarm btn-state-silenced";
      el.btnSilenceAlarm.disabled = true;
      el.btnSilenceText.textContent = "ALARM SILENCED (BUZZER OFF)";
    }
    // State 3: Alarm Inactive (Normal level 25%, 50%, 75%)
    else {
      el.alarmStatusContainer.className = "alarm-status-container";
      el.alarmHeroIndicator.className = "alarm-indicator-bulb inactive";
      el.muteHeroSubbadge.classList.add("hidden");

      el.alarmHeroStateText.textContent = "ALARM INACTIVE";
      el.alarmHeroDetailText.textContent = "Physical buzzer on GPIO 23 is quiet. Alerts sound automatically at 0% or 100%.";

      el.btnSilenceAlarm.className = "btn-silence-alarm btn-state-inactive";
      el.btnSilenceAlarm.disabled = true;
      el.btnSilenceText.textContent = "ALARM INACTIVE";
    }
  }

  /**
   * Handles user click on "SILENCE ALARM".
   * Communicates bidirectionally with Render Cloud and ESP32.
   */
  async function handleSilenceAlarmClick() {
    if (state.commandInFlight) return;

    // Check if operator token is present in local storage
    const token = state.operatorToken.trim();

    state.commandInFlight = true;
    updateAlarmControlUI();
    setCommandFeedback("Transmitting silence command to cloud backend...");

    try {
      const headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
      };
      if (token) {
        headers["X-Dashboard-Token"] = token;
      }

      const res = await fetch(ENDPOINTS.muteCommand, {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ device_id: "esp32-tank-01" })
      });

      if (res.status === 401) {
        // Operator authorization required
        state.commandInFlight = false;
        updateAlarmControlUI();
        setCommandFeedback("Authorization required. Please enter Operator Control Token.");
        openSettingsModal();
        return;
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error (${res.status})`);
      }

      const cmd = await res.json();
      state.pendingCommandId = cmd.id;
      setCommandFeedback(`Command #${cmd.id} posted. Waiting for ESP32 hardware acknowledgement...`);

      // Begin polling command status until ESP32 acknowledges
      pollCommandAcknowledgment(cmd.id);

    } catch (err) {
      console.error("[TankPulse] Failed to transmit mute command:", err);
      state.commandInFlight = false;
      updateAlarmControlUI();
      setCommandFeedback(`Error: ${err.message}`);
    }
  }

  /**
   * Polls GET /api/commands/status/{id} until the ESP32 hardware acknowledges execution.
   */
  function pollCommandAcknowledgment(commandId) {
    let attempts = 0;
    const maxAttempts = 15; // 15 attempts x 1.2s = 18s timeout

    const pollInterval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetch(ENDPOINTS.commandStatus(commandId), {
          cache: "no-store",
          headers: { "Accept": "application/json" }
        });

        if (res.ok) {
          const cmd = await res.json();
          if (cmd.command_status === "ACKNOWLEDGED") {
            clearInterval(pollInterval);
            state.commandInFlight = false;
            setCommandFeedback(`Success: ESP32 acknowledged command #${commandId}. Physical buzzer silenced!`);
            
            // Immediately refresh telemetry to sync dashboard
            fetchTelemetry();
            return;
          } else if (cmd.command_status === "EXPIRED") {
            clearInterval(pollInterval);
            state.commandInFlight = false;
            updateAlarmControlUI();
            setCommandFeedback(`Notice: Command #${commandId} expired before ESP32 received it.`);
            fetchTelemetry();
            return;
          }
        }
      } catch (e) {
        // Continue polling
      }

      if (attempts >= maxAttempts) {
        clearInterval(pollInterval);
        state.commandInFlight = false;
        updateAlarmControlUI();
        setCommandFeedback(`Notice: Command #${commandId} queued. Waiting for ESP32 check-in.`);
        fetchTelemetry();
      }
    }, 1200);
  }

  function setCommandFeedback(text) {
    if (el.commandFeedbackText) {
      el.commandFeedbackText.textContent = text;
    }
  }

  // ============================================================================
  // 7. PART 3: REALTIME LEVEL Activity Timeline Modal
  // ============================================================================

  /**
   * Generates chronological plain-language events from verified readings & commands.
   */
  function buildTimelineEvents() {
    const events = [];

    // 1. Process consecutive water level transitions
    const historyReadings = [...state.history].reverse(); // oldest first

    for (let i = 0; i < historyReadings.length; i++) {
      const current = historyReadings[i];
      const prev = i > 0 ? historyReadings[i - 1] : null;

      // Event: Water Level Change
      if (!prev) {
        events.push({
          type: "level",
          icon: "💧",
          class: "item-water-up",
          headline: `Water tank is at ${current.water_level}%`,
          detail: getLevelCondition(current.water_level).desc,
          time: current.created_at,
        });
      } else if (current.water_level !== prev.water_level) {
        const increased = current.water_level > prev.water_level;
        events.push({
          type: "level",
          icon: increased ? "📈" : "📉",
          class: increased ? "item-water-up" : "item-water-down",
          headline: increased 
            ? `Water level increased to ${current.water_level}%` 
            : `Water level decreased to ${current.water_level}%`,
          detail: `Transitioned from ${prev.water_level}% to ${current.water_level}% capacity`,
          time: current.created_at,
        });
      }

      // Event: Alarm Activation
      if (current.alarm && (!prev || !prev.alarm)) {
        events.push({
          type: "alarm",
          icon: "🚨",
          class: "item-alarm",
          headline: current.water_level === 0 ? "Empty-tank alarm activated" : "Full-tank alarm activated",
          detail: "Audible buzzer on GPIO 23 started sounding",
          time: current.created_at,
        });
      }

      // Event: Buzzer Silenced
      if (current.muted && (!prev || !prev.muted)) {
        events.push({
          type: "alarm",
          icon: "🔕",
          class: "item-mute",
          headline: "Alarm silenced on hardware",
          detail: "Physical buzzer muted; will re-arm if water level changes",
          time: current.created_at,
        });
      }
    }

    // 2. Process acknowledged remote commands
    if (Array.isArray(state.commandHistory)) {
      state.commandHistory.forEach((cmd) => {
        if (cmd.command_status === "ACKNOWLEDGED") {
          events.push({
            type: "alarm",
            icon: "✅",
            class: "item-mute",
            headline: "Alarm silenced from dashboard",
            detail: `ESP32 confirmed command #${cmd.id} execution on GPIO 23 buzzer`,
            time: cmd.acknowledged_at || cmd.created_at,
          });
        }
      });
    }

    // 3. Add latest telemetry connection heartbeat
    if (state.latestReading) {
      events.push({
        type: "connection",
        icon: "📡",
        class: "item-system",
        headline: "Latest water-level reading received successfully",
        detail: `Verified telemetry snapshot #${state.latestReading.id} from ESP32`,
        time: state.latestReading.created_at,
      });
    }

    // Sort newest first
    events.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());

    return events;
  }

  /**
   * Renders the timeline modal list based on active filter.
   */
  function renderTimeline() {
    if (!el.timelineList) return;

    const allEvents = buildTimelineEvents();
    const filter = state.activeFilter;

    const filtered = allEvents.filter((ev) => {
      if (filter === "all") return true;
      if (filter === "level") return ev.type === "level";
      if (filter === "alarm") return ev.type === "alarm";
      if (filter === "connection") return ev.type === "connection";
      return true;
    });

    if (filtered.length === 0) {
      el.timelineList.innerHTML = `
        <div class="timeline-empty">
          <p>No activity records match the selected filter.</p>
        </div>
      `;
      return;
    }

    const html = filtered.map((ev) => `
      <div class="timeline-item ${ev.class}">
        <div class="timeline-dot-box">${ev.icon}</div>
        <div class="timeline-content-card">
          <div class="timeline-header-row">
            <span class="timeline-headline">${ev.headline}</span>
            <span class="timeline-time font-mono">${formatISTShort(ev.time, false)}</span>
          </div>
          <p class="timeline-detail">${ev.detail}</p>
        </div>
      </div>
    `).join("");

    el.timelineList.innerHTML = html;
  }

  function openTimelineModal() {
    if (!el.timelineModal) return;
    renderTimeline();
    el.timelineModal.classList.remove("hidden");
  }

  function closeTimelineModal() {
    if (!el.timelineModal) return;
    el.timelineModal.classList.add("hidden");
  }

  // ============================================================================
  // 8. Settings & Operator Token Management
  // ============================================================================
  function openSettingsModal() {
    if (!el.settingsModal) return;
    if (el.inputOperatorToken) el.inputOperatorToken.value = state.operatorToken;
    el.settingsModal.classList.remove("hidden");
  }

  function closeSettingsModal() {
    if (!el.settingsModal) return;
    el.settingsModal.classList.add("hidden");
  }

  function saveOperatorToken() {
    if (!el.inputOperatorToken) return;
    const val = el.inputOperatorToken.value.trim();
    state.operatorToken = val;
    localStorage.setItem(STORAGE_KEY_TOKEN, val);
    closeSettingsModal();
    setCommandFeedback(val ? "Operator token saved in browser." : "Operator token cleared.");
  }

  function clearOperatorToken() {
    state.operatorToken = "";
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    if (el.inputOperatorToken) el.inputOperatorToken.value = "";
    closeSettingsModal();
    setCommandFeedback("Operator token cleared.");
  }

  // ============================================================================
  // 9. UI Renderers
  // ============================================================================

  /**
   * Updates all DOM elements with the latest reading payload.
   */
  function renderLatestReading(reading) {
    if (!reading) return;

    const level = reading.water_level;
    const condition = getLevelCondition(level);

    // 1. Hero Percentage & Condition
    el.heroPercentage.textContent = level;
    el.heroStatusText.textContent = condition.desc;
    el.levelConditionBadge.textContent = condition.label;
    el.levelConditionBadge.className = `condition-badge ${condition.badgeClass}`;

    // 2. Trend Badge (Filling, Draining, or Stable)
    if (state.previousReading) {
      const prevLevel = state.previousReading.water_level;
      if (level > prevLevel) {
        el.trendBadge.className = "trend-badge trend-filling";
        el.trendBadge.textContent = "Filling up ↑";
      } else if (level < prevLevel) {
        el.trendBadge.className = "trend-badge trend-draining";
        el.trendBadge.textContent = "Draining ↓";
      } else {
        el.trendBadge.className = "trend-badge trend-stable";
        el.trendBadge.textContent = "Level Stable ↔";
      }
    }

    // 3. Metadata: IST Timestamp, Relative Time, ID
    el.timestampIST.textContent = formatIST(reading.created_at);
    el.relativeTime.textContent = formatRelativeTime(reading.created_at);
    el.readingId.textContent = `#${reading.id}`;

    // 4. Hardware Freshness Check (ESP32 online if reading is within 45s)
    const readingTime = new Date(reading.created_at).getTime();
    const ageSeconds = Math.floor((Date.now() - readingTime) / 1000);
    const isRecent = ageSeconds < 45;

    if (isRecent) {
      el.hardwareLinkStatus.className = "meta-value status-badge badge-online";
      el.hardwareLinkStatus.textContent = "ESP32 Online (Live)";
    } else {
      el.hardwareLinkStatus.className = "meta-value status-badge badge-stale";
      el.hardwareLinkStatus.textContent = `Telemetry Stale (${formatRelativeTime(reading.created_at)})`;
    }

    // 5. Probes Status (Strictly "Filled" and "Empty")
    updateProbeElement(el.probeCard25, el.probeState25, reading.probe_25);
    updateProbeElement(el.probeCard50, el.probeState50, reading.probe_50);
    updateProbeElement(el.probeCard75, el.probeState75, reading.probe_75);
    updateProbeElement(el.probeCard100, el.probeState100, reading.probe_100);

    // 6. Physical Buzzer Mute Status in Hardware Card
    const isMuted = Boolean(reading.muted);
    if (isMuted) {
      el.muteStatusBadge.className = "status-pill-badge badge-muted-on";
      el.muteStatusBadge.textContent = "Silenced (Muted)";
      el.buzzerPhysicalStateDesc.textContent = "Physical buzzer is silenced on GPIO 23";
    } else {
      el.muteStatusBadge.className = "status-pill-badge badge-muted-off";
      el.muteStatusBadge.textContent = "Unmuted";
      el.buzzerPhysicalStateDesc.textContent = "Audible buzzer alerts at 0% and 100%";
    }

    // 7. Update Prominent Alarm Control Section
    updateAlarmControlUI();

    // 8. Firmware Hardware LEDs Simulation
    const isFull = (level === 100);
    const leds = [el.led1, el.led2, el.led3, el.led4, el.led5];
    leds.forEach(l => l.classList.remove("on", "blink"));

    if (isFull) {
      leds.forEach(l => l.classList.add("on", "blink"));
    } else {
      if (level === 0) el.led1.classList.add("on");
      else if (level === 25) el.led2.classList.add("on");
      else if (level === 50) el.led3.classList.add("on");
      else if (level === 75) el.led4.classList.add("on");
    }
  }

  function updateProbeElement(cardEl, stateEl, isFilled) {
    if (!cardEl || !stateEl) return;
    if (isFilled) {
      cardEl.className = "probe-card probe-filled";
      stateEl.textContent = "Filled";
    } else {
      cardEl.className = "probe-card probe-empty";
      stateEl.textContent = "Empty";
    }
  }

  function renderHistoryTable(readings) {
    if (!el.telemetryTableBody) return;

    if (!readings || readings.length === 0) {
      el.recordsCountBadge.textContent = "0 records";
      el.telemetryTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center" style="padding: 2rem; color: var(--text-muted);">
            No historical telemetry records found in PostgreSQL database.
          </td>
        </tr>
      `;
      return;
    }

    el.recordsCountBadge.textContent = `${readings.length} records`;

    const rowsHtml = readings.map((r) => {
      const condition = getLevelCondition(r.water_level);
      const isAlarm = Boolean(r.alarm);
      const isMuted = Boolean(r.muted);

      const probePill = (filled, label) => 
        `<span class="table-probe-pill ${filled ? "filled" : "empty"}">${label}: ${filled ? "Filled" : "Empty"}</span>`;

      return `
        <tr>
          <td class="font-mono">#${r.id}</td>
          <td class="font-mono">${formatIST(r.created_at)}</td>
          <td>
            <strong style="color: var(--text-main); font-size: 0.95rem;">${r.water_level}%</strong>
            <span class="condition-badge ${condition.badgeClass}" style="margin-left: 0.5rem; font-size: 0.65rem; padding: 0.15rem 0.45rem;">
              ${condition.label}
            </span>
          </td>
          <td>
            <div class="table-probe-indicator">
              ${probePill(r.probe_25, "25%")}
              ${probePill(r.probe_50, "50%")}
              ${probePill(r.probe_75, "75%")}
              ${probePill(r.probe_100, "100%")}
            </div>
          </td>
          <td>
            <span class="status-pill-badge ${isAlarm ? "badge-critical" : "badge-ok"}" style="font-size: 0.68rem;">
              ${isAlarm ? "ACTIVE" : "Normal"}
            </span>
          </td>
          <td>
            <span class="status-pill-badge ${isMuted ? "badge-muted-on" : "badge-muted-off"}" style="font-size: 0.68rem;">
              ${isMuted ? "Silenced" : "No"}
            </span>
          </td>
        </tr>
      `;
    }).join("");

    el.telemetryTableBody.innerHTML = rowsHtml;
  }

  function renderHistoryChart(readings) {
    if (!el.historyChart || typeof Chart === "undefined") return;
    if (!readings || readings.length === 0) return;

    const sorted = [...readings].reverse();
    const labels = sorted.map((r) => formatISTShort(r.created_at));
    const dataPoints = sorted.map((r) => r.water_level);

    if (chartInstance) {
      chartInstance.data.labels = labels;
      chartInstance.data.datasets[0].data = dataPoints;
      chartInstance.update("none");
      return;
    }

    const ctx = el.historyChart.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, "rgba(56, 189, 248, 0.35)");
    gradient.addColorStop(1, "rgba(56, 189, 248, 0.0)");

    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Water Level (%)",
            data: dataPoints,
            borderColor: "#38bdf8",
            borderWidth: 2.5,
            backgroundColor: gradient,
            fill: true,
            tension: 0.3,
            pointBackgroundColor: "#0284c7",
            pointBorderColor: "#38bdf8",
            pointRadius: 4,
            pointHoverRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600 },
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            titleColor: "#94a3b8",
            titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
            bodyColor: "#ffffff",
            bodyFont: { family: "'Inter', sans-serif", size: 13, weight: "bold" },
            borderColor: "rgba(56, 189, 248, 0.3)",
            borderWidth: 1,
            padding: 10,
            displayColors: false,
            callbacks: {
              title: function (items) {
                const idx = items[0].dataIndex;
                const reading = sorted[idx];
                return reading ? formatIST(reading.created_at) : items[0].label;
              },
              label: function (context) {
                const idx = context.dataIndex;
                const reading = sorted[idx];
                const cond = getLevelCondition(context.parsed.y);
                const probeStates = reading
                  ? `[25%: ${reading.probe_25 ? "Filled" : "Empty"} | 50%: ${reading.probe_50 ? "Filled" : "Empty"} | 75%: ${reading.probe_75 ? "Filled" : "Empty"} | 100%: ${reading.probe_100 ? "Filled" : "Empty"}]`
                  : "";
                return [
                  `Level: ${context.parsed.y}% (${cond.label})`,
                  `Probes: ${probeStates}`,
                ];
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#64748b",
              font: { family: "'JetBrains Mono', monospace", size: 10 },
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 7,
            },
          },
          y: {
            min: 0,
            max: 100,
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            ticks: {
              stepSize: 25,
              color: "#64748b",
              font: { family: "'JetBrains Mono', monospace", size: 11 },
              callback: (val) => val + "%",
            },
          },
        },
      },
    });
  }

  // ============================================================================
  // 10. Fetch Telemetry Data from Cloud API
  // ============================================================================
  async function fetchTelemetry() {
    if (state.fetchInFlight) return;
    state.fetchInFlight = true;

    try {
      const latestPromise = fetch(ENDPOINTS.latest, {
        cache: "no-store",
        headers: { "Accept": "application/json" }
      });

      const historyPromise = fetch(ENDPOINTS.history, {
        cache: "no-store",
        headers: { "Accept": "application/json" }
      });

      const commandHistoryPromise = fetch(ENDPOINTS.commandHistory, {
        cache: "no-store",
        headers: { "Accept": "application/json" }
      }).catch(() => null);

      const [latestRes, historyRes, cmdHistRes] = await Promise.all([
        latestPromise,
        historyPromise,
        commandHistoryPromise
      ]);

      if (!latestRes.ok) {
        throw new Error(`Cloud API returned HTTP ${latestRes.status}`);
      }

      const latestData = await latestRes.json();
      state.previousReading = state.latestReading;
      state.latestReading = latestData;
      renderLatestReading(latestData);

      if (historyRes.ok) {
        const historyData = await historyRes.json();
        state.history = Array.isArray(historyData) ? historyData : [];
        renderHistoryTable(state.history);
        renderHistoryChart(state.history);
      }

      if (cmdHistRes && cmdHistRes.ok) {
        const cmdData = await cmdHistRes.json();
        state.commandHistory = Array.isArray(cmdData) ? cmdData : [];
      }

      // Update Timeline modal if open
      if (el.timelineModal && !el.timelineModal.classList.contains("hidden")) {
        renderTimeline();
      }

      state.isConnected = true;
      state.consecutiveErrors = 0;
      state.lastSuccessfulFetch = new Date();
      updateConnectionStatus("connected", "Connected (Render Cloud API)");

    } catch (err) {
      console.warn("[TankPulse] Error fetching cloud telemetry:", err.message);
      state.consecutiveErrors++;

      if (state.consecutiveErrors >= 2) {
        state.isConnected = false;
        updateConnectionStatus("error", `API Connection Error (${err.message})`);
      }
    } finally {
      state.fetchInFlight = false;
      resetCountdown();
    }
  }

  function updateConnectionStatus(status, text) {
    if (!el.connectionPill || !el.connectionText) return;
    el.connectionPill.className = `status-pill pill-${status}`;
    el.connectionText.textContent = text;
  }

  // ============================================================================
  // 11. Countdown & Auto-Refresh Timer
  // ============================================================================
  const CIRCLE_CIRCUMFERENCE = 2 * Math.PI * 11; // r=11 => 69.115

  function resetCountdown() {
    state.countdownSeconds = 5;
    updateCountdownUI();
  }

  function updateCountdownUI() {
    if (!el.countdownText || !el.refreshCircle) return;
    el.countdownText.textContent = `${state.countdownSeconds}s`;

    const progress = (5 - state.countdownSeconds) / 5;
    const offset = CIRCLE_CIRCUMFERENCE * (1 - progress);
    el.refreshCircle.style.strokeDashoffset = offset;
  }

  function startRefreshLoop() {
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = setInterval(() => {
      state.countdownSeconds--;
      if (state.countdownSeconds <= 0) {
        resetCountdown();
      } else {
        updateCountdownUI();
      }

      if (state.latestReading) {
        el.relativeTime.textContent = formatRelativeTime(state.latestReading.created_at);
      }
    }, 1000);

    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      fetchTelemetry();
    }, REFRESH_INTERVAL_MS);
  }

  // ============================================================================
  // 12. Event Listeners & Modal Controls
  // ============================================================================
  function setupEventListeners() {
    // 1. Prominent Silence Alarm Button Click
    if (el.btnSilenceAlarm) {
      el.btnSilenceAlarm.addEventListener("click", handleSilenceAlarmClick);
    }

    // 2. REALTIME LEVEL Timeline Button Click
    if (el.btnOpenTimeline) {
      el.btnOpenTimeline.addEventListener("click", openTimelineModal);
    }
    if (el.btnCloseTimeline) {
      el.btnCloseTimeline.addEventListener("click", closeTimelineModal);
    }
    if (el.btnCloseTimelineFooter) {
      el.btnCloseTimelineFooter.addEventListener("click", closeTimelineModal);
    }

    // Timeline Filter Tabs
    if (el.filterTabs) {
      el.filterTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
          el.filterTabs.forEach((t) => t.classList.remove("active"));
          tab.classList.add("active");
          state.activeFilter = tab.getAttribute("data-filter") || "all";
          renderTimeline();
        });
      });
    }

    // 3. Settings / Operator Token Modal
    if (el.btnOpenSettings) {
      el.btnOpenSettings.addEventListener("click", openSettingsModal);
    }
    if (el.btnCloseSettings) {
      el.btnCloseSettings.addEventListener("click", closeSettingsModal);
    }
    if (el.btnSaveToken) {
      el.btnSaveToken.addEventListener("click", saveOperatorToken);
    }
    if (el.btnClearToken) {
      el.btnClearToken.addEventListener("click", clearOperatorToken);
    }

    // 4. Manual Refresh Button
    if (el.btnManualRefresh) {
      el.btnManualRefresh.addEventListener("click", () => {
        el.btnManualRefresh.classList.add("spinning");
        resetCountdown();
        fetchTelemetry().finally(() => {
          setTimeout(() => {
            el.btnManualRefresh.classList.remove("spinning");
          }, 600);
        });
      });
    }

    // 5. Global Alert Dismiss
    if (el.alertDismiss) {
      el.alertDismiss.addEventListener("click", () => {
        if (el.alertBanner) el.alertBanner.classList.add("hidden");
      });
    }

    // 6. Close modals on backdrop click
    window.addEventListener("click", (evt) => {
      if (evt.target === el.timelineModal) closeTimelineModal();
      if (evt.target === el.settingsModal) closeSettingsModal();
    });

    // 7. Window visibility listener
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        fetchTelemetry();
      }
    });
  }

  // ============================================================================
  // 13. Application Initialization
  // ============================================================================
  function init() {
    console.log("[TankPulse] Initializing Water Tank Cloud Monitor dashboard...");
    console.log("[TankPulse] Cloud Target:", API_BASE);

    // Initialize Animated Water Tank Canvas
    initTankCanvas();

    // Setup circular countdown stroke
    if (el.refreshCircle) {
      el.refreshCircle.style.strokeDasharray = CIRCLE_CIRCUMFERENCE;
      el.refreshCircle.style.strokeDashoffset = 0;
    }

    // Setup DOM Event Listeners
    setupEventListeners();

    // Trigger initial data fetch immediately
    fetchTelemetry();

    // Start auto-refresh timer loop
    startRefreshLoop();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
