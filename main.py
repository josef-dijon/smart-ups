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
