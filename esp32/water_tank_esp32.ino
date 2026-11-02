#include <WiFi.h>
#include <WebServer.h>
#include "secrets.h"

WebServer server(80);

// ---------- Sensor pins (probe touches water = pin pulled LOW) ----------
const int wire25  = 5;
const int wire50  = 4;
const int wire75  = 16;
const int wire100 = 17;

// ---------- LED pins ----------
const int ledRedBelow25 = 13;  // Below 25%
const int ledRed25to50  = 22;  // 25% to 50%
const int ledYel50to75  = 21;  // 50% to 75%
const int ledYel75to100 = 19;  // 75% to 100%
const int ledGreen100   = 18;  // 100% full

// ---------- Buzzer ----------
const int buzzerPin = 23;

// ---------- State ----------
bool buzzerMuted = false;
int  level = 0;            // stable level used by LEDs, buzzer and the web page
int  candidate = -1;       // debounce: new reading must repeat before it is accepted
int  candidateCount = 0;
const int STABLE_READS = 3;  // 3 reads x 200 ms = 600 ms

// =====================================================
//  Dashboard page (HTML + CSS + JS), stored in flash
// =====================================================
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Water tank level</title>
<style>
:root{
  --bg:#e8eef1; --panel:#f6f9fa; --ink:#12303b; --muted:#5b7580; --line:#c8d6dc;
  --water:#1f8fb3; --deep:#0f6b8c; --ok:#2e8b6a; --warn:#d9822b; --bad:#c23b3b;
  --font:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#0e1a20; --panel:#15252d; --ink:#e3eef2; --muted:#8fa9b4; --line:#27404b; --water:#35b3d8; --deep:#1b86a8; }
}
*{box-sizing:border-box}
body{margin:0;padding:20px;background:var(--bg);color:var(--ink);font-family:var(--font);line-height:1.45}
.wrap{max-width:980px;margin:0 auto}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:18px}
h1{font-size:1.6rem;font-weight:800;margin:0;letter-spacing:-.02em}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;background:var(--panel);border:1px solid var(--line);font-size:.85rem;color:var(--muted)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--muted)}
.pill.live .dot{background:var(--ok)} .pill.offline .dot{background:var(--bad)}
.alert{padding:12px 16px;border-radius:12px;margin-bottom:18px;font-weight:600;border:1px solid var(--line);background:var(--panel)}
.alert.ok{border-color:var(--ok);color:var(--ok)} .alert.warn{border-color:var(--warn);color:var(--warn)} .alert.bad{border-color:var(--bad);color:var(--bad)}
.grid{display:grid;grid-template-columns:minmax(240px,340px) 1fr;gap:18px}
@media (max-width:720px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px}
.tank-panel{display:flex;justify-content:center;align-items:center}
#tank{width:100%;max-width:300px;height:auto;display:block}
.big{font-size:clamp(3rem,9vw,4.8rem);font-weight:800;letter-spacing:-.04em;line-height:1}
.sub{color:var(--muted);margin-top:6px}
.probes{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}
.probe{border:1px solid var(--line);border-radius:12px;padding:10px;text-align:center;font-size:.85rem;color:var(--muted)}
.probe b{display:block;font-size:1.05rem;color:var(--muted)}
.probe.wet{border-color:var(--water)} .probe.wet b{color:var(--water)}
h2{font-size:1rem;margin:0 0 10px;font-weight:600;color:var(--muted)}
#chart{width:100%;height:150px;display:block}
button{font:inherit;font-weight:600;color:#fff;background:var(--bad);border:0;border-radius:10px;padding:12px 20px;cursor:pointer;margin-top:18px}
button:disabled{background:var(--line);color:var(--muted);cursor:default}
:focus-visible{outline:3px solid var(--water);outline-offset:2px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Water tank level</h1>
    <span id="status" class="pill"><span class="dot"></span><span id="statusText">Connecting…</span></span>
  </header>

  <div id="alert" class="alert ok">Waiting for the sensor…</div>

  <div class="grid">
    <section class="panel tank-panel">
      <canvas id="tank" width="300" height="440" role="img" aria-label="Water tank level"></canvas>
    </section>

    <section>
      <div class="panel">
        <div class="big" id="big">–</div>
        <div class="sub" id="sub">&nbsp;</div>
        <div class="probes" id="probes"></div>
        <button id="mute" type="button" disabled>Silence alarm</button>
      </div>
      <div class="panel" style="margin-top:18px">
        <h2>Last 10 minutes</h2>
        <canvas id="chart"></canvas>
      </div>
    </section>
  </div>
</div>

<script>
(function(){
  const $ = id => document.getElementById(id);

  // Sensor has 4 probes, so the level is one of 5 bands.
  // "mid" is where the water is drawn inside the band.
  const BANDS = {
    0:   {label:"Below 25%", mid:12,  msg:"Tank is almost empty. Refill now.", cls:"bad"},
    25:  {label:"25–50%",    mid:37,  msg:"Water level is low.",               cls:"warn"},
    50:  {label:"50–75%",    mid:62,  msg:"Tank level is normal.",             cls:"ok"},
    75:  {label:"75–100%",   mid:87,  msg:"Tank level is normal.",             cls:"ok"},
    100: {label:"Full",      mid:100, msg:"Tank is full.",                     cls:"ok"}
  };
  const PROBE_NAMES = ["25%","50%","75%","100%"];

  let target = 12, shown = 12, history = [];
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // probe cards
  $("probes").innerHTML = PROBE_NAMES.map((n,i) =>
    '<div class="probe" id="p'+i+'"><b>'+n+'</b><span>–</span></div>').join("");

  function setStatus(kind, text){
    $("status").className = "pill " + kind;
    $("statusText").textContent = text;
  }

  async function poll(){
    try{
      const res = await fetch("/level", {cache:"no-store"});
      const d = await res.json();
      const band = BANDS[d.level] || BANDS[0];
      target = band.mid;

      $("big").textContent = band.label;
      $("sub").textContent = d.level === 100 ? "All four probes are wet" : "Reading comes from 4 probes";
      const a = $("alert"); a.className = "alert " + band.cls; a.textContent = band.msg;

      d.probes.forEach((wet,i) => {
        const el = $("p"+i);
        el.className = "probe" + (wet ? " wet" : "");
        el.lastChild.textContent = wet ? "Wet" : "Dry";
      });

      const m = $("mute");
      if (d.alarm && !d.muted){ m.disabled = false; m.textContent = "Silence alarm"; }
      else { m.disabled = true; m.textContent = d.alarm ? "Alarm silenced" : "Alarm off"; }

      history.push({t:Date.now(), v:band.mid});
      const cut = Date.now() - 600000;
      history = history.filter(p => p.t >= cut);
      setStatus("live", "Live · " + new Date().toLocaleTimeString());
    }catch(e){
      setStatus("offline", "Can’t reach the tank");
    }
  }

  $("mute").addEventListener("click", () => {
    fetch("/mute", {method:"POST"}).then(poll);
  });

  // ----- canvas helpers -----
  const cv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function setup(c,w,h){
    const r = window.devicePixelRatio || 1;
    c.width = w*r; c.height = h*r;
    const x = c.getContext("2d"); x.setTransform(r,0,0,r,0,0); return x;
  }
  function rr(ctx,x,y,w,h,r){
    ctx.beginPath(); ctx.moveTo(x+r,y);
    ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r);
    ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath();
  }

  // ----- tank -----
  const TW=300, TH=440, tctx = setup($("tank"), TW, TH);
  let wave = 0;
  function drawTank(){
    const ctx = tctx, x=30, y=20, w=TW-60, h=TH-40, r=34;
    const water=cv("--water"), deep=cv("--deep"), line=cv("--line"), ink=cv("--ink"), bg=cv("--bg");
    ctx.clearRect(0,0,TW,TH);
    rr(ctx,x,y,w,h,r); ctx.fillStyle=bg; ctx.fill();
    ctx.save(); rr(ctx,x,y,w,h,r); ctx.clip();

    const surface = y + h - (shown/100)*h;
    const amp = calm ? 0 : 5;
    function layer(off,color,alpha){
      ctx.beginPath(); ctx.moveTo(x,y+h);
      for(let px=0; px<=w; px+=4) ctx.lineTo(x+px, surface + Math.sin(px/w*Math.PI*3 + wave + off)*amp);
      ctx.lineTo(x+w,y+h); ctx.closePath();
      ctx.globalAlpha=alpha; ctx.fillStyle=color; ctx.fill(); ctx.globalAlpha=1;
    }
    layer(1.8,water,.55); layer(0,deep,.9);

    ctx.font = "12px " + cv("--font"); ctx.textBaseline = "middle";
    [25,50,75,100].forEach(m => {
      const ty = y + h - (m/100)*h + (m===100 ? 8 : 0);
      ctx.globalAlpha=.3; ctx.strokeStyle=ink; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.moveTo(x,ty); ctx.lineTo(x+18,ty); ctx.stroke();
      ctx.globalAlpha=.65; ctx.fillStyle=ink; ctx.fillText(m+"%", x+24, ty);
      ctx.globalAlpha=1;
    });
    ctx.restore();
    rr(ctx,x,y,w,h,r); ctx.lineWidth=4; ctx.strokeStyle=line; ctx.stroke();
  }

  // ----- history chart (steps) -----
  function drawChart(){
    const c=$("chart"), W=c.clientWidth, H=c.clientHeight, ctx=setup(c,W,H);
    const line=cv("--line"), water=cv("--water"), muted=cv("--muted");
    ctx.clearRect(0,0,W,H); ctx.font="11px "+cv("--font"); ctx.fillStyle=muted; ctx.strokeStyle=line; ctx.lineWidth=1;
    const py = p => H-4-(p/100)*(H-12);
    [0,50,100].forEach(v => { ctx.beginPath(); ctx.moveTo(34,py(v)); ctx.lineTo(W,py(v)); ctx.stroke(); ctx.fillText(v+"%",0,py(v)+4); });
    if(history.length < 2){ ctx.fillText("Collecting readings…", 44, H/2); return; }
    const t1=Date.now(), t0=t1-600000, px = t => 34 + (t-t0)/(t1-t0)*(W-34);
    ctx.beginPath();
    history.forEach((p,i) => i ? ctx.lineTo(px(p.t),py(p.v)) : ctx.moveTo(px(p.t),py(p.v)));
    ctx.strokeStyle=water; ctx.lineWidth=2.5; ctx.stroke();
    ctx.lineTo(px(history[history.length-1].t),py(0)); ctx.lineTo(px(history[0].t),py(0)); ctx.closePath();
    ctx.globalAlpha=.15; ctx.fillStyle=water; ctx.fill(); ctx.globalAlpha=1;
  }

  let lastChart = 0;
  function frame(now){
    shown += (target-shown)*0.04;
    if(!calm) wave += 0.04;
    drawTank();
    if(now-lastChart > 1000){ drawChart(); lastChart = now; }
    requestAnimationFrame(frame);
  }

  window.addEventListener("resize", drawChart);
  poll(); setInterval(poll, 1500);
  requestAnimationFrame(frame);
})();
</script>
</body>
</html>
)rawliteral";

