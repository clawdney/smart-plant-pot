#!/usr/bin/env python3
"""
Smart Plant Pot - MQTT Bridge
Receives data from ESP8266 and forwards to dashboard
Also sends commands from dashboard to ESP8266
"""

import paho.mqtt.client as mqtt
import json
import sqlite3
import os

DB_FILE = '/home/clawdney/.openclaw/workspace/smart-plant-pot/data.db'
MQTT_BROKER = '192.168.178.158'
MQTT_PORT = 1883
MQTT_STATUS_TOPIC = 'smart-plant-pot/status'
MQTT_COMMAND_TOPIC = 'smart-plant-pot/command'

def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        soil_moisture INTEGER,
        pump_on BOOLEAN,
        wifi_rssi INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def save_reading(device_id, soil_moisture, pump_on, wifi_rssi):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO readings (device_id, soil_moisture, pump_on, wifi_rssi)
                 VALUES (?, ?, ?, ?)''',
              (device_id, soil_moisture, pump_on, wifi_rssi))
    conn.commit()
    conn.close()

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")
    client.subscribe(MQTT_STATUS_TOPIC)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        print(f"Received: {data}")
        
        device_id = data.get('deviceId', 'unknown')
        soil_moisture = data.get('soilMoisture', 0)
        pump_on = data.get('pumpOn', False)
        wifi_rssi = data.get('wifiRssi', 0)
        
        save_reading(device_id, soil_moisture, pump_on, wifi_rssi)
        
    except Exception as e:
        print(f"Error processing message: {e}")

def send_command(command):
    """Send command to ESP8266"""
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.publish(MQTT_COMMAND_TOPIC, json.dumps(command))
    client.disconnect()
    print(f"Sent command: {command}")

def main():
    init_db()
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    print(f"Starting MQTT bridge on {MQTT_BROKER}:{MQTT_PORT}...")
    client.loop_forever()

if __name__ == '__main__':
    main()