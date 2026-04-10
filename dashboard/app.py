#!/usr/bin/env python3
"""
Smart Plant Pot - Dashboard Server
Flask API + Web Dashboard for monitoring and control
"""

from flask import Flask, render_template_string, request, jsonify
import sqlite3
import json
import datetime
from datetime import datetime as dt
import threading
import time

app = Flask(__name__)
DB_FILE = '/home/clawdney/.openclaw/workspace/smart-plant-pot/data.db'

# ============== DATABASE ==============
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,
        name TEXT,
        type TEXT,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        event_type TEXT,
        soil_moisture INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(device_id) REFERENCES devices(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        enabled BOOLEAN,
        hour INTEGER,
        minute INTEGER,
        duration INTEGER,
        FOREIGN KEY(device_id) REFERENCES devices(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        device_id TEXT PRIMARY KEY,
        auto_watering BOOLEAN DEFAULT 1,
        moisture_threshold INTEGER DEFAULT 30,
        pump_duration INTEGER DEFAULT 5,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

# ============== ROUTES ==============
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/devices/register', methods=['POST'])
def register_device():
    data = request.json
    device_id = data.get('deviceId')
    device_type = data.get('type', 'unknown')
    name = data.get('name', device_id)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('INSERT OR REPLACE INTO devices (id, name, type) VALUES (?, ?, ?)',
              (device_id, name, device_type))
    
    # Create default settings
    c.execute('INSERT OR IGNORE INTO settings (device_id) VALUES (?)', (device_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'ok'})

@app.route('/api/devices/<device_id>/event', methods=['POST'])
def device_event(device_id):
    data = request.json
    event_type = data.get('event')
    soil_moisture = data.get('soilMoisture', 0)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('INSERT INTO events (device_id, event_type, soil_moisture) VALUES (?, ?, ?)',
              (device_id, event_type, soil_moisture))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'ok'})

@app.route('/api/devices/<device_id>/status', methods=['POST'])
def update_status(device_id):
    data = request.json
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO settings 
                 (device_id, auto_watering, moisture_threshold, pump_duration, last_updated)
                 VALUES (?, ?, ?, ?, ?)''',
              (device_id,
               data.get('autoWatering', True),
               data.get('moistureThreshold', 30),
               data.get('pumpDuration', 5),
               datetime.datetime.now()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'ok'})

@app.route('/api/devices')
def list_devices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, name, type, registered_at FROM devices')
    devices = [{'id': row[0], 'name': row[1], 'type': row[2], 'registered_at': row[3]} 
               for row in c.fetchall()]
    conn.close()
    return jsonify(devices)

@app.route('/api/devices/<device_id>/events')
def get_events(device_id):
    limit = request.args.get('limit', 50)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT event_type, soil_moisture, timestamp 
                 FROM events WHERE device_id = ? 
                 ORDER BY timestamp DESC LIMIT ?''', (device_id, limit))
    events = [{'type': row[0], 'soil_moisture': row[1], 'timestamp': row[2]} 
              for row in c.fetchall()]
    conn.close()
    return jsonify(events)

