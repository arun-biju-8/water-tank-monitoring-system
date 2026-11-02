#ifndef SECRETS_H
#define SECRETS_H

// Wi-Fi Credentials placeholder
// Copy this file to secrets.h and replace with your actual Wi-Fi credentials.
const char* ssid     = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// Hardware Device Key for bidirectional cloud authentication
// Matches ESP32_API_KEY environment variable configured on Render backend.
const char* deviceApiKey = "YOUR_ESP32_DEVICE_API_KEY";

#endif // SECRETS_H
