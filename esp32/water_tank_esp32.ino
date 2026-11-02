#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <time.h>
#include "secrets.h"

// ---------- Cloud Backend Endpoints ----------
const char* cloudEndpoint        = "https://tankpulse-2sq4.onrender.com/api/readings";
const char* commandPollEndpoint  = "https://tankpulse-2sq4.onrender.com/api/commands/pending?device_id=esp32-tank-01";
const char* commandAckBaseUrl    = "https://tankpulse-2sq4.onrender.com/api/commands/";

// Trusted Root CA certificates for Render endpoint (*.onrender.com)
// Includes GlobalSign Root CA (primary root) and GTS Root R4 (Google Trust Services root)
const char* rootCACertificate PROGMEM = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIDdTCCAl2gAwIBAgILBAAAAAABFUtaw5QwDQYJKoZIhvcNAQEFBQAwVzELMAkG\n" \
"A1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24gbnYtc2ExEDAOBgNVBAsTB1Jv\n" \
"b3QgQ0ExGzAZBgNVBAMTEkdsb2JhbFNpZ24gUm9vdCBDQTAeFw05ODA5MDExMjAw\n" \
"MDBaFw0yODAxMjgxMjAwMDBaMFcxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9i\n" \
"YWxTaWduIG52LXNhMRAwDgYDVQQLEwdSb290IENBMRswGQYDVQQDExJHbG9iYWxT\n" \
"aWduIFJvb3QgQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDaDuaZ\n" \
"jc6j40+Kfvvxi4Mla+pIH/EqsLmVEQS98GPR4mdmzxzdzxtIK+6NiY6arymAZavp\n" \
"xy0Sy6scTHAHoT0KMM0VjU/43dSMUBUc71DuxC73/OlS8pF94G3VNTCOXkNz8kHp\n" \
"1Wrjsok6Vjk4bwY8iGlbKk3Fp1S4bInMm/k8yuX9ifUSPJJ4ltbcdG6TRGHRjcdG\n" \
"snUOhugZitVtbNV4FpWi6cgKOOvyJBNPc1STE4U6G7weNLWLBYy5d4ux2x8gkasJ\n" \
"U26Qzns3dLlwR5EiUWMWea6xrkEmCMgZK9FGqkjWZCrXgzT/LCrBbBlDSgeF59N8\n" \
"9iFo7+ryUp9/k5DPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNVHRMBAf8E\n" \
"BTADAQH/MB0GA1UdDgQWBBRge2YaRQ2XyolQL30EzTSo//z9SzANBgkqhkiG9w0B\n" \
"AQUFAAOCAQEA1nPnfE920I2/7LqivjTFKDK1fPxsnCwrvQmeU79rXqoRSLblCKOz\n" \
"yj1hTdNGCbM+w6DjY1Ub8rrvrTnhQ7k4o+YviiY776BQVvnGCv04zcQLcFGUl5gE\n" \
"38NflNUVyRRBnMRddWQVDf9VMOyGj/8N7yy5Y0b2qvzfvGn9LhJIZJrglfCm7ymP\n" \
"AbEVtQwdpf5pLGkkeB6zpxxxYu7KyJesF12KwvhHhm4qxFYxldBniYUr+WymXUad\n" \
"DKqC5JlR3XC321Y9YeRq4VzW9v493kHMB65jUr9TU/Qr6cf9tveCX4XSQRjbgbME\n" \
"HMUfpIBvFSDJ3gyICh3WZlXi/EjJKSZp4A==\n" \
"-----END CERTIFICATE-----\n" \
"-----BEGIN CERTIFICATE-----\n" \
"MIICCTCCAY6gAwIBAgINAgPlwGjvYxqccpBQUjAKBggqhkjOPQQDAzBHMQswCQYD\n" \
"VQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2VzIExMQzEUMBIG\n" \
"A1UEAxMLR1RTIFJvb3QgUjQwHhcNMTYwNjIyMDAwMDAwWhcNMzYwNjIyMDAwMDAw\n" \
"WjBHMQswCQYDVQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2Vz\n" \
"IExMQzEUMBIGA1UEAxMLR1RTIFJvb3QgUjQwdjAQBgcqhkjOPQIBBgUrgQQAIgNi\n" \
"AATzdHOnaItgrkO4NcWBMHtLSZ37wWHO5t5GvWvVYRg1rkDdc/eJkTBa6zzuhXyi\n" \
"QHY7qca4R9gq55KRanPpsXI5nymfopjTX15YhmUPoYRlBtHci8nHc8iMai/lxKvR\n" \
"HYqjQjBAMA4GA1UdDwEB/wQEAwIBhjAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQW\n" \
"BBSATNbrdP9JNqPV2Py1PsVq8JQdjDAKBggqhkjOPQQDAwNpADBmAjEA6ED/g94D\n" \
"9J+uHXqnLrmvT/aDHQ4thQEd0dlq7A/Cr8deVl5c1RxYIigL9zC2L7F8AjEA8GE8\n" \
"p/SgguMh1YQdc4acLa/KNJvxn7kjNuK8YAOdgLOaVsjh4rsUecrNIdSUtUlD\n" \
"-----END CERTIFICATE-----\n";

