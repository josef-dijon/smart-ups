import sys
import os
import time
import json
import sqlite3
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configurations
DB_PATH = os.environ.get("DB_PATH", "/data/history.db")
PICO_UPS_URL = os.environ.get("PICO_UPS_URL", "")
PORT = int(os.environ.get("PORT", "8080"))

if not PICO_UPS_URL or PICO_UPS_URL.strip() == "":
    PICO_UPS_URL = None

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
