# Hardware Configuration for Smart UPS Controller Platform
# Compute Core: W5500-EVB-Pico (RP2040 Microcontroller)

# 1. W5500 Internal SPI Routing (SPI0 Peripheral Block)
W5500_SPI_ID = 0
W5500_MISO = 16
W5500_MOSI = 19
W5500_SCLK = 18
W5500_CS = 17
W5500_RST = 20

# 2. LAD-600BU UART1 Signaling Interface
LAD_UART_ID = 1
LAD_TX_PIN = 4
LAD_RX_PIN = 5
LAD_BAUD = 9600

# 3. Network Configuration
USE_DHCP = True
# Fallback static configuration if USE_DHCP is False
STATIC_IP = ("192.168.1.15", "255.255.255.0", "192.168.1.1", "8.8.8.8")

# 4. Web Daemon Configuration
WEB_PORT = 80
JSON_API_PATH = "/api/status"

# 5. MQTT Configuration (Telemetry Publishing)
MQTT_BROKER = "192.168.1.50"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "smart_ups_pico"
MQTT_TOPIC_PREFIX = "smart_ups"
MQTT_USER = None
MQTT_PASSWORD = None
MQTT_PUBLISH_INTERVAL = 10