// ---------- Cloud Telemetry & FreeRTOS Synchronization ----------
struct TankTelemetry {
  int  waterLevel;
  bool probe25;
  bool probe50;
  bool probe75;
  bool probe100;
  bool alarm;
  bool muted;
};

TankTelemetry sharedTelemetry;
SemaphoreHandle_t telemetryMutex = NULL;
TaskHandle_t cloudTaskHandle = NULL;

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
//  Local Web Dashboard Page (Stored in Flash)
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
button{font:inherit;font-weight:600;color:#fff;background:var(--bad);border:0;border-radius:10px;padding:12px 20px;cursor:pointer;margin-top:18px}
button:disabled{background:var(--line);color:var(--muted);cursor:default}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Water tank level (Local Web Server)</h1>
    <span id="status" class="pill"><span class="dot"></span><span id="statusText">Connecting…</span></span>
  </header>
  <div id="alert" class="alert ok">Monitoring...</div>
  <div class="grid">
    <section class="panel tank-panel">
      <div class="big" id="big">–</div>
    </section>
    <section>
      <div class="panel">
        <button id="mute" type="button" onclick="fetch('/mute', {method:'POST'}).then(()=>location.reload())">Silence physical alarm</button>
      </div>
    </section>
  </div>
</div>
</body>
</html>
)rawliteral";

// =====================================================
//  Sensor Readings & LED Outputs
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
//  Local Web Handlers
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
  updateTelemetrySnapshot(true);  // Notify cloud immediately of mute event
  server.send(200, "text/plain", "OK");
}

// =====================================================
//  Cloud Sync & Bidirectional Command Execution
//  (FreeRTOS Background Task on Core 0)
// =====================================================
void updateTelemetrySnapshot(bool triggerImmediateSend) {
  if (telemetryMutex != NULL && xSemaphoreTake(telemetryMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    sharedTelemetry.waterLevel = level;
    sharedTelemetry.probe25    = (digitalRead(wire25)  == LOW);
    sharedTelemetry.probe50    = (digitalRead(wire50)  == LOW);
    sharedTelemetry.probe75    = (digitalRead(wire75)  == LOW);
    sharedTelemetry.probe100   = (digitalRead(wire100) == LOW);
    sharedTelemetry.alarm      = alarmActive();
    sharedTelemetry.muted      = buzzerMuted;
    xSemaphoreGive(telemetryMutex);

    if (triggerImmediateSend && cloudTaskHandle != NULL) {
      xTaskNotifyGive(cloudTaskHandle);
    }
  }
}

void acknowledgeCloudCommand(int cmdId) {
  WiFiClientSecure client;
  client.setCACert(rootCACertificate);
  client.setTimeout(8);

  HTTPClient http;
  http.setTimeout(8000);

  String ackUrl = String(commandAckBaseUrl) + String(cmdId) + "/ack";
  if (http.begin(client, ackUrl)) {
    http.addHeader("Content-Type", "application/json");
    #ifdef SECRETS_H
    if (String(deviceApiKey).length() > 0) {
      http.addHeader("X-Device-Key", deviceApiKey);
    }
    #endif

    String ackBody = "{\"device_id\":\"esp32-tank-01\",\"status\":\"ACKNOWLEDGED\"}";
    int httpCode = http.POST(ackBody);
    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
      Serial.printf("[Commands] Command #%d acknowledged successfully (HTTP %d).\n", cmdId, httpCode);
    } else if (httpCode == 401 || httpCode == 403) {
      Serial.printf("[Commands] Failed to acknowledge command #%d: Authentication failure (HTTP %d).\n", cmdId, httpCode);
    } else if (httpCode >= 500) {
      Serial.printf("[Commands] Failed to acknowledge command #%d: Server error (HTTP %d).\n", cmdId, httpCode);
    } else if (httpCode > 0) {
      Serial.printf("[Commands] Failed to acknowledge command #%d: Server returned HTTP %d.\n", cmdId, httpCode);
    } else {
      Serial.printf("[Commands] Failed to acknowledge command #%d: HTTPS connection failure (%s, code %d).\n", cmdId, http.errorToString(httpCode).c_str(), httpCode);
    }
    http.end();
  } else {
    Serial.printf("[Commands] Failed to acknowledge command #%d: Unable to establish TLS connection to ack endpoint.\n", cmdId);
  }
}

