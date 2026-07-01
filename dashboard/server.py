import sys
import os
import time
import json
import sqlite3
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import random

# Configurations
DB_PATH = os.environ.get("DB_PATH", "/data/history.db")
PICO_UPS_URL = os.environ.get("PICO_UPS_URL", "")
PORT = int(os.environ.get("PORT", "8080"))
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

if not PICO_UPS_URL or PICO_UPS_URL.strip() == "":
    PICO_UPS_URL = None

def seed_demo_history():
    """Seeds the SQLite database with 100 points of realistic historical cycle data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if we already have data
    cursor.execute("SELECT COUNT(*) FROM ups_history")
    count = cursor.fetchone()[0]
    if count > 0:
        conn.close()
        return
        
    print("[Backend] Seeding SQLite database with 100 historical demo points...", flush=True)
    
    now = time.time()
    for i in range(100):
        t_offset = (100 - i) * 15  # 15 second intervals
        point_time = now - t_offset
        
        # 1200-second cycle:
        # 0 to 600s: Grid up, 600s to 1200s: Blackout!
        cycle = int(point_time) % 1200
        is_grid_up = (cycle < 600)
        
        if is_grid_up:
            grid_v = round(230.2 + random.uniform(-1.0, 1.0), 1)
            # battery charges from 25.0V up to 27.6V
            charge_progress = min(300, cycle)
            bat_v = round(25.0 + (charge_progress * 0.0087), 2)
            load_c = round(1.45 + random.uniform(-0.05, 0.05), 2)
        else:
            grid_v = 0.0
            discharge_elapsed = cycle - 600
            # battery discharges down to 23.8V
            bat_v = round(25.0 - (discharge_elapsed * 0.002), 2)
            load_c = round(3.5 + random.uniform(-0.1, 0.1), 2)
            
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(point_time))
        cursor.execute(
            "INSERT INTO ups_history (timestamp, battery_voltage, grid_voltage, load_current) VALUES (?, ?, ?, ?)",
            (timestamp_str, bat_v, grid_v, load_c)
        )
        
    conn.commit()
    conn.close()
    print("[Backend] Database seeding completed.", flush=True)

# Ensure database directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def init_db():
    """Initializes the SQLite schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ups_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            battery_voltage REAL,
            grid_voltage REAL,
            load_current REAL
        )
    """)
    conn.commit()
    conn.close()
    print(f"[Backend] Database initialized at: {DB_PATH}")

def start_udp_discovery():
    """Listens for UDP broadcast beacons from the Pico board to auto-discover its IP address."""
    import socket
    
    def discovery_worker():
        global PICO_UPS_URL
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('', 5555))
            print("[Discovery] Listening for Pico discovery beacons on UDP port 5555...", flush=True)
        except Exception as e:
            print(f"[Discovery] Failed to bind UDP discovery port: {e}", flush=True)
            return

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                payload = json.loads(data.decode('utf-8'))
                if payload.get("device") == "smart_ups":
                    new_ip = payload.get("ip")
                    new_url = f"http://{new_ip}"
                    if PICO_UPS_URL != new_url:
                         print(f"[Discovery] Auto-discovered Smart UPS board at {new_url}", flush=True)
                         PICO_UPS_URL = new_url
            except Exception as e:
                time.sleep(1)

    threading.Thread(target=discovery_worker, daemon=True).start()

def polling_loop():
    """Background polling loop that pulls telemetry from the Pico and stores it in SQLite."""
    print("[Backend] Starting background telemetry logger...")
    while True:
        if DEMO_MODE:
            # Generate dynamic telemetry data for SQLite history logging
            cycle = int(time.time()) % 120
            is_grid_up = (cycle < 60)
            if is_grid_up:
                grid_voltage = round(230.2 + random.uniform(-1.5, 1.5), 1)
                battery_voltage = 27.60
                load_current = round(1.45 + random.uniform(-0.05, 0.05), 2)
            else:
                grid_voltage = 0.0
                discharge_elapsed = cycle - 60
                battery_voltage = round(25.0 - (discharge_elapsed * 0.075), 2)
                load_current = round(3.5 + random.uniform(-0.1, 0.1), 2)
                
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO ups_history (battery_voltage, grid_voltage, load_current) VALUES (?, ?, ?)",
                    (battery_voltage, grid_voltage, load_current)
                )
                cursor.execute("DELETE FROM ups_history WHERE timestamp < datetime('now', '-24 hours')")
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[Backend] Demo poll insert failed: {e}")
                
        else:
            if not PICO_UPS_URL:
                time.sleep(2)
                continue
                
            try:
                req = urllib.request.Request(f"{PICO_UPS_URL}/api/status")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                # Extract readings
                battery_voltage = data.get("battery_voltage", 0.0)
                grid_voltage = data.get("grid_voltage", 0.0)
                load_current = data.get("load_current", 0.0)
                
                # Save to SQLite
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO ups_history (battery_voltage, grid_voltage, load_current) VALUES (?, ?, ?)",
                    (battery_voltage, grid_voltage, load_current)
                )
                # Prune logs older than 24 hours to keep the database size lightweight
                cursor.execute("DELETE FROM ups_history WHERE timestamp < datetime('now', '-24 hours')")
                conn.commit()
                conn.close()
                
            except Exception as e:
                # Print warnings occasionally but continue running
                print(f"[Backend] Background poll failed: {e}")
            
        # Poll every 10 seconds for historical logs
        time.sleep(10)

class DashboardHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stdout.write(f"[Server] {format % args}\n")

    def end_headers(self):
        # Enable CORS for direct queries
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = parsed_url.query

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            with open(index_path, "rb") as f:
                self.wfile.write(f.read())
                
        elif path == "/api/status":
            if DEMO_MODE:
                # Generate dynamic realistic telemetry data for demo mode
                cycle = int(time.time()) % 120
                is_grid_up = (cycle < 60)
                
                battery_voltage = 27.60 if is_grid_up else round(25.0 - ((cycle - 60) * 0.075), 2)
                
                telemetry = {
                    "ac_ok": is_grid_up,
                    "bat_sw_off": False,
                    "bat_nc": False,
                    "discharge_olp": False,
                    "bat_uvp": False if is_grid_up else (cycle >= 110),
                    "lad_power_supply": is_grid_up,
                    "link_ctrl": False,
                    "bat_ovp": False,
                    "bat_no_balance": False,
                    "bat_error_1": False,
                    "bat_error_2": False,
                    "bat_error_3": False,
                    "bat_error_4": False,
                    "bat_chgfull": is_grid_up and (cycle >= 25),
                    "bat_chging": is_grid_up and (cycle < 25),
                    "bat_rev": False,
                    "force_status": False,
                    "grid_voltage": round(230.2 + random.uniform(-1.5, 1.5), 1) if is_grid_up else 0.0,
                    "load_current": round(1.45 + random.uniform(-0.05, 0.05), 2) if is_grid_up else round(3.5 + random.uniform(-0.1, 0.1), 2),
                    "battery_voltage": battery_voltage,
                    "cell1_voltage": round(battery_voltage / 2.0, 2),
                    "cell2_voltage": round(battery_voltage / 2.0, 2),
                    "uvp_threshold": 21.5,
                    "last_update": int(time.time())
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(telemetry).encode('utf-8'))
                return

            if not PICO_UPS_URL:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Smart UPS board not discovered yet. Waiting for UDP beacon..."}).encode('utf-8'))
                return
            # Proxy status request to Pico
            try:
                req = urllib.request.Request(f"{PICO_UPS_URL}/api/status")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(resp.read())
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Failed to reach device: {e}"}).encode('utf-8'))
                
        elif path == "/api/control":
            if DEMO_MODE:
                # Return success for all control commands in demo mode
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
                return

            if not PICO_UPS_URL:
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Smart UPS board not discovered yet. Waiting for UDP beacon..."}).encode('utf-8'))
                return
            # Proxy control command to Pico
            try:
                url = f"{PICO_UPS_URL}/api/control?{query}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(resp.read())
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Failed to control device: {e}"}).encode('utf-8'))
                
        elif path == "/api/history":
            # Retrieve historical logs from SQLite
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                # Select only the last 1440 points (approx 4 hours at 10s intervals, or 24 hours if polled less frequently)
                cursor.execute("""
                    SELECT strftime('%H:%M:%S', datetime(timestamp, 'localtime')), battery_voltage, grid_voltage, load_current 
                    FROM ups_history 
                    ORDER BY id DESC LIMIT 100
                """)
                rows = cursor.fetchall()
                conn.close()
                
                # Reverse to sort ascending for Chart.js timeline
                rows.reverse()
                
                history_data = []
                for row in rows:
                    history_data.append({
                        "time": row[0],
                        "battery_voltage": row[1],
                        "grid_voltage": row[2],
                        "load_current": row[3]
                    })
                    
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(history_data).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def start_server():
    init_db()
    
    if DEMO_MODE:
        seed_demo_history()
    
    # Start UDP discovery listener
    start_udp_discovery()
    
    # Start background polling loop
    poll_thread = threading.Thread(target=polling_loop, daemon=True)
    poll_thread.start()
    
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, DashboardHandler)
    print(f"[Backend] Server listening on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Backend] Shutting down.")
        httpd.server_close()

if __name__ == '__main__':
    start_server()
