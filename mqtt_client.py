import uasyncio
import usocket as socket
import json
import config
from lad_controller import LADController

class MQTTTelemetryPublisher:
    """
    Lightweight, self-contained asynchronous MQTT publisher client.
    Runs cooperatively under MicroPython uasyncio to publish telemetry.
    """
    
    def __init__(self, controller: LADController):
        self.controller = controller
        self.client_id = config.MQTT_CLIENT_ID
        self.server = config.MQTT_BROKER
        self.port = config.MQTT_PORT
        self.user = config.MQTT_USER
        self.password = config.MQTT_PASSWORD
        self.topic = f"{config.MQTT_TOPIC_PREFIX}/status"
        self.sock = None
        self.is_connected = False
        
    async def connect(self) -> bool:
        try:
            print(f"[MQTT] Connecting to broker at {self.server}:{self.port}...")
            addr_info = socket.getaddrinfo(self.server, self.port)
            addr = addr_info[0][-1]
            
            self.sock = socket.socket()
            self.sock.settimeout(5)
            self.sock.connect(addr)
            self.sock.settimeout(None)
            
            # Setup connect packet flags
            flags = 0x02  # Clean Session
            if self.user:
                flags |= 0x80
                if self.password:
                    flags |= 0x40
                    
            payload = bytearray()
            
            # Client ID
            payload.append(0)
            payload.append(len(self.client_id))
            payload.extend(self.client_id.encode('utf-8'))
            
            # Username
            if self.user:
                payload.append(0)
                payload.append(len(self.user))
                payload.extend(self.user.encode('utf-8'))
                # Password
                if self.password:
                    payload.append(0)
                    payload.append(len(self.password))
                    payload.extend(self.password.encode('utf-8'))
                    
            # Variable Header
            var_header = bytearray(b"\x00\x04MQTT\x04")
            var_header.append(flags)
            var_header.append(0)   # Keepalive MSB
            var_header.append(60)  # Keepalive LSB (60s)
            
            remaining_length = len(var_header) + len(payload)
            
            packet = bytearray()
            packet.append(0x10)  # CONNECT
            packet.append(remaining_length)
            packet.extend(var_header)
            packet.extend(payload)
            
            self.sock.write(packet)
            
            # Read CONNACK response (4 bytes)
            resp = self.sock.read(4)
            if resp and resp[0] == 0x20 and resp[1] == 0x02 and resp[3] == 0:
                self.is_connected = True
                print("[MQTT] Connected successfully to broker.")
                return True
            else:
                code = resp[3] if resp and len(resp) >= 4 else "Unknown"
                print(f"[MQTT] Connection rejected by broker (code {code}).")
                self.close_socket()
                return False
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            self.close_socket()
            return False

    def close_socket(self):
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    async def publish(self, topic: str, payload_str: str) -> bool:
        if not self.is_connected or not self.sock:
            return False
            
        try:
            topic_bytes = topic.encode('utf-8')
            payload_bytes = payload_str.encode('utf-8')
            
            rem_len = 2 + len(topic_bytes) + len(payload_bytes)
            
            packet = bytearray()
            packet.append(0x30)  # PUBLISH (QoS 0)
            
            # Variable byte remaining length encoding
            val = rem_len
            while val > 0x7f:
                packet.append((val & 0x7f) | 0x80)
                val >>= 7
            packet.append(val)
            
            # Topic length & topic
            packet.append((len(topic_bytes) >> 8) & 0xFF)
            packet.append(len(topic_bytes) & 0xFF)
            packet.extend(topic_bytes)
            
            # Payload
            packet.extend(payload_bytes)
            
            self.sock.write(packet)
            return True
        except Exception as e:
            print(f"[MQTT] Publish failed: {e}")
            self.close_socket()
            return False
            
    async def start_loop(self):
        """Asynchronous background loop to keep MQTT client alive and publish data."""
        print("[MQTT] Telemetry loop started.")
        while True:
            # Reconnect if offline
            if not self.is_connected:
                await self.connect()
                
            if self.is_connected:
                # Compile status telemetry (strip last_update)
                telemetry_data = {k: v for k, v in self.controller.telemetry.items() if k != "last_update"}
                payload_str = json.dumps(telemetry_data)
                
                success = await self.publish(self.topic, payload_str)
                if success:
                    print(f"[MQTT] Published telemetry to {self.topic}")
                    
            # Garbage collect to prevent fragmentation
            import gc
            gc.collect()
            
            await uasyncio.sleep(config.MQTT_PUBLISH_INTERVAL)
