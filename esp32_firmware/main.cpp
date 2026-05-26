/*
 * ESP32 Gateway Firmware — sortingStation6
 *
 * Chức năng:
 *   - Đọc temperature từ DS18B20 (OneWire)
 *   - Nhận JSON telemetry từ Python bridge qua Serial (USB)
 *   - Forward lên ThingsBoard qua HTTP (WiFi)
 *   - Nhận RPC từ ThingsBoard qua MQTT → gửi lại Python bridge qua Serial
 *
 * Protocol:
 *   Serial IN  (từ Python): JSON line, ví dụ: {"type":"telemetry","data":{...}}
 *   Serial OUT (đến Python): JSON line, ví dụ: {"type":"rpc","method":"setConveyor","params":{"run":true}}
 *
 * Board: ESP32 DevKit V1
 * Baudrate: 115200
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ── Config (từ platformio.ini build_flags hoặc hardcode) ─────────────────────
#ifndef WIFI_SSID
  #define WIFI_SSID       "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
  #define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"
#endif
#ifndef TB_HOST
  #define TB_HOST         "your-thingsboard-host"
#endif
#ifndef TB_HTTP_PORT
  #define TB_HTTP_PORT    58090
#endif
#ifndef TB_ACCESS_TOKEN
  #define TB_ACCESS_TOKEN "YOUR_DEVICE_TOKEN"
#endif

#define ONE_WIRE_PIN     4
#define SERIAL_BAUD      115200
#define TEMP_READ_MS     5000   // Đọc nhiệt độ mỗi 5 giây
#define HTTP_TIMEOUT_MS  5000

// ── Instances ────────────────────────────────────────────────────────────────
OneWire           oneWire(ONE_WIRE_PIN);
DallasTemperature tempSensor(&oneWire);
WiFiClient        wifiClient;
PubSubClient      mqttClient(wifiClient);

// ── State ────────────────────────────────────────────────────────────────────
float         lastTemperature  = 0.0f;
bool          mqttAvailable    = false;
unsigned long lastTempRead     = 0;
String        serialBuffer     = "";

// ── Function declarations ────────────────────────────────────────────────────
void     connectWiFi();
bool     connectMQTT();
void     mqttCallback(char* topic, byte* payload, unsigned int length);
bool     sendTelemetryHTTP(const String& jsonBody);
void     readTemperature();
void     processSerial();

// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(100);

  tempSensor.begin();
  connectWiFi();

  mqttClient.setServer(TB_HOST, 1883);
  mqttClient.setCallback(mqttCallback);
  mqttAvailable = connectMQTT();
}

void loop() {
  // WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // MQTT reconnect (non-blocking — no retry loop here)
  if (mqttAvailable) {
    if (!mqttClient.connected()) {
      mqttAvailable = connectMQTT();
    } else {
      mqttClient.loop();
    }
  }

  readTemperature();
  processSerial();
}

// ═════════════════════════════════════════════════════════════════════════════
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 20) {
    delay(500);
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    // Send status to Python bridge
    Serial.println("{\"type\":\"status\",\"wifi\":true,\"ip\":\"" + WiFi.localIP().toString() + "\"}");
  }
}

bool connectMQTT() {
  if (mqttClient.connect("esp32_gateway", TB_ACCESS_TOKEN, nullptr)) {
    mqttClient.subscribe("v1/devices/me/rpc/request/+");
    return true;
  }
  return false;
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Parse incoming RPC from ThingsBoard
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;

  const char* method = doc["method"] | "unknown";
  JsonObject params = doc["params"];

  // Extract request_id from topic: v1/devices/me/rpc/request/<id>
  String topicStr(topic);
  int lastSlash = topicStr.lastIndexOf('/');
  String requestId = topicStr.substring(lastSlash + 1);

  // Forward to Python bridge via Serial
  JsonDocument out;
  out["type"]       = "rpc";
  out["method"]     = method;
  out["params"]     = params;
  out["request_id"] = requestId;

  String outStr;
  serializeJson(out, outStr);
  Serial.println(outStr);
}

void readTemperature() {
  if (millis() - lastTempRead < TEMP_READ_MS) return;
  lastTempRead = millis();

  tempSensor.requestTemperatures();
  float t = tempSensor.getTempCByIndex(0);
  if (t != DEVICE_DISCONNECTED_C) {
    lastTemperature = t;
  }
}

void processSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (serialBuffer.length() > 0) {
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, serialBuffer);
        if (err == DeserializationError::Ok) {
          const char* type = doc["type"] | "";

          if (strcmp(type, "telemetry") == 0) {
            // Inject temperature and MQTT status into telemetry
            JsonObject data = doc["data"];
            data["temperature_c"]     = lastTemperature;
            data["mqtt_rpc_available"] = mqttAvailable && mqttClient.connected();

            String body;
            serializeJson(data, body);
            sendTelemetryHTTP(body);
          }
        }
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
      // Prevent buffer overflow
      if (serialBuffer.length() > 1024) {
        serialBuffer = "";
      }
    }
  }
}

bool sendTelemetryHTTP(const String& jsonBody) {
  HTTPClient http;

  String url = "http://";
  url += TB_HOST;
  url += ":";
  url += String(TB_HTTP_PORT);
  url += "/api/v1/";
  url += TB_ACCESS_TOKEN;
  url += "/telemetry";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);

  int code = http.POST(jsonBody);
  http.end();
  return (code == 200);
}
