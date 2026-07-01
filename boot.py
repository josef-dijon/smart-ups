import network
from machine import Pin, SPI
import time
import gc
import config

def init_network():
    print("[Boot] Initializing W5500 Ethernet MAC/PHY...")
    
    # 1. Perform Hardware Reset of the W5500 chip
    rst = Pin(config.W5500_RST, Pin.OUT)
    rst.value(0)
    time.sleep_ms(20)
    rst.value(1)
    time.sleep_ms(100)
    
    # 2. Configure SPI1 interface for W5500
    # GP12 (MISO), GP13 (MOSI), GP14 (SCLK), GP15 (CS)
    spi = SPI(
        config.W5500_SPI_ID, 
        baudrate=20000000, 
        polarity=0, 
        phase=0, 
        mosi=Pin(config.W5500_MOSI), 
        miso=Pin(config.W5500_MISO), 
        sck=Pin(config.W5500_SCLK)
    )
    cs = Pin(config.W5500_CS, Pin.OUT)
    
    # 3. Instantiate the WIZNET5K driver
    nic = network.WIZNET5K(spi, cs, rst)
    nic.active(True)
    
    # 4. Apply network settings
    if config.USE_DHCP:
        print("[Boot] Requesting IP address from DHCP server...")
        # Poll for connection up to 15 seconds
        retries = 15
        while not nic.isconnected() and retries > 0:
            time.sleep(1)
            retries -= 1
    else:
        print("[Boot] Setting static configuration...")
        nic.ifconfig(config.STATIC_IP)
        
    if nic.isconnected():
        print("[Boot] Network connection successful.")
        print("[Boot] Interface Config (IP, Subnet, Gateway, DNS):", nic.ifconfig())
    else:
        print("[Boot] Warning: DHCP timeout or link is down. Fallback to static config.")
        nic.ifconfig(config.STATIC_IP)
        print("[Boot] Interface Config:", nic.ifconfig())

# Run hardware initialization on start
try:
    init_network()
except Exception as e:
    print("[Boot] Critical error during boot/network init:", e)

# Garbage collect memory to start fresh
gc.collect()
