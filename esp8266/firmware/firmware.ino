/**
 * Smart Plant Pot - ESP8266 Firmware
 * Soil Sensor + Relay Control + WiFi Manager + MQTT
 * 
 * Hardware:
 * - ESP8266 (NodeMCU)
 * - Soil moisture sensor (analog)
 * - 5V Relay module (for water pump)
 * - DHT22 (temperature/humidity - optional)
 * 
 * Connections:
 * - A0: Soil moisture sensor
 * - D1: Relay pin
 * - D2: DHT22 (optional)
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP8266HTTPClient.h>

// ============== CONFIGURATION ==============
// WiFi credentials - will be configured via WiFiManager if these don't work
const char* default_ssid = "YourWiFiSSID";
const char* default_password = "YourWiFiPassword";

// MQTT Server
const char* mqtt_server = "192.168.178.158";
const char* mqtt_topic = "smart-plant-pot/status";

// API Server for dashboard
const char* api_server = "http://192.168.178.158:5000";

// Pin definitions
const int SOIL_SENSOR_PIN = A0;
const int RELAY_PIN = D1;
const int LED_PIN = LED_BUILTIN;

// ============== VARIABLES ==============
WiFiClient espClient;
PubSubClient mqttClient(espClient);

String deviceId;
int soilMoisture = 0;
bool pumpOn = false;
bool autoWatering = true;
int moistureThreshold = 30; // Water when below this %
int pumpDuration = 5; // seconds
unsigned long lastSensorRead = 0;
unsigned long lastPumpRun = 0;
unsigned long pumpStartTime = 0;

// Schedule
bool scheduleEnabled = false;
int scheduleHour = 8; // 8 AM
int scheduleMinute = 0;

// ============== SETUP ==============
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== Smart Plant Pot Starting ===");
  
  // Generate unique device ID
  deviceId = "plant-pot-" + String(ESP.getChipId(), HEX);
  
  // Configure pins
  pinMode(SOIL_SENSOR_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(LED_PIN, HIGH); // LED off
  
  // Connect to WiFi
  connectWiFi();
  
  // Setup MQTT
  mqttClient.setServer(mqtt_server, 1883);
  mqttClient.setCallback(mqttCallback);
  
  // Register device with API
  registerDevice();
  
  Serial.println("=== Setup Complete ===");
}

void loop() {
  // Reconnect MQTT if needed
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();
  
  unsigned long now = millis();
  
  // Read sensors every 30 seconds
  if (now - lastSensorRead > 30000) {
    readSensors();
    lastSensorRead = now;
  }
  
  // Check auto-watering
  if (autoWatering && soilMoisture < moistureThreshold && !pumpOn) {
    startPump();
  }
  
  // Check schedule
  if (scheduleEnabled) {
    checkSchedule();
  }
  
  // Update MQTT
  if (now - lastSensorRead > 10000) {
    publishStatus();
  }
  
  // Turn off pump after duration
  if (pumpOn && (now - pumpStartTime > (pumpDuration * 1000UL))) {
    stopPump();
  }
  
  delay(100);
}

// ============== WiFi ==============
void connectWiFi() {
  Serial.print("Connecting to WiFi...");
  
  // Try saved credentials first
  WiFi.begin();
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi Failed - starting AP mode");
    startAPMode();
  }
}

void startAPMode() {
  WiFi.softAP("SmartPlantPot", "12345678");
  Serial.println("AP Mode: Connect to WiFi 'SmartPlantPot'");
  Serial.println("Password: 12345678");
  Serial.println("Then configure via web interface");
}

// ============== MQTT ==============
void reconnectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT...");
    if (mqttClient.connect(deviceId.c_str())) {
      Serial.println("MQTT Connected");
      mqttClient.subscribe("smart-plant-pot/command");
    } else {
      Serial.print(" failed, retrying in 5s...");
      delay(5000);
    }
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  Serial.print("MQTT Message: ");
  Serial.println(message);
  
  // Parse JSON command
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, message);
  
  if (!error) {
    if (doc.containsKey("pump")) {
      if (doc["pump"] == true) {
        startPump();
      } else {
        stopPump();
      }
    }
    if (doc.containsKey("autoWatering")) {
      autoWatering = doc["autoWatering"];
    }
    if (doc.containsKey("threshold")) {
      moistureThreshold = doc["threshold"];
    }
    if (doc.containsKey("pumpDuration")) {
      pumpDuration = doc["pumpDuration"];
    }
    if (doc.containsKey("scheduleEnabled")) {
      scheduleEnabled = doc["scheduleEnabled"];
      scheduleHour = doc["scheduleHour"];
      scheduleMinute = doc["scheduleMinute"];
    }
  }
}

void publishStatus() {
  StaticJsonDocument<256> doc;
  doc["deviceId"] = deviceId;
  doc["soilMoisture"] = soilMoisture;
  doc["pumpOn"] = pumpOn;
  doc["autoWatering"] = autoWatering;
  doc["moistureThreshold"] = moistureThreshold;
  doc["pumpDuration"] = pumpDuration;
  doc["scheduleEnabled"] = scheduleEnabled;
  doc["scheduleHour"] = scheduleHour;
  doc["scheduleMinute"] = scheduleMinute;
  doc["wifiRssi"] = WiFi.RSSI();
  doc["uptime"] = millis / 1000;
  
  String output;
  serializeJson(doc, output);
  mqttClient.publish(mqtt_topic, output.c_str());
}

// ============== SENSORS ==============
void readSensors() {
  // Read soil moisture (0-1023, lower = wetter)
  int rawValue = analogRead(SOIL_SENSOR_PIN);
  
  // Convert to percentage (0% = wet, 100% = dry)
  // Note: Different sensors may need calibration
  soilMoisture = map(rawValue, 0, 1023, 100, 0);
  soilMoisture = constrain(soilMoisture, 0, 100);
  
  Serial.print("Soil Moisture: ");
  Serial.println(soilMoisture);
}

// ============== PUMP CONTROL ==============
void startPump() {
  if (!pumpOn) {
    pumpOn = true;
    pumpStartTime = millis();
    digitalWrite(RELAY_PIN, HIGH);
    digitalWrite(LED_PIN, LOW); // LED on
    Serial.println("Pump Started");
    publishStatus();
    sendEvent("pump_started");
  }
}

void stopPump() {
  if (pumpOn) {
    pumpOn = false;
    digitalWrite(RELAY_PIN, LOW);
    digitalWrite(LED_PIN, HIGH); // LED off
    Serial.println("Pump Stopped");
    publishStatus();
    sendEvent("pump_stopped");
  }
}

// ============== SCHEDULE ==============
void checkSchedule() {
  // Simple check - should be improved with actual time sync
  // For now, check every hour
}

// ============== API ==============
void registerDevice() {
  HTTPClient http;
  WiFiClient client;
  
  http.begin(client, String(api_server) + "/api/devices/register");
  http.addHeader("Content-Type", "application/json");
  
  StaticJsonDocument<256> doc;
  doc["deviceId"] = deviceId;
  doc["type"] = "smart-plant-pot";
  doc["name"] = "Smart Plant Pot";
  
  String output;
  serializeJson(doc, output);
  
  int httpCode = http.POST(output);
  Serial.println("Register: " + String(httpCode));
  
  http.end();
}

void sendEvent(const char* event) {
  HTTPClient http;
  WiFiClient client;
  
  http.begin(client, String(api_server) + "/api/devices/" + deviceId + "/event");
  http.addHeader("Content-Type", "application/json");
  
  StaticJsonDocument<128> doc;
  doc["event"] = event;
  doc["soilMoisture"] = soilMoisture;
  
  String output;
  serializeJson(doc, output);
  
  http.POST(output);
  http.end();
}