void pollPendingCloudCommands() {
  WiFiClientSecure client;
  client.setCACert(rootCACertificate);
  client.setTimeout(8);

  HTTPClient http;
  http.setTimeout(8000);

  if (http.begin(client, commandPollEndpoint)) {
    #ifdef SECRETS_H
    if (String(deviceApiKey).length() > 0) {
      http.addHeader("X-Device-Key", deviceApiKey);
    }
    #endif

    int httpCode = http.GET();
    if (httpCode == HTTP_CODE_OK) {
      String response = http.getString();

      // Check if a pending command object is present
      int idIdx = response.indexOf("\"id\":");
      if (idIdx != -1) {
        int start = idIdx + 5;
        while (start < response.length() && (response[start] == ' ' || response[start] == ':')) start++;
        int end = start;
        while (end < response.length() && isDigit(response[end])) end++;
        int cmdId = response.substring(start, end).toInt();

        // Extract command_type
        String cmdType = "UNKNOWN";
        int typeIdx = response.indexOf("\"command_type\":");
        if (typeIdx != -1) {
          int tStart = typeIdx + 15;
          while (tStart < response.length() && (response[tStart] == ' ' || response[tStart] == ':' || response[tStart] == '"')) tStart++;
          int tEnd = tStart;
          while (tEnd < response.length() && response[tEnd] != '"' && response[tEnd] != ',' && response[tEnd] != '}') tEnd++;
          cmdType = response.substring(tStart, tEnd);
        }

        if (cmdId > 0) {
          Serial.printf("[Commands] Pending command received — ID: #%d, Type: %s\n", cmdId, cmdType.c_str());

          if (cmdType == "MUTE_ALARM") {
            // Only silence buzzer if alarm is currently active (level 0% or 100%)
            // Prevents reconnected ESP32 from muting future alarms
            if (alarmActive()) {
              buzzerMuted = true;
              digitalWrite(buzzerPin, LOW);
              updateTelemetrySnapshot(true);
              Serial.println("[Commands] Physical buzzer on GPIO 23 silenced.");
            } else {
              Serial.println("[Commands] Alarm is not active; command acknowledged without muting future alarms.");
            }
          } else {
            Serial.printf("[Commands] Unhandled command type '%s' (acknowledging to clear).\n", cmdType.c_str());
          }

          // Send acknowledgment back to cloud to clear command
          acknowledgeCloudCommand(cmdId);
        } else {
          Serial.println("[Commands] Polled cloud: No pending commands.");
        }
      } else {
        // Successful poll with no pending commands
        Serial.println("[Commands] Polled cloud: No pending commands.");
      }
    } else if (httpCode == 401 || httpCode == 403) {
      Serial.printf("[Commands] Authentication failure (HTTP %d): Invalid or missing X-Device-Key.\n", httpCode);
    } else if (httpCode >= 500) {
      Serial.printf("[Commands] Server error (HTTP %d): Backend service or database issue.\n", httpCode);
    } else if (httpCode > 0) {
      Serial.printf("[Commands] Poll returned unexpected HTTP status: %d\n", httpCode);
    } else {
      Serial.printf("[Commands] HTTPS connection failure during poll: %s (code %d)\n", http.errorToString(httpCode).c_str(), httpCode);
    }
    http.end();
  } else {
    Serial.println("[Commands] HTTPS connection failure: Unable to establish TLS connection to poll endpoint.");
  }
}

