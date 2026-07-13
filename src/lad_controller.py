import uasyncio
from machine import UART, Pin
import time
import config
from crc8 import crc8, verify_crc8

class LADController:
    """
    Controller for MEAN WELL LAD-600BU (UART version) over half-duplex UART interface.
    Handles telemetry parsing and register writes asynchronously.
    """

    def __init__(self):
        # Initialize UART1 per specifications
        self.uart = UART(
            config.LAD_UART_ID,
            baudrate=config.LAD_BAUD,
            tx=Pin(config.LAD_TX_PIN),
            rx=Pin(config.LAD_RX_PIN),
            bits=8,
            parity=None,
            stop=1
        )
        self.lock = uasyncio.Lock()
        
        # Telemetry storage (all voltages scaled back to Float Volts, currents to Float Amps)
        self.telemetry = {
            # STATUS flags (0x0010 Read)
            "ac_ok": False,
            "bat_sw_off": False,
            "bat_nc": False,
            "discharge_olp": False,
            "bat_uvp": False,
            "lad_power_supply": False,
            "link_ctrl": False,
            "bat_ovp": False,
            "bat_no_balance": False,
            "bat_error_1": False,
            "bat_error_2": False,
            "bat_error_3": False,
            "bat_error_4": False,
            "bat_chgfull": False,
            "bat_chging": False,
            "bat_rev": False,
            "force_status": False,
            
            # Measurement registers
            "grid_voltage": 0.0,       # V (0x0020 Read, scale 0.1V)
            "load_current": 0.0,       # A (0x0030 Read, scale 0.01A)
            "battery_voltage": 0.0,    # V (0x0040 Read, scale 0.01V)
            "cell1_voltage": 0.0,      # V (0x0050 index 0-1, scale 0.01V)
            "cell2_voltage": 0.0,      # V (0x0050 index 2-3, scale 0.01V)
            "cell3_voltage": 0.0,      # V (0x0050 index 4-5, scale 0.01V)
            "cell4_voltage": 0.0,      # V (0x0050 index 6-7, scale 0.01V)
            "uvp_threshold": 0.0,      # V (0x0060 Read, scale 0.01V)
            
            "last_update": 0
        }

    async def send_command(self, cmd_rw: int, reg_addr: int, data_bytes: bytes = b"") -> bytes:
        """
        Sends a command to the LAD device and returns the response payload.
        Ensures a minimum 20ms pause before transmission and handles peripheral turnaround.
        """
        async with self.lock:
            # 1. Enforce minimum 20ms inter-packet pause
            await uasyncio.sleep_ms(20)
            
            # Format: R/W byte | Length | Address_H | Address_L | [Data Bytes] | CRC-8
            # Length includes address (2), data_bytes, and CRC (1)
            length = 2 + len(data_bytes) + 1
            addr_h = (reg_addr >> 8) & 0xFF
            addr_l = reg_addr & 0xFF
            
            packet = bytes([cmd_rw, length, addr_h, addr_l]) + data_bytes
            chksum = crc8(packet)
            full_packet = packet + bytes([chksum])
            
            # Flush any pending RX bytes in buffer
            while self.uart.any():
                self.uart.read()
                
            # Write full command packet
            self.uart.write(full_packet)
            
            # 2. Allow up to 5ms for peripheral turnaround latency
            await uasyncio.sleep_ms(5)
            
            # Read response header (R/W byte and Length byte)
            resp_header = await self._read_exact(2)
            if not resp_header or len(resp_header) < 2:
                raise OSError("Timeout reading response header")
                
            resp_rw = resp_header[0]
            resp_len = resp_header[1]
            
            # Read the rest of the packet: Address (2), Data (len), and CRC (1)
            resp_body = await self._read_exact(resp_len)
            if not resp_body or len(resp_body) < resp_len:
                raise OSError("Timeout reading response body")
                
            # Verify CRC-8 over header + body except the last CRC byte
            full_resp = resp_header + resp_body
            data_to_verify = full_resp[:-1]
            received_crc = full_resp[-1]
            if not verify_crc8(data_to_verify, received_crc):
                raise ValueError("Response CRC-8 checksum verification failed")
                
            # Verify register address matches
            resp_addr_h = resp_body[0]
            resp_addr_l = resp_body[1]
            resp_addr = (resp_addr_h << 8) | resp_addr_l
            if resp_addr != reg_addr:
                raise ValueError(f"Response register address mismatch: expected {hex(reg_addr)}, got {hex(resp_addr)}")
                
            # Data bytes are located after the 2-byte address and before the 1-byte CRC
            return resp_body[2:-1]

    async def _read_exact(self, n: int) -> bytes:
        """Reads exactly n bytes from UART with a timeout."""
        buf = bytearray()
        timeout_ms = 100
        elapsed = 0
        while len(buf) < n and elapsed < timeout_ms:
            if self.uart.any():
                data = self.uart.read(n - len(buf))
                if data:
                    buf.extend(data)
            else:
                await uasyncio.sleep_ms(2)
                elapsed += 2
        return bytes(buf)

    async def update_telemetry(self) -> bool:
        """
        Polls the LAD-600BU device to update the telemetry dictionary.
        Returns True if successful, False otherwise.
        """
        try:
            # 1. Read status (0x0010)
            status_data = await self.send_command(0x55, 0x0010)
            if len(status_data) >= 4:
                status_h_low = status_data[1]
                status_l_high = status_data[2]
                status_l_low = status_data[3]

                self.telemetry["bat_sw_off"] = bool(status_h_low & 0x01)

                self.telemetry["bat_error_1"] = bool(status_l_high & 0x01)
                self.telemetry["bat_error_2"] = bool(status_l_high & 0x02)
                self.telemetry["bat_error_3"] = bool(status_l_high & 0x04)
                self.telemetry["bat_error_4"] = bool(status_l_high & 0x08)
                self.telemetry["bat_chgfull"] = bool(status_l_high & 0x10)
                self.telemetry["bat_chging"] = bool(status_l_high & 0x20)
                self.telemetry["bat_rev"] = bool(status_l_high & 0x40)
                self.telemetry["force_status"] = bool(status_l_high & 0x80)

                self.telemetry["ac_ok"] = bool(status_l_low & 0x01)
                self.telemetry["bat_nc"] = bool(status_l_low & 0x02)
                self.telemetry["discharge_olp"] = bool(status_l_low & 0x04)
                self.telemetry["bat_uvp"] = bool(status_l_low & 0x08)
                self.telemetry["lad_power_supply"] = bool(status_l_low & 0x10)
                self.telemetry["link_ctrl"] = bool(status_l_low & 0x20)
                self.telemetry["bat_ovp"] = bool(status_l_low & 0x40)
                self.telemetry["bat_no_balance"] = bool(status_l_low & 0x80)

            # 2. Read grid voltage (0x0020)
            grid_data = await self.send_command(0x55, 0x0020)
            if len(grid_data) >= 2:
                self.telemetry["grid_voltage"] = ((grid_data[0] << 8) | grid_data[1]) / 10.0

            # 3. Read load current (0x0030)
            load_data = await self.send_command(0x55, 0x0030)
            if len(load_data) >= 2:
                self.telemetry["load_current"] = ((load_data[0] << 8) | load_data[1]) / 100.0

            # 4. Read battery voltage (0x0040)
            bat_data = await self.send_command(0x55, 0x0040)
            if len(bat_data) >= 2:
                self.telemetry["battery_voltage"] = ((bat_data[0] << 8) | bat_data[1]) / 100.0

            # 5. Read cell voltages (0x0050)
            # Unpack indices 0-1 (Cell 1), 2-3 (Cell 2), 4-5 (Cell 3), and 6-7 (Cell 4) from 8-byte array
            cell_data = await self.send_command(0x55, 0x0050)
            if len(cell_data) >= 8:
                self.telemetry["cell1_voltage"] = ((cell_data[0] << 8) | cell_data[1]) / 100.0
                self.telemetry["cell2_voltage"] = ((cell_data[2] << 8) | cell_data[3]) / 100.0
                self.telemetry["cell3_voltage"] = ((cell_data[4] << 8) | cell_data[5]) / 100.0
                self.telemetry["cell4_voltage"] = ((cell_data[6] << 8) | cell_data[7]) / 100.0

            # 6. Read hardware UVP threshold limit (0x0060)
            uvp_data = await self.send_command(0x55, 0x0060)
            if len(uvp_data) >= 2:
                self.telemetry["uvp_threshold"] = ((uvp_data[0] << 8) | uvp_data[1]) / 100.0

            self.telemetry["last_update"] = time.time()
            return True
        except Exception as e:
            print("[LAD] Error updating telemetry:", e)
            return False

    async def isolate_battery(self) -> bool:
        """
        Sends command to open the battery relay (isolates the battery).
        Targets volatile RAM: defaults will clear on system power cycle.
        """
        print("[LAD] Warning: Register modification targets volatile RAM (will clear on power cycle).")
        try:
            # Write 0x01 to 0x0010 (Backup removal control / Standby excision)
            await self.send_command(0xAA, 0x0010, b"\x01")
            print("[LAD] Battery isolation command sent successfully.")
            return True
        except Exception as e:
            print("[LAD] Error isolating battery:", e)
            return False

    async def enable_battery_backup(self) -> bool:
        """
        Sends command to close the battery relay (re-enables standby battery backup).
        Targets volatile RAM: defaults will clear on system power cycle.
        """
        print("[LAD] Warning: Register modification targets volatile RAM (will clear on power cycle).")
        try:
            # Write 0x01 to 0x0040 (Standby enable command)
            await self.send_command(0xAA, 0x0040, b"\x01")
            print("[LAD] Standby enable command sent successfully.")
            return True
        except Exception as e:
            print("[LAD] Error enabling standby backup:", e)
            return False

    async def set_uvp_limit(self, voltage: float) -> bool:
        """
        Sets runtime UVP (under-voltage protection) limit.
        Scale unit is 0.01V (e.g. 43.2V = 4320).
        Targets volatile RAM: defaults will clear on system power cycle.
        """
        print("[LAD] Warning: Register modification targets volatile RAM (will clear on power cycle).")
        try:
            val = int(round(voltage * 100.0))
            if not (0 <= val <= 65535):
                raise ValueError("Voltage value out of 16-bit range")
            data = bytes([(val >> 8) & 0xFF, val & 0xFF])
            # Write to 0x0020
            await self.send_command(0xAA, 0x0020, data)
            print(f"[LAD] UVP threshold set to {voltage}V successfully.")
            return True
        except Exception as e:
            print("[LAD] Error setting UVP limit:", e)
            return False

    async def set_buzzer_mute(self, mute: bool) -> bool:
        """
        Mutes or unmutes the buzzer.
        0x01 mutes the buzzer, 0x00 unmutes.
        Targets volatile RAM: defaults will clear on system power cycle.
        """
        print("[LAD] Warning: Register modification targets volatile RAM (will clear on power cycle).")
        try:
            data = b"\x01" if mute else b"\x00"
            # Write to 0x0030
            await self.send_command(0xAA, 0x0030, data)
            print(f"[LAD] Buzzer mute state set to {mute} successfully.")
            return True
        except Exception as e:
            print("[LAD] Error setting buzzer mute:", e)
            return False
