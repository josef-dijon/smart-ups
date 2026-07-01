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
    "uvp_threshold": 21.5
}

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