void cloudSyncTask(void* pvParameters) {
  Serial.println("[FreeRTOS] CloudSyncTask started execution on Core 0.");

  TankTelemetry localTelemetry;
  unsigned long lastSendTime = 0;
  unsigned long lastCommandPoll = 0;
  const unsigned long MIN_SEND_INTERVAL_MS = 2000;  // Throttle telemetry upload to min 2s
  const unsigned long COMMAND_POLL_INTERVAL_MS = 3000; // Poll commands every 3s

  for (;;) {
    // Wait for 5-second periodic timer OR task notification (immediate state trigger)
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(5000));

    unsigned long now = millis();

    // Check Wi-Fi connectivity non-blockingly
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[Cloud] Wi-Fi disconnected. Attempting reconnect...");
      WiFi.reconnect();
      vTaskDelay(pdMS_TO_TICKS(3000));
      continue;
    }

    // 1. Ensure NTP time is synchronized for TLS certificate validation
    if (time(nullptr) < 1000000000) {
      Serial.println("[Cloud] Synchronizing NTP time for TLS validation...");
      int retries = 0;
      while (time(nullptr) < 1000000000 && retries++ < 20) {
        vTaskDelay(pdMS_TO_TICKS(250));
      }
    }

    // 2. Poll for pending remote commands from cloud
    if (now - lastCommandPoll >= COMMAND_POLL_INTERVAL_MS) {
      pollPendingCloudCommands();
      lastCommandPoll = millis();
    }

    // 3. Throttle consecutive telemetry sends
    if (now - lastSendTime < MIN_SEND_INTERVAL_MS) {
      vTaskDelay(pdMS_TO_TICKS(MIN_SEND_INTERVAL_MS - (now - lastSendTime)));
    }

    // Safely copy current telemetry snapshot under mutex
    bool hasData = false;
    if (telemetryMutex != NULL && xSemaphoreTake(telemetryMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      localTelemetry = sharedTelemetry;
      hasData = true;
      xSemaphoreGive(telemetryMutex);
    }

    if (!hasData) {
      continue;
    }

    // Construct JSON payload matching FastAPI WaterReadingCreate schema
    String payload = "{";
    payload += "\"water_level\":" + String(localTelemetry.waterLevel) + ",";
    payload += "\"probe_25\":" + String(localTelemetry.probe25 ? "true" : "false") + ",";
    payload += "\"probe_50\":" + String(localTelemetry.probe50 ? "true" : "false") + ",";
    payload += "\"probe_75\":" + String(localTelemetry.probe75 ? "true" : "false") + ",";
    payload += "\"probe_100\":" + String(localTelemetry.probe100 ? "true" : "false") + ",";
    payload += "\"alarm\":" + String(localTelemetry.alarm ? "true" : "false") + ",";
    payload += "\"muted\":" + String(localTelemetry.muted ? "true" : "false");
    payload += "}";

    // Perform HTTPS POST
    WiFiClientSecure client;
    client.setCACert(rootCACertificate);
    client.setTimeout(8);

    HTTPClient http;
    http.setTimeout(8000);

    if (http.begin(client, cloudEndpoint)) {
      http.addHeader("Content-Type", "application/json");
      #ifdef SECRETS_H
      if (String(deviceApiKey).length() > 0) {
        http.addHeader("X-Device-Key", deviceApiKey);
      }
      #endif

      int httpCode = http.POST(payload);
      if (httpCode == HTTP_CODE_CREATED || httpCode == HTTP_CODE_OK) {
        // Success: Telemetry successfully persisted
      } else if (httpCode == 401 || httpCode == 403) {
        Serial.printf("[Cloud] Telemetry authentication failure (HTTP %d): Check deviceApiKey.\n", httpCode);
      } else if (httpCode >= 500) {
        Serial.printf("[Cloud] Telemetry server error (HTTP %d): Backend service or database issue.\n", httpCode);
      } else if (httpCode > 0) {
        Serial.printf("[Cloud] Warning: Server returned non-2xx status (%d)\n", httpCode);
      } else {
        Serial.printf("[Cloud] HTTPS connection failure during telemetry upload: %s (code %d)\n", http.errorToString(httpCode).c_str(), httpCode);
      }
      http.end();
    } else {
      Serial.println("[Cloud] Error: Unable to establish TLS connection to telemetry endpoint.");
    }

    lastSendTime = millis();
  }
}

