class Pin:
    OUT = 1
    IN = 2
    
    def __init__(self, pin_id, mode=IN, value=0):
        self.pin_id = pin_id
        self.mode = mode
        self._value = value
        
    def value(self, val=None):
        if val is not None:
            self._value = val
        return self._value


class SPI:
    def __init__(self, spi_id, baudrate=1000000, polarity=0, phase=0, mosi=None, miso=None, sck=None):
        self.spi_id = spi_id
        self.baudrate = baudrate
        self.polarity = polarity
        self.phase = phase
        self.mosi = mosi
        self.miso = miso
        self.sck = sck


class UART:
    def __init__(self, uart_id, baudrate=9600, tx=None, rx=None, bits=8, parity=None, stop=1):
        self.uart_id = uart_id
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx
        self.bits = bits
        self.parity = parity
        self.stop = stop
        
        self.rx_buffer = bytearray()
        self.tx_history = []
        
    def write(self, data):
        self.tx_history.append(bytes(data))
        
        if len(data) >= 4:
            rw = data[0]
            addr = (data[2] << 8) | data[3]
            
            from crc8 import crc8
            
            if rw == 0x55:  # Read Command
                if addr == 0x0010:
                    payload = b'\x00\x01\x17\x81'  # status
                elif addr == 0x0020:
                    payload = b'\x08\xfe'          # grid voltage (230.2V)
                elif addr == 0x0030:
                    payload = b'\x02\x21'          # load current (5.45A)
                elif addr == 0x0040:
                    payload = b'\x0a\xc8'          # battery voltage (27.60V)
                elif addr == 0x0050:
                    payload = b'\x05\x64\x05\x64\x00\x00\x00\x00'  # cell voltages (13.80V, 13.80V)
                elif addr == 0x0060:
                    payload = b'\x08\x66'          # hardware UVP limit (21.50V)
                else:
                    payload = b'\x00\x00'
                
                # Header: R/W (1), Length (1), Addr (2). Body: payload, CRC (1)
                # Length = 2 (address) + len(payload) + 1 (CRC) = len(payload) + 3
                resp_header = bytes([0x55, len(payload) + 3, data[2], data[3]])
                resp_packet = resp_header + payload
                resp_packet += bytes([crc8(resp_packet)])
                self.rx_buffer.extend(resp_packet)
                
            elif rw == 0xAA:  # Write Command
                # Echo back the write command for verification success
                self.rx_buffer.extend(data)
                
        return len(data)
        
    def any(self):
        return len(self.rx_buffer) > 0
        
    def read(self, n=None):
        if len(self.rx_buffer) == 0:
            return b""
        if n is None:
            data = bytes(self.rx_buffer)
            self.rx_buffer.clear()
            return data
        else:
            data = bytes(self.rx_buffer[:n])
            self.rx_buffer = self.rx_buffer[n:]
            return data
