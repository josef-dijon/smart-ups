import uasyncio
import gc
import time
from lad_controller import LADController
import web_server
from mqtt_client import MQTTTelemetryPublisher

async def telemetry_loop(controller: LADController):
    """
    Asynchronous cooperative polling task.
    Polls the MEAN WELL LAD-600BU serial bus every 1.5 seconds.
    Ensures UART loops never block the network daemon or main runtime.
    """
    print("[Main] Starting primary hardware UART telemetry loop...")
    while True:
        try:
            success = await controller.update_telemetry()
            if not success:
                print("[Main] Warning: Failed to poll telemetry from LAD interface.")
        except Exception as e:
            print("[Main] Telemetry loop exception:", e)
            
        # Constrained RP2040 system RAM requires aggressive garbage collection
        gc.collect()
        
        # 1.5 second inter-read cycle delay
        await uasyncio.sleep(1.5)

async def network_beacon_loop():
    """
    Broadcasts UDP discovery beacons every 5 seconds.
    Enables auto-discovery by the Docker dashboard server.
    """
    print("[Main] Starting UDP broadcast discovery beacon loop...")
    import usocket as socket
    import config
    while True:
        if config.ACTIVE_IP and config.ACTIVE_IP != "0.0.0.0":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                payload = '{"device": "smart_ups", "ip": "%s"}' % config.ACTIVE_IP
                s.sendto(payload.encode('utf-8'), ('255.255.255.255', 5555))
                s.close()
            except Exception as e:
                print("[Main] Failed to send UDP discovery beacon:", e)
        await uasyncio.sleep(5)

async def main_async():
    print("[Main] Initializing system nodes...")
    
    # 1. Instantiate the UART device controller
    controller = LADController()
    
    # 2. Perform initial connection poll to verify serial link
    print("[Main] Verifying serial link with LAD-600BU...")
    success = await controller.update_telemetry()
    if success:
        print("[Main] Serial connection established successfully.")
    else:
        print("[Main] Warning: Could not communicate with LAD-600BU on boot. Check RX/TX pins.")
        
    # 3. Start the Web server daemon
    await web_server.start_server(controller)
    
    # 4. Spawn the telemetry task in the background loop
    uasyncio.create_task(telemetry_loop(controller))
    
    # 5. Initialize and spawn the MQTT Telemetry Publisher task
    mqtt_publisher = MQTTTelemetryPublisher(controller)
    uasyncio.create_task(mqtt_publisher.start_loop())
    
    # 6. Spawn the UDP Broadcast Beacon discovery task
    uasyncio.create_task(network_beacon_loop())
    
    # Keep main task alive indefinitely
    while True:
        await uasyncio.sleep(3600)

if __name__ == "__main__":
    try:
        uasyncio.run(main_async())
    except KeyboardInterrupt:
        print("[Main] Execution aborted by keyboard interrupt.")
    except Exception as e:
        print("[Main] Crash loop protection triggered. Error:", e)