// =====================================================
//  Setup / Loop
// =====================================================
void setup() {
  Serial.begin(115200);

  // Initialize mutex for thread-safe telemetry sharing
  telemetryMutex = xSemaphoreCreateMutex();

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
  updateTelemetrySnapshot(false);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("Local Dashboard URL: http://");
  Serial.println(WiFi.localIP());

  // Configure NTP time synchronization for accurate TLS certificate validation
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  server.on("/", handleRoot);
  server.on("/level", handleLevelJSON);
  server.on("/mute", HTTP_POST, handleMute);
  server.begin();

  // Launch FreeRTOS background task on Core 0 for non-blocking cloud HTTPS communication & command polling
  BaseType_t taskStatus = xTaskCreatePinnedToCore(
    cloudSyncTask,      // Task function
    "CloudSyncTask",    // Task name
    10240,              // Stack depth (bytes, sufficient for TLS handshake)
    NULL,               // Parameters
    1,                  // Task priority
    &cloudTaskHandle,   // Task handle
    0                   // Pin to Core 0 (main Arduino loop runs on Core 1)
  );

  if (taskStatus == pdPASS && cloudTaskHandle != NULL) {
    Serial.println("[FreeRTOS] CloudSyncTask created successfully on Core 0.");
    xTaskNotifyGive(cloudTaskHandle);
  } else {
    Serial.printf("[FreeRTOS] ERROR: Failed to create CloudSyncTask (return code: %d)!\n", (int)taskStatus);
  }
}

void loop() {
  server.handleClient();  // runs every pass, so the local page stays responsive

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
        buzzerMuted = false;  // new level, so re-arm the alarm automatically!
        candidate = -1;
        candidateCount = 0;
        updateTelemetrySnapshot(true);  // Confirmed level change: trigger immediate cloud sync
      }
    } else {
      candidate = reading;
      candidateCount = 1;
    }

    // Drive actual physical buzzer on GPIO 23
    digitalWrite(buzzerPin, (!buzzerMuted && alarmActive()) ? HIGH : LOW);
    updateTelemetrySnapshot(false);
  }

  updateLEDs(level);  // every pass, so the 100% blink stays smooth

  // Serial log once per second
  if (now - lastPrint >= 1000) {
    lastPrint = now;
    Serial.print("Pins [25%:");  Serial.print(digitalRead(wire25)  == LOW ? "FILLED" : "EMPTY");
    Serial.print(" | 50%:");     Serial.print(digitalRead(wire50)  == LOW ? "FILLED" : "EMPTY");
    Serial.print(" | 75%:");     Serial.print(digitalRead(wire75)  == LOW ? "FILLED" : "EMPTY");
    Serial.print(" | 100%:");    Serial.print(digitalRead(wire100) == LOW ? "FILLED" : "EMPTY");
    Serial.print("] => Level: "); Serial.print(level);
    Serial.print("% | Alarm: "); Serial.print(alarmActive() ? "YES" : "NO");
    Serial.print(" | Muted: "); Serial.println(buzzerMuted ? "YES" : "NO");
  }
}
