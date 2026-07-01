import uasyncio
import json
import config
from lad_controller import LADController

# Global controller instance reference
_controller = None

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart UPS Controller Platform</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(30, 41, 59, 0.7);
            --border-color: rgba(255, 255, 255, 0.1);
            --primary: #3b82f6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        body {
            background-color: var(--bg-color);
            background-image: radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), transparent 400px),
                              radial-gradient(circle at bottom left, rgba(16, 185, 129, 0.05), transparent 400px);
            color: var(--text);
            min-height: 100vh;
            padding: 2rem 1rem;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }

        h1 {
            font-size: 1.8rem;
            font-weight: 700;
            background: linear-gradient(to right, #3b82f6, #10b981);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .sub-header {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
        }

        .status-badge {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--success);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
            border-color: rgba(59, 130, 246, 0.2);
        }

        .card-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .metric-group {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .metric-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }

        .metric-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .metric-label {
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        .metric-val {
            font-size: 1.25rem;
            font-weight: 700;
        }

        .metric-unit {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-left: 0.15rem;
        }

        .badge {
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-success { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
        .badge-danger { background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }
        .badge-warning { background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-info { background: rgba(59, 130, 246, 0.15); color: var(--primary); border: 1px solid rgba(59, 130, 246, 0.3); }

        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s, opacity 0.2s;
            margin-top: 0.5rem;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .btn-danger {
            background: var(--danger);
        }

        .btn-success {
            background: var(--success);
        }

        .control-input {
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            color: white;
            padding: 0.6rem;
            border-radius: 8px;
            font-size: 1rem;
            margin-bottom: 0.75rem;
            text-align: center;
        }

        .control-input:focus {
            outline: none;
            border-color: var(--primary);
        }

        .cell-bar-container {
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            height: 12px;
            margin-top: 0.4rem;
            overflow: hidden;
            border: 1px solid var(--border-color);
        }

        .cell-bar {
            height: 100%;
            background: var(--primary);
            width: 0%;
            transition: width 0.5s, background-color 0.5s;
        }

        .fuse-notice {
            background: rgba(245, 158, 11, 0.05);
            border: 1px dashed var(--warning);
            border-radius: 12px;
            padding: 1rem 1.5rem;
            font-size: 0.85rem;
            line-height: 1.4;
            color: #fbd38d;
            margin-top: 2rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .fuse-icon {
            font-size: 1.5rem;
            flex-shrink: 0;
        }

        .write-notice {
            font-size: 0.75rem;
            color: var(--text-muted);
            text-align: center;
            margin-top: 0.5rem;
        }

        @media (max-width: 768px) {
            .grid { grid-template-columns: 1fr; }
            header { flex-direction: column; align-items: flex-start; gap: 1rem; }
            .status-badge { align-self: flex-start; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Smart UPS Controller</h1>
                <div class="sub-header">W5500-EVB-Pico & Mean Well LAD-600BU Platform</div>
            </div>
            <div class="status-badge">
                <div class="pulse-dot"></div>
                <span>Pico System Live</span>
            </div>
        </header>

        <div class="grid">
            <!-- Telemetry Card -->
            <div class="card">
                <div class="card-title">
                    <span>AC Grid & Main Power</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                </div>
                <div class="metric-group">
                    <div class="metric-row">
                        <span class="metric-label">Grid Input Voltage</span>
                        <div>
                            <span class="metric-val" id="grid_voltage">--.-</span>
                            <span class="metric-unit">V</span>
                        </div>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Grid AC Status</span>
                        <span class="badge" id="ac_status_badge">UNKNOWN</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Load Current</span>
                        <div>
                            <span class="metric-val" id="load_current">--.--</span>
                            <span class="metric-unit">A</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Battery Card -->
            <div class="card">
                <div class="card-title">
                    <span>Battery Series String</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="16" height="12" rx="2" ry="2"/><line x1="6" y1="11" x2="10" y2="11"/><line x1="6" y1="15" x2="12" y2="15"/><line x1="22" y1="11" x2="22" y2="15"/></svg>
                </div>
                <div class="metric-group">
                    <div class="metric-row">
                        <span class="metric-label">Total Battery Voltage</span>
                        <div>
                            <span class="metric-val" id="battery_voltage">--.--</span>
                            <span class="metric-unit">V</span>
                        </div>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Battery Connection</span>
                        <span class="badge" id="bat_conn_badge">UNKNOWN</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Charge State</span>
                        <span class="badge" id="charge_badge">UNKNOWN</span>
                    </div>
                </div>
            </div>

            <!-- Cell Supervision Card -->
            <div class="card">
                <div class="card-title">
                    <span>Discrete Cell Inspection</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                </div>
                <div class="metric-group">
                    <div>
                        <div class="metric-row" style="border: none; padding-bottom: 0;">
                            <span class="metric-label">Battery 1 Voltage</span>
                            <div>
                                <span class="metric-val" style="font-size: 1.1rem;" id="cell1_voltage">--.--</span>
                                <span class="metric-unit">V</span>
                            </div>
                        </div>
                        <div class="cell-bar-container">
                            <div class="cell-bar" id="cell1_bar"></div>
                        </div>
                    </div>
                    <div>
                        <div class="metric-row" style="border: none; padding-bottom: 0;">
                            <span class="metric-label">Battery 2 Voltage</span>
                            <div>
                                <span class="metric-val" style="font-size: 1.1rem;" id="cell2_voltage">--.--</span>
                                <span class="metric-unit">V</span>
                            </div>
                        </div>
                        <div class="cell-bar-container">
                            <div class="cell-bar" id="cell2_bar"></div>
                        </div>
                    </div>
                    <div class="metric-row" style="margin-top: 0.5rem;">
                        <span class="metric-label">Cell Imbalance</span>
                        <span class="badge" id="balance_badge">UNKNOWN</span>
                    </div>
                </div>
            </div>

            <!-- Protection Limits & Warnings -->
            <div class="card">
                <div class="card-title">
                    <span>Safety Limits & Diagnostics</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                </div>
                <div class="metric-group">
                    <div class="metric-row">
                        <span class="metric-label">Hardware UVP Limit</span>
                        <div>
                            <span class="metric-val" id="uvp_threshold">--.--</span>
                            <span class="metric-unit">V</span>
                        </div>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">UVP Alert Status</span>
                        <span class="badge" id="uvp_alert_badge">UNKNOWN</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Overload Warning</span>
                        <span class="badge" id="olp_badge">UNKNOWN</span>
                    </div>
                </div>
            </div>

            <!-- Control Card 1 -->
            <div class="card">
                <div class="card-title">
                    <span>Isolate / Backup Relay</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                </div>
                <div class="metric-group">
                    <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.5rem;">
                        Isolate the energy storage string to prevent backup, or re-enable the automatic backup path.
                    </p>
                    <div class="metric-row">
                        <span class="metric-label">Standby Switch</span>
                        <span class="badge" id="relay_state_badge">UNKNOWN</span>
                    </div>
                    <button class="btn btn-danger" id="btn_isolate" onclick="controlAction('isolate')">Isolate Battery Relay</button>
                    <button class="btn btn-success" id="btn_connect" onclick="controlAction('connect')">Restore Backup Relay</button>
                </div>
            </div>

            <!-- Control Card 2 -->
            <div class="card">
                <div class="card-title">
                    <span>Mute & Thresholds</span>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M23 9l-6 6M17 9l6 6"/></svg>
                </div>
                <div class="metric-group">
                    <div class="metric-row">
                        <span class="metric-label">Buzzer Control</span>
                        <button class="btn" style="margin: 0; width: auto;" id="btn_buzzer" onclick="toggleBuzzer()">Toggle Mute</button>
                    </div>
                    <div style="margin-top: 0.5rem;">
                        <span class="metric-label" style="display: block; margin-bottom: 0.4rem;">Set Runtime UVP (V)</span>
                        <input type="number" step="0.1" min="18.0" max="28.0" class="control-input" id="input_uvp" placeholder="e.g. 21.5">
                        <button class="btn" onclick="submitUvp()">Write UVP Limit</button>
                    </div>
                    <div class="write-notice">Writes target processor volatile RAM</div>
                </div>
            </div>
        </div>

        <div class="fuse-notice">
            <span class="fuse-icon">⚠️</span>
            <div>
                <strong>Mandatory Safety Requirement:</strong> Ensure a physical, inline safety fuse is installed directly on the high-current <strong>BAT+</strong> terminal wire. Hardware alarms are not a substitute for physical safety fuses in short-circuit conditions.
            </div>
        </div>
    </div>

    <script>
        let isBuzzerMuted = false;
        let isIsolated = false;

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                updateUI(data);
            } catch (err) {
                console.error("Error fetching telemetry:", err);
            }
        }

        function updateUI(data) {
            // Voltages & Currents
            document.getElementById('grid_voltage').innerText = data.grid_voltage.toFixed(1);
            document.getElementById('load_current').innerText = data.load_current.toFixed(2);
            document.getElementById('battery_voltage').innerText = data.battery_voltage.toFixed(2);
            document.getElementById('cell1_voltage').innerText = data.cell1_voltage.toFixed(2);
            document.getElementById('cell2_voltage').innerText = data.cell2_voltage.toFixed(2);
            document.getElementById('uvp_threshold').innerText = data.uvp_threshold.toFixed(2);

            // Progress bars (assuming SLA battery float is 13.8V max per cell)
            const getPct = (val) => Math.max(0, Math.min(100, ((val - 10.0) / 3.8) * 100));
            document.getElementById('cell1_bar').style.width = getPct(data.cell1_voltage) + '%';
            document.getElementById('cell2_bar').style.width = getPct(data.cell2_voltage) + '%';

            // AC Status
            const acBadge = document.getElementById('ac_status_badge');
            if (data.ac_ok) {
                acBadge.innerText = "Grid OK";
                acBadge.className = "badge badge-success";
            } else {
                acBadge.innerText = "AC FAIL";
                acBadge.className = "badge badge-danger";
            }

            // Battery Connection
            const batConnBadge = document.getElementById('bat_conn_badge');
            if (!data.bat_nc) {
                batConnBadge.innerText = "Connected";
                batConnBadge.className = "badge badge-success";
            } else {
                batConnBadge.innerText = "No Battery";
                batConnBadge.className = "badge badge-danger";
            }

            // Charge State
            const chargeBadge = document.getElementById('charge_badge');
            if (data.bat_rev) {
                chargeBadge.innerText = "REVERSE POLARITY";
                chargeBadge.className = "badge badge-danger";
            } else if (data.bat_chgfull) {
                chargeBadge.innerText = "Full Charge";
                chargeBadge.className = "badge badge-success";
            } else if (data.bat_chging) {
                chargeBadge.innerText = "Charging";
                chargeBadge.className = "badge badge-info";
            } else {
                chargeBadge.innerText = "Discharging / Standby";
                chargeBadge.className = "badge badge-warning";
            }

            // Cell Imbalance Status
            const balanceBadge = document.getElementById('balance_badge');
            if (data.bat_no_balance) {
                balanceBadge.innerText = "Imbalanced";
                balanceBadge.className = "badge badge-danger";
            } else {
                balanceBadge.innerText = "Balanced / OK";
                balanceBadge.className = "badge badge-success";
            }

            // UVP Alert
            const uvpBadge = document.getElementById('uvp_alert_badge');
            if (data.bat_uvp) {
                uvpBadge.innerText = "UNDER-VOLTAGE";
                uvpBadge.className = "badge badge-danger";
            } else {
                uvpBadge.innerText = "Voltage Normal";
                uvpBadge.className = "badge badge-success";
            }

            // Overload status
            const olpBadge = document.getElementById('olp_badge');
            if (data.discharge_olp) {
                olpBadge.innerText = "OVERLOAD ALERT";
                olpBadge.className = "badge badge-danger";
            } else {
                olpBadge.innerText = "Load OK";
                olpBadge.className = "badge badge-success";
            }

            // Standby Switch State
            const relayBadge = document.getElementById('relay_state_badge');
            isIsolated = data.bat_sw_off;
            if (isIsolated) {
                relayBadge.innerText = "ISOLATED";
                relayBadge.className = "badge badge-danger";
            } else {
                relayBadge.innerText = "BACKUP ARMED";
                relayBadge.className = "badge badge-success";
            }
        }

        async function controlAction(action) {
            try {
                const res = await fetch(`/api/control?action=${action}`);
                const data = await res.json();
                if (data.success) {
                    alert(`Relay Action '${action}' executed successfully.`);
                    fetchStatus();
                } else {
                    alert(`Action failed: ${data.error}`);
                }
            } catch (err) {
                alert(`Error executing control: ${err}`);
            }
        }

        async function toggleBuzzer() {
            const nextState = !isBuzzerMuted;
            const action = nextState ? 'mute' : 'unmute';
            try {
                const res = await fetch(`/api/control?action=${action}`);
                const data = await res.json();
                if (data.success) {
                    isBuzzerMuted = nextState;
                    document.getElementById('btn_buzzer').innerText = isBuzzerMuted ? "Unmute Buzzer" : "Mute Buzzer";
                } else {
                    alert(`Action failed: ${data.error}`);
                }
            } catch (err) {
                alert(`Error executing control: ${err}`);
            }
        }

        async function submitUvp() {
            const val = parseFloat(document.getElementById('input_uvp').value);
            if (isNaN(val) || val < 18.0 || val > 28.0) {
                alert("Please enter a valid voltage between 18.0V and 28.0V");
                return;
            }
            try {
                const res = await fetch(`/api/control?action=uvp&voltage=${val}`);
                const data = await res.json();
                if (data.success) {
                    alert(`UVP limit set to ${val}V successfully.`);
                    fetchStatus();
                } else {
                    alert(`Action failed: ${data.error}`);
                }
            } catch (err) {
                alert(`Error executing control: ${err}`);
            }
        }

        // Start status polling
        fetchStatus();
        setInterval(fetchStatus, 1500);
    </script>
</body>
</html>
"""

async def handle_client(reader, writer):
    """
    Handles single web socket connection.
    Implements aggressive socket tracking to prevent memory leakage on RP2040.
    """
    try:
        # 1. Read HTTP request line
        req_line = await reader.readline()
        if not req_line:
            return
        
        # Consume request headers
        while True:
            line = await reader.readline()
            if not line or line == b'\r\n':
                break
                
        # Parse method and URI
        req_str = req_line.decode('utf-8')
        parts = req_str.split(' ')
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]
        
        # 2. Router Dispatch
        if path == "/" or path == "/index.html":
            # Serve dashboard html
            response_header = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
            writer.write(response_header.encode('utf-8'))
            writer.write(HTML_DASHBOARD.encode('utf-8'))
            
        elif path == "/api/status":
            # Serve telemetry json
            telemetry_data = json.dumps(_controller.telemetry)
            response_header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            writer.write(response_header.encode('utf-8'))
            writer.write(telemetry_data.encode('utf-8'))
            
        elif path.startswith("/api/control?"):
            # Parse simple query params
            query = path.split("?")[1]
            params = {}
            for pair in query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=")
                    params[k] = v
            
            action = params.get("action", "")
            success = False
            err_msg = ""
            
            if action == "isolate":
                success = await _controller.isolate_battery()
            elif action == "connect":
                success = await _controller.enable_battery_backup()
            elif action == "mute":
                success = await _controller.set_buzzer_mute(True)
            elif action == "unmute":
                success = await _controller.set_buzzer_mute(False)
            elif action == "uvp":
                voltage_str = params.get("voltage", "")
                try:
                    voltage = float(voltage_str)
                    success = await _controller.set_uvp_limit(voltage)
                except ValueError:
                    err_msg = "Invalid voltage parameter value"
            else:
                err_msg = "Unknown action requested"
                
            resp_body = json.dumps({"success": success, "error": err_msg})
            response_header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
            writer.write(response_header.encode('utf-8'))
            writer.write(resp_body.encode('utf-8'))
            
        else:
            # 404 Not Found
            resp_body = "404 Not Found"
            response_header = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n"
            writer.write(response_header.encode('utf-8'))
            writer.write(resp_body.encode('utf-8'))
            
        await writer.drain()
        
    except Exception as e:
        print("[Web] Error in client handler:", e)
    finally:
        # Aggressive connection tracking to free socket file descriptors
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print("[Web] Socket close error:", e)

async def start_server(controller: LADController):
    """Starts the network web server daemon."""
    global _controller
    _controller = controller
    
    print(f"[Web] Starting daemon on port {config.WEB_PORT}...")
    server = await uasyncio.start_server(handle_client, '0.0.0.0', config.WEB_PORT)
    return server
