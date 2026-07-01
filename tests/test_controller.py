import sys
import os
import unittest
import asyncio

# Resolve paths to allow running from any directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. Mock 'machine' module
import tests.mock_machine as mock_machine
sys.modules['machine'] = mock_machine

# 2. Mock 'uasyncio' using standard Python 'asyncio'
async def sleep_ms(delay):
    await asyncio.sleep(delay / 1000.0)

asyncio.sleep_ms = sleep_ms
sys.modules['uasyncio'] = asyncio

# Import production code to test
from crc8 import crc8, verify_crc8
from lad_controller import LADController

class TestSmartUpsTelemetry(unittest.IsolatedAsyncioTestCase):
    
    def test_crc8_known_vectors(self):
        # Read status request from manual page 32
        self.assertEqual(crc8(b'\x55\x03\x00\x10'), 0x7F)
        # Read status response from manual page 32
        self.assertEqual(crc8(b'\x55\x07\x00\x10\x00\x01\x17\x81'), 0x4C)
        # Read voltage request from manual page 34
        self.assertEqual(crc8(b'\x55\x03\x00\x20'), 0xEF)
        # Read load current request from manual page 35
        self.assertEqual(crc8(b'\x55\x03\x00\x30'), 0x9F)
        # Read battery voltage request from manual page 36
        self.assertEqual(crc8(b'\x55\x03\x00\x40'), 0xC8)
        # Read cell voltage request from manual page 37
        self.assertEqual(crc8(b'\x55\x03\x00\x50'), 0xB8)
        
    async def test_telemetry_polling_and_scaling(self):
        controller = LADController()
        
        # Run asynchronous telemetry update (the mock UART will generate correct responses on the fly)
        success = await controller.update_telemetry()
        self.assertTrue(success)
        
        # Assert scale and mapping values
        self.assertEqual(controller.telemetry["grid_voltage"], 230.2)
        self.assertEqual(controller.telemetry["load_current"], 5.45)
        self.assertEqual(controller.telemetry["battery_voltage"], 27.6)
        self.assertEqual(controller.telemetry["cell1_voltage"], 13.8)
        self.assertEqual(controller.telemetry["cell2_voltage"], 13.8)
        self.assertEqual(controller.telemetry["uvp_threshold"], 21.5)
        
        # Check unpacked status flags
        self.assertTrue(controller.telemetry["bat_sw_off"])
        self.assertTrue(controller.telemetry["ac_ok"])
        self.assertTrue(controller.telemetry["bat_no_balance"])
        self.assertTrue(controller.telemetry["bat_error_1"])
        self.assertTrue(controller.telemetry["bat_chgfull"])
        self.assertFalse(controller.telemetry["bat_rev"])
 
    async def test_write_commands(self):
        controller = LADController()
        uart = controller.uart
        
        # 1. Test set UVP limit (21.5V -> 2150 = 0x0866)
        uvp_cmd_raw = b'\xaa\x05\x00\x20\x08\x66'
        uvp_expected_packet = uvp_cmd_raw + bytes([crc8(uvp_cmd_raw)])
        
        success = await controller.set_uvp_limit(21.5)
        self.assertTrue(success)
        self.assertEqual(uart.tx_history[-1], uvp_expected_packet)
        
        # 2. Test buzzer mute toggle (True -> mute = write 0x01 to 0x0030)
        mute_cmd_raw = b'\xaa\x04\x00\x30\x01'
        mute_expected_packet = mute_cmd_raw + bytes([crc8(mute_cmd_raw)])
        
        success = await controller.set_buzzer_mute(True)
        self.assertTrue(success)
        self.assertEqual(uart.tx_history[-1], mute_expected_packet)
 
        # 3. Test battery isolation (isolate_battery -> write 0x01 to 0x0010)
        isolate_cmd_raw = b'\xaa\x04\x00\x10\x01'
        isolate_expected_packet = isolate_cmd_raw + bytes([crc8(isolate_cmd_raw)])
        
        success = await controller.isolate_battery()
        self.assertTrue(success)
        self.assertEqual(uart.tx_history[-1], isolate_expected_packet)


if __name__ == '__main__':
    unittest.main()