// =====================================================
//  Sensor + outputs
// =====================================================
int readWaterPercentage() {
  if (digitalRead(wire100) == LOW) return 100;
  if (digitalRead(wire75)  == LOW) return 75;
  if (digitalRead(wire50)  == LOW) return 50;
  if (digitalRead(wire25)  == LOW) return 25;
  return 0;  // below 25%
}

void updateLEDs(int lvl) {
  // At 100% every LED blinks together (twice per second);
  // otherwise only the LED for the current band stays on
  bool full = (lvl == 100);
  bool blinkOn = ((millis() / 250) % 2) == 0;
  bool fullState = full && blinkOn;
  digitalWrite(ledRedBelow25, fullState || lvl == 0);
  digitalWrite(ledRed25to50,  fullState || lvl == 25);
  digitalWrite(ledYel50to75,  fullState || lvl == 50);
  digitalWrite(ledYel75to100, fullState || lvl == 75);
  digitalWrite(ledGreen100,   fullState);
}

bool alarmActive() {
  return (level == 100 || level == 0);
}

// =====================================================
//  Web handlers
// =====================================================
void handleRoot() {
  server.send_P(200, "text/html; charset=utf-8", INDEX_HTML);
}

void handleLevelJSON() {
  String json = "{\"level\":" + String(level);
  json += ",\"probes\":[";
  json += (digitalRead(wire25)  == LOW) ? "1," : "0,";
  json += (digitalRead(wire50)  == LOW) ? "1," : "0,";
  json += (digitalRead(wire75)  == LOW) ? "1," : "0,";
  json += (digitalRead(wire100) == LOW) ? "1" : "0";
  json += "],\"alarm\":";
  json += alarmActive() ? "true" : "false";
  json += ",\"muted\":";
  json += buzzerMuted ? "true" : "false";
  json += "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

void handleMute() {
  buzzerMuted = true;
  digitalWrite(buzzerPin, LOW);
  server.send(200, "text/plain", "OK");
}

// =====================================================
//  Setup / loop
// =====================================================
void setup() {
  Serial.begin(115200);

  pinMode(wire25,  INPUT_PULLUP);
  pinMode(wire50,  INPUT_PULLUP);
  pinMode(wire75,  INPUT_PULLUP);
  pinMode(wire100, INPUT_PULLUP);

  pinMode(ledRedBelow25, OUTPUT);
  pinMode(ledRed25to50,  OUTPUT);
  pinMode(ledYel50to75,  OUTPUT);
  pinMode(ledYel75to100, OUTPUT);
  pinMode(ledGreen100,   OUTPUT);
  pinMode(buzzerPin,     OUTPUT);

  level = readWaterPercentage();
  updateLEDs(level);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("Dashboard URL: http://");
  Serial.println(WiFi.localIP());

  server.on("/", handleRoot);
  server.on("/level", handleLevelJSON);
  server.on("/mute", HTTP_POST, handleMute);
  server.begin();
}

void loop() {
  server.handleClient();  // runs every pass, so the page stays responsive

  static unsigned long lastRead = 0;
  static unsigned long lastPrint = 0;
  unsigned long now = millis();

  // Read the probes every 200 ms and only accept a new level once it repeats
  if (now - lastRead >= 200) {
    lastRead = now;
    int reading = readWaterPercentage();

    if (reading == level) {
      candidate = -1;
      candidateCount = 0;
    } else if (reading == candidate) {
      if (++candidateCount >= STABLE_READS) {
        level = reading;
        buzzerMuted = false;  // new level, so re-arm the alarm
        candidate = -1;
        candidateCount = 0;
      }
    } else {
      candidate = reading;
      candidateCount = 1;
    }

    digitalWrite(buzzerPin, (!buzzerMuted && alarmActive()) ? HIGH : LOW);
  }

  updateLEDs(level);  // every pass, so the 100% blink stays smooth

  // Serial log once per second
  if (now - lastPrint >= 1000) {
    lastPrint = now;
    Serial.print("Pins [25%:");  Serial.print(digitalRead(wire25)  == LOW ? "WET" : "DRY");
    Serial.print(" | 50%:");     Serial.print(digitalRead(wire50)  == LOW ? "WET" : "DRY");
    Serial.print(" | 75%:");     Serial.print(digitalRead(wire75)  == LOW ? "WET" : "DRY");
    Serial.print(" | 100%:");    Serial.print(digitalRead(wire100) == LOW ? "WET" : "DRY");
    Serial.print("] => Level: "); Serial.print(level);
    Serial.print("% | Muted: "); Serial.println(buzzerMuted ? "YES" : "NO");
  }
}
