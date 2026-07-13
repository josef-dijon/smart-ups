from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import sys

# Simulated telemetry state mapping to a real LAD-600BU target
telemetry = {
    # Status flags
    "ac_ok": True,
    "bat_sw_off": False,
    "bat_nc": False,
    "discharge_olp": False,
    "bat_uvp": False,
    "lad_power_supply": True,
    "link_ctrl": False,
    "bat_ovp": False,
    "bat_no_balance": False,
    "bat_error_1": False,
    "bat_error_2": False,
    "bat_error_3": False,
    "bat_error_4": False,
    "bat_chgfull": False,
    "bat_chging": True,
    "bat_rev": False,
    "force_status": False,
    
    # Readings
    "grid_voltage": 230.2,
    "load_current": 1.45,
    "battery_voltage": 26.8,
    "cell1_voltage": 13.38,
    "cell2_voltage": 13.42,
    "cell3_voltage": 0.0,
    "cell4_voltage": 0.0,
    "uvp_threshold": 21.5
}

import time
import random

def update_mock_telemetry():
    """
    Simulates a 120-second grid blackout cycle:
      - 0 to 60s: Grid is healthy, charging/float state.
      - 60 to 120s: Grid dropout (blackout), discharging state under load.
    """
    cycle = int(time.time()) % 120
    is_grid_up = (cycle < 60)
    
    if is_grid_up:
        telemetry["ac_ok"] = True
        telemetry["grid_voltage"] = round(230.2 + random.uniform(-1.5, 1.5), 1)
        telemetry["lad_power_supply"] = True
        
        if telemetry["bat_sw_off"]:
            # Battery isolated/disconnected
            telemetry["bat_chgfull"] = False
            telemetry["bat_chging"] = False
            telemetry["battery_voltage"] = 25.20
            telemetry["cell1_voltage"] = 12.60
            telemetry["cell2_voltage"] = 12.60
            telemetry["bat_uvp"] = False
        else:
            # Battery charging or full
            charging_phase = (cycle < 25)
            if charging_phase:
                telemetry["bat_chgfull"] = False
                telemetry["bat_chging"] = True
                telemetry["battery_voltage"] = round(26.0 + (cycle * 0.064), 2)
            else:
                telemetry["bat_chgfull"] = True
                telemetry["bat_chging"] = False
                telemetry["battery_voltage"] = 27.60
                
            telemetry["cell1_voltage"] = round(telemetry["battery_voltage"] / 2.0, 2)
            telemetry["cell2_voltage"] = round(telemetry["battery_voltage"] / 2.0, 2)
            telemetry["bat_uvp"] = False
            
        telemetry["load_current"] = round(1.45 + random.uniform(-0.05, 0.05), 2)
    else:
        # Mains dropout simulation
        telemetry["ac_ok"] = False
        telemetry["grid_voltage"] = 0.0
        telemetry["lad_power_supply"] = False
        telemetry["bat_chgfull"] = False
        telemetry["bat_chging"] = False
        
        if telemetry["bat_sw_off"]:
            # Battery isolated, zero load output
            telemetry["load_current"] = 0.0
            telemetry["battery_voltage"] = 25.00
            telemetry["cell1_voltage"] = 12.50
            telemetry["cell2_voltage"] = 12.50
            telemetry["bat_uvp"] = False
        else:
            # Active backup discharging under load
            discharge_elapsed = cycle - 60
            # Instant drop under load, then gradual discharge
            telemetry["battery_voltage"] = round(25.0 - (discharge_elapsed * 0.075), 2)
            telemetry["cell1_voltage"] = round(telemetry["battery_voltage"] / 2.0, 2)
            telemetry["cell2_voltage"] = round(telemetry["battery_voltage"] / 2.0, 2)
            
            # Check under-voltage threshold (21.5V)
            telemetry["bat_uvp"] = (telemetry["battery_voltage"] < telemetry["uvp_threshold"])
            
            # Current load increases slightly due to lower battery voltage supplying load inverter
            telemetry["load_current"] = round(3.5 + random.uniform(-0.1, 0.1), 2)

class MockDeviceHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Silence default stderr logging to keep terminal output clean
        sys.stdout.write(f"[Mock Device Server] {format % args}\n")

    def end_headers(self):
        # Enable CORS headers so local browsers can hit the mock directly
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
        query = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/status":
            update_mock_telemetry()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(telemetry).encode('utf-8'))
            
        elif path == "/api/control":
            action = query.get('action', [''])[0]
            success = False
            error = ""
            
            print(f"[Mock Device Server] Received control action: {action}")
            
            if action == 'isolate':
                telemetry['bat_sw_off'] = True
                success = True
            elif action == 'connect':
                telemetry['bat_sw_off'] = False
                success = True
            elif action == 'mute':
                success = True
            elif action == 'unmute':
                success = True
            elif action == 'uvp':
                try:
                    volts = float(query.get('voltage', ['21.5'])[0])
                    telemetry['uvp_threshold'] = volts
                    success = True
                except ValueError:
                    error = "Invalid voltage parameter"
            else:
                error = "Unknown action"
                
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "error": error}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, MockDeviceHandler)
    print(f"[Mock Device Server] Running mock device API server on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Mock Device Server] Shutting down.")
        httpd.server_close()

if __name__ == '__main__':
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run(port)
