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

# Shared telemetry cache for throttling network requests to the Pico
latest_telemetry = None
latest_telemetry_time = 0.0
telemetry_lock = threading.Lock()

def seed_demo_history():
    """Seeds the SQLite database with realistic historical cycle data spanning the past 30 days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if we already have data
    cursor.execute("SELECT COUNT(*) FROM ups_history")
    count = cursor.fetchone()[0]
    if count > 0:
        conn.close()
        return
        
    print("[Backend] Seeding SQLite database with historical demo points spanning 30 days...", flush=True)
    
    now = time.time()
    points = []
    
    # Generate points for the past 30 days (hourly)
    for hour_offset in range(720, 24, -1):
        point_time = now - hour_offset * 3600
        points.append(point_time)
        
    # Generate points for the last 24 hours (every 10 minutes)
    for min_offset in range(144, 0, -1):
        point_time = now - min_offset * 600
        points.append(point_time)
        
    for pt in points:
        cycle = int(pt) % 1200
        is_grid_up = (cycle < 600)
        
        if is_grid_up:
            grid_v = round(230.2 + random.uniform(-1.0, 1.0), 1)
            charge_progress = min(300, cycle)
            bat_v = round(25.0 + (charge_progress * 0.0087), 2)
            load_c = round(1.45 + random.uniform(-0.05, 0.05), 2)
        else:
            grid_v = 0.0
            discharge_elapsed = cycle - 600
            bat_v = round(25.0 - (discharge_elapsed * 0.002), 2)
            load_c = round(3.5 + random.uniform(-0.1, 0.1), 2)
            
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(pt))
        c1 = round(bat_v / 2.0 + random.uniform(-0.01, 0.01), 2)
        c2 = round(bat_v - c1, 2)
        cursor.execute(
            "INSERT INTO ups_history (timestamp, battery_voltage, grid_voltage, load_current, cell1_voltage, cell2_voltage, cell3_voltage, cell4_voltage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp_str, bat_v, grid_v, load_c, c1, c2, None, None)
        )
        
    conn.commit()
    conn.close()
    print("[Backend] Database seeding completed.", flush=True)

# Ensure database directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def init_db():
    """Initializes the SQLite schema and migrates columns if necessary."""
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
    
    # Check if cell voltage columns exist, if not, add them
    cursor.execute("PRAGMA table_info(ups_history)")
    columns = [col[1] for col in cursor.fetchall()]
    for i in range(1, 5):
        col_name = f"cell{i}_voltage"
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE ups_history ADD COLUMN {col_name} REAL")
            print(f"[Backend] Migrated: added {col_name} to ups_history", flush=True)
            
    conn.commit()
    conn.close()
    print(f"[Backend] Database initialized at: {DB_PATH}", flush=True)

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
    global latest_telemetry, latest_telemetry_time
    print("[Backend] Starting background telemetry logger...", flush=True)
    
    last_db_write_time = 0.0
    
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
                cell1 = round(battery_voltage / 2.0 + random.uniform(-0.01, 0.01), 2)
                cell2 = round(battery_voltage - cell1, 2)
                cursor.execute(
                    "INSERT INTO ups_history (battery_voltage, grid_voltage, load_current, cell1_voltage, cell2_voltage, cell3_voltage, cell4_voltage) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (battery_voltage, grid_voltage, load_current, cell1, cell2, None, None)
                )
                cursor.execute("DELETE FROM ups_history WHERE timestamp < datetime('now', '-30 days')")
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[Backend] Demo poll insert failed: {e}", flush=True)
            
            time.sleep(10)
            
        else:
            if not PICO_UPS_URL:
                time.sleep(2)
                continue
                
            data = None
            try:
                req = urllib.request.Request(f"{PICO_UPS_URL}/api/status")
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                with telemetry_lock:
                    latest_telemetry = data
                    latest_telemetry_time = time.time()
                
            except Exception as e:
                # Print warnings occasionally but continue running
                print(f"[Backend] Background poll failed: {e}", flush=True)
            
            # Save to SQLite history every 10 seconds to keep database size lightweight
            now_time = time.time()
            if data and (now_time - last_db_write_time >= 10.0):
                try:
                    battery_voltage = data.get("battery_voltage", 0.0)
                    grid_voltage = data.get("grid_voltage", 0.0)
                    load_current = data.get("load_current", 0.0)
                    cell1 = data.get("cell1_voltage")
                    cell2 = data.get("cell2_voltage")
                    cell3 = data.get("cell3_voltage")
                    cell4 = data.get("cell4_voltage")
                    
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO ups_history (battery_voltage, grid_voltage, load_current, cell1_voltage, cell2_voltage, cell3_voltage, cell4_voltage) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (battery_voltage, grid_voltage, load_current, cell1, cell2, cell3, cell4)
                    )
                    cursor.execute("DELETE FROM ups_history WHERE timestamp < datetime('now', '-30 days')")
                    conn.commit()
                    conn.close()
                    last_db_write_time = now_time
                except Exception as db_err:
                    print(f"[Backend] Database write failed: {db_err}", flush=True)
            
            # Fast polling interval to keep cached data fresh for HTTP requests
            time.sleep(1.5)

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

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        
        if path == "/api/clear":
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ups_history")
                conn.commit()
                conn.close()
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Failed to clear history: {e}"}).encode('utf-8'))
                return
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

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
            
            # Return cached data if valid (within 6 seconds)
            with telemetry_lock:
                cache_valid = (latest_telemetry is not None) and (time.time() - latest_telemetry_time < 6.0)
                cached_data = latest_telemetry

            if cache_valid:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(cached_data).encode('utf-8'))
            else:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                time_diff = time.time() - latest_telemetry_time if latest_telemetry else -1
                self.wfile.write(json.dumps({
                    "error": "Device offline (cached telemetry expired)",
                    "last_seen_seconds_ago": time_diff
                }).encode('utf-8'))
                
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

        elif path == "/api/download":
            try:
                params = urllib.parse.parse_qs(query)
                start_param = params.get("start", [None])[0]
                end_param = params.get("end", [None])[0]

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                if start_param and end_param:
                    start_clean = start_param.replace('T', ' ').replace('Z', '')
                    if '.' in start_clean:
                        start_clean = start_clean.split('.')[0]
                    end_clean = end_param.replace('T', ' ').replace('Z', '')
                    if '.' in end_clean:
                        end_clean = end_clean.split('.')[0]

                    cursor.execute("""
                        SELECT timestamp, battery_voltage, grid_voltage, load_current, cell1_voltage, cell2_voltage, cell3_voltage, cell4_voltage
                        FROM ups_history
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY timestamp ASC
                    """, (start_clean, end_clean))
                    filename = "ups_history_range.csv"
                else:
                    cursor.execute("""
                        SELECT timestamp, battery_voltage, grid_voltage, load_current, cell1_voltage, cell2_voltage, cell3_voltage, cell4_voltage
                        FROM ups_history
                        ORDER BY timestamp ASC
                    """)
                    filename = "ups_history_all.csv"

                rows = cursor.fetchall()
                conn.close()

                csv_lines = ["timestamp,battery_voltage,grid_voltage,load_current,cell1_voltage,cell2_voltage,cell3_voltage,cell4_voltage"]
                for row in rows:
                    c1 = row[4] if row[4] is not None else ""
                    c2 = row[5] if row[5] is not None else ""
                    c3 = row[6] if row[6] is not None else ""
                    c4 = row[7] if row[7] is not None else ""
                    csv_lines.append(f"{row[0]},{row[1]},{row[2]},{row[3]},{c1},{c2},{c3},{c4}")
                csv_data = "\n".join(csv_lines).encode('utf-8')

                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(csv_data)))
                self.end_headers()
                self.wfile.write(csv_data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Failed to generate CSV: {e}"}).encode('utf-8'))
                return
                
        elif path == "/api/history":
            try:
                params = urllib.parse.parse_qs(query)
                start_param = params.get("start", [None])[0]
                end_param = params.get("end", [None])[0]

                if start_param:
                    start_param = start_param.replace('T', ' ')
                if end_param:
                    end_param = end_param.replace('T', ' ')

                # Parse start/end datetimes to calculate duration for downsampling
                import datetime as dt
                now_dt = dt.datetime.now()
                s_dt = now_dt - dt.timedelta(hours=24)
                e_dt = now_dt

                if start_param:
                    try:
                        s_dt = dt.datetime.strptime(start_param.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        try:
                            s_dt = dt.datetime.strptime(start_param, "%Y-%m-%d %H:%M")
                        except Exception:
                            pass
                if end_param:
                    try:
                        e_dt = dt.datetime.strptime(end_param.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        try:
                            e_dt = dt.datetime.strptime(end_param, "%Y-%m-%d %H:%M")
                        except Exception:
                            pass

                duration_sec = (e_dt - s_dt).total_seconds()
                # Pick standard downsampling group interval based on duration (UTC timestamp)
                if duration_sec <= 600: # 10 mins
                    group_expr = "strftime('%Y-%m-%d %H:%M:%S', timestamp)"
                elif duration_sec <= 3600 * 2: # 2 hours
                    group_expr = "strftime('%Y-%m-%d %H:%M:', timestamp) || (strftime('%S', timestamp) / 10 * 10)"
                elif duration_sec <= 3600 * 12: # 12 hours
                    group_expr = "strftime('%Y-%m-%d %H:%M', timestamp)"
                elif duration_sec <= 86400 * 3: # 3 days
                    group_expr = "strftime('%Y-%m-%d %H:', timestamp) || (strftime('%M', timestamp) / 5 * 5)"
                elif duration_sec <= 86400 * 10: # 10 days
                    group_expr = "strftime('%Y-%m-%d %H:', timestamp) || (strftime('%M', timestamp) / 30 * 30)"
                else: # Up to 30 days
                    group_expr = "strftime('%Y-%m-%d %H:00', timestamp)"

                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                query_str = f"""
                    SELECT 
                        {group_expr} as t_time,
                        ROUND(AVG(battery_voltage), 2),
                        ROUND(MIN(grid_voltage), 1),
                        ROUND(AVG(load_current), 2),
                        ROUND(AVG(cell1_voltage), 2),
                        ROUND(AVG(cell2_voltage), 2),
                        ROUND(AVG(cell3_voltage), 2),
                        ROUND(AVG(cell4_voltage), 2)
                    FROM ups_history 
                    WHERE timestamp BETWEEN ? AND ?
                    GROUP BY t_time
                    ORDER BY t_time ASC
                """
                cursor.execute(query_str, (s_dt.strftime("%Y-%m-%d %H:%M:%S"), e_dt.strftime("%Y-%m-%d %H:%M:%S")))
                rows = cursor.fetchall()
                conn.close()

                history_data = []
                for row in rows:
                    history_data.append({
                        "time": row[0],
                        "battery_voltage": row[1],
                        "grid_voltage": row[2],
                        "load_current": row[3],
                        "cell1_voltage": row[4],
                        "cell2_voltage": row[5],
                        "cell3_voltage": row[6],
                        "cell4_voltage": row[7]
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