@app.route('/api/devices/<device_id>/settings')
def get_settings(device_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT auto_watering, moisture_threshold, pump_duration, last_updated 
                 FROM settings WHERE device_id = ?''', (device_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'auto_watering': bool(row[0]),
            'moisture_threshold': row[1],
            'pump_duration': row[2],
            'last_updated': row[3]
        })
    return jsonify({})

@app.route('/api/devices/<device_id>/command', methods=['POST'])
def send_command(device_id):
    # This would publish to MQTT in production
    # For now, just acknowledge
    return jsonify({'status': 'ok', 'message': 'Command sent to device'})

@app.route('/api/schedule', methods=['GET', 'POST'])
def manage_schedule():
    device_id = request.args.get('device_id', 'plant-pot-default')
    
    if request.method == 'POST':
        data = request.json
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO schedules 
                     (device_id, enabled, hour, minute, duration)
                     VALUES (?, ?, ?, ?, ?)''',
                  (device_id,
                   data.get('enabled', False),
                   data.get('hour', 8),
                   data.get('minute', 0),
                   data.get('duration', 5)))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'ok'})
    
    # GET
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT enabled, hour, minute, duration 
                 FROM schedules WHERE device_id = ?''', (device_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'enabled': bool(row[0]),
            'hour': row[1],
            'minute': row[2],
            'duration': row[3]
        })
    return jsonify({'enabled': False, 'hour': 8, 'minute': 0, 'duration': 5})

# ============== HTML TEMPLATE ==============
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Plant Pot</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
               min-height: 100vh; color: #fff; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { text-align: center; margin-bottom: 30px; font-size: 2.5rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px; margin-bottom: 30px; }
        .card { background: rgba(255,255,255,0.1); border-radius: 15px; padding: 20px;
                backdrop-filter: blur(10px); }
        .card h2 { margin-bottom: 15px; color: #4ade80; font-size: 1.2rem; }
        .stat { font-size: 3rem; font-weight: bold; text-align: center; margin: 20px 0; }
        .stat-label { text-align: center; opacity: 0.7; }
        .gauge { width: 100%; height: 20px; background: #333; border-radius: 10px; overflow: hidden; }
        .gauge-fill { height: 100%; background: linear-gradient(90deg, #4ade80, #22c55e); 
                      transition: width 0.5s ease; }
        .gauge-fill.dry { background: linear-gradient(90deg, #f59e0b, #ef4444); }
        .controls { display: grid; gap: 15px; }
        .btn { padding: 15px 30px; border: none; border-radius: 10px; cursor: pointer;
               font-size: 1rem; font-weight: bold; transition: all 0.3s; }
        .btn-primary { background: #4ade80; color: #1a1a2e; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(74,222,128,0.4); }
        .btn-danger { background: #ef4444; color: white; }
        .btn-danger:hover { transform: translateY(-2px); }
        .switch { position: relative; display: inline-block; width: 60px; height: 34px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
                  background: #333; transition: .4s; border-radius: 34px; }
        .slider:before { position: absolute; content: ""; height: 26px; width: 26px;
                         left: 4px; bottom: 4px; background: white; transition: .4s;
                         border-radius: 50%; }
        input:checked + .slider { background: #4ade80; }
        input:checked + .slider:before { transform: translateX(26px); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; opacity: 0.8; }
        .form-group input, .form-group select { width: 100%; padding: 12px; border-radius: 8px;
                                                border: none; background: rgba(255,255,255,0.1);
                                                color: white; font-size: 1rem; }
        .events { max-height: 300px; overflow-y: auto; }
        .event { padding: 10px; margin-bottom: 5px; background: rgba(0,0,0,0.2); 
                 border-radius: 5px; font-size: 0.9rem; }
        .event-time { opacity: 0.5; font-size: 0.8rem; }
        .status-indicator { display: inline-block; width: 10px; height: 10px; 
                            border-radius: 50%; margin-right: 10px; }
        .status-on { background: #4ade80; box-shadow: 0 0 10px #4ade80; }
        .status-off { background: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌱 Smart Plant Pot</h1>
        
        <div class="grid">
            <div class="card">
                <h2>💧 Soil Moisture</h2>
                <div class="stat" id="moistureValue">--%</div>
                <div class="gauge">
                    <div class="gauge-fill" id="moistureGauge" style="width: 0%"></div>
                </div>
                <div class="stat-label">Current Reading</div>
            </div>
            
            <div class="card">
                <h2>💦 Pump Status</h2>
                <div class="stat">
                    <span class="status-indicator" id="pumpIndicator"></span>
                    <span id="pumpStatus">OFF</span>
                </div>
                <div class="stat-label">Water Pump</div>
            </div>
            
            <div class="card">
                <h2>⚙️ Controls</h2>
                <div class="controls">
                    <button class="btn btn-primary" onclick="startPump()">Start Pump</button>
                    <button class="btn btn-danger" onclick="stopPump()">Stop Pump</button>
                </div>
            </div>
            
            <div class="card">
                <h2>🔧 Settings</h2>
                <div class="form-group">
                    <label>Auto Watering</label>
                    <label class="switch">
                        <input type="checkbox" id="autoWatering" checked onchange="updateSettings()">
                        <span class="slider"></span>
                    </label>
                </div>
                <div class="form-group">
                    <label>Moisture Threshold (%)</label>
                    <input type="number" id="threshold" value="30" min="0" max="100" onchange="updateSettings()">
                </div>
                <div class="form-group">
                    <label>Pump Duration (seconds)</label>
                    <input type="number" id="duration" value="5" min="1" max="60" onchange="updateSettings()">
                </div>
            </div>
            
            <div class="card">
                <h2>📅 Schedule</h2>
                <div class="form-group">
                    <label>Enable Schedule</label>
                    <label class="switch">
                        <input type="checkbox" id="scheduleEnabled" onchange="updateSchedule()">
                        <span class="slider"></span>
                    </label>
                </div>
                <div class="form-group">
                    <label>Time</label>
                    <input type="time" id="scheduleTime" value="08:00" onchange="updateSchedule()">
                </div>
                <div class="form-group">
                    <label>Duration (seconds)</label>
                    <input type="number" id="scheduleDuration" value="5" min="1" max="60" onchange="updateSchedule()">
                </div>
            </div>
            
            <div class="card">
                <h2>📊 Recent Events</h2>
                <div class="events" id="eventsList"></div>
            </div>
        </div>
    </div>
    
    <script>
        const deviceId = 'plant-pot-default';
        
        async function fetchStatus() {
            try {
                const response = await fetch(`/api/devices/${deviceId}/events?limit=10`);
                const events = await response.json();
                
                if (events.length > 0) {
                    const latest = events[0];
                    updateMoisture(latest.soil_moisture || 50);
                }
                
                updateEventsList(events);
            } catch (e) {
                console.error('Error fetching status:', e);
            }
        }
        
        function updateMoisture(value) {
            document.getElementById('moistureValue').textContent = value + '%';
            const gauge = document.getElementById('moistureGauge');
            gauge.style.width = value + '%';
            
            if (value > 70) {
                gauge.classList.add('dry');
            } else {
                gauge.classList.remove('dry');
            }
        }
        
        function updateEventsList(events) {
            const list = document.getElementById('eventsList');
            list.innerHTML = events.map(e => `
                <div class="event">
                    <strong>${e.type}</strong> - ${e.soil_moisture}%
                    <div class="event-time">${e.timestamp}</div>
                </div>
            `).join('');
        }
        
        async function startPump() {
            await fetch('/api/devices/' + deviceId + '/command', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({pump: true})
            });
            document.getElementById('pumpIndicator').classList.add('status-on');
            document.getElementById('pumpStatus').textContent = 'ON';
        }
        
        async function stopPump() {
            await fetch('/api/devices/' + deviceId + '/command', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({pump: false})
            });
            document.getElementById('pumpIndicator').classList.remove('status-on');
            document.getElementById('pumpStatus').textContent = 'OFF';
        }
        
        async function updateSettings() {
            const data = {
                autoWatering: document.getElementById('autoWatering').checked,
                moistureThreshold: parseInt(document.getElementById('threshold').value),
                pumpDuration: parseInt(document.getElementById('duration').value)
            };
            
            await fetch('/api/devices/' + deviceId + '/status', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
        }
        
        async function updateSchedule() {
            const time = document.getElementById('scheduleTime').value.split(':');
            const data = {
                enabled: document.getElementById('scheduleEnabled').checked,
                hour: parseInt(time[0]),
                minute: parseInt(time[1]),
                duration: parseInt(document.getElementById('scheduleDuration').value)
            };
            
            await fetch('/api/schedule?device_id=' + deviceId, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
        }
        
        // Initialize
        fetchStatus();
        setInterval(fetchStatus, 10000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    init_db()
    print("🌱 Smart Plant Pot Dashboard starting on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)