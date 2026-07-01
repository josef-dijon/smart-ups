# Antigravity Agent Configuration: Smart UPS Controller Platform

## 1. System Target Architecture
* [cite_start]**Primary Power Hardware:** MEAN WELL LAD-600BU (600W, 27.6V Nominal DC Bus, UART Version)[cite: 17, 19, 21].
* [cite_start]**Energy Storage Subsystem:** Two 12V Lead-Acid (SLA) batteries wired in series forming a 24V nominal string (27.6V float charge profiles)[cite: 36, 39, 196].
* **Compute Core:** W5500-EVB-Pico (RP2040 Microcontroller with hardwired internal Wiznet 5500 MAC/PHY) via MicroPython.

## 2. Hardwired Electrical Interconnect Matrix

### 2.1 W5500 Internal SPI Routing (SPI1 Peripheral Block)
The AI agent must explicitly use these exact pin configurations when modifying network or socket wrappers. Do not assume standard external Raspberry Pi Pico SPI0 layouts:
* **MISO (RX):** `GP12`
* **MOSI (TX):** `GP13`
* **SCLK (SCK):** `GP14`
* **CS (Chip Select):** `GP15`
* **RST (Reset):** `GP11`

### 2.2 LAD-600BU UART1 Signaling Interface
* **Pico TX Pin (Output):** `GP4` -> Connects to LAD CN2 Pin 13 (UART_RX)
* **Pico RX Pin (Input):** `GP5` -> Connects to LAD CN2 Pin 14 (UART_TX)
* **Logic Ground:** `GP3` or any common ground rail -> Connects to LAD CN2 Pin 15 (GND)

### 2.3 Discrete Battery Cell Inspection Link
* [cite_start]**CN2 Pin 9 (BAT1):** Must bridge directly to the center tap (the link wire bridging Battery 1 Positive to Battery 2 Negative)[cite: 331, 352]. [cite_start]This is critical for parsing discrete cell metrics via the `0x0050` register array[cite: 478, 665].

## 3. Communication Protocol Standards
[cite_start]The serial bus operates as a half-duplex, master-slave interface over a 2-wire setup[cite: 437]. 
* [cite_start]**Baud Rate:** 9600 [cite: 439]
* [cite_start]**Data Layout:** 8 Data Bits, 1 Stop Bit, No Parity, No Flow Control [cite: 439]
* [cite_start]**Byte Ordering:** High byte first (Big-Endian) for all data registers, except the terminal checksum bit[cite: 437].
* [cite_start]**Error Detection:** CRC-8 using polynomial $X^8 + X^2 + X + 1$ (`0x07`)[cite: 437, 481, 482].
* [cite_start]**Timing Constraints:** Mandate a minimum 20ms inter-packet pause before sending a write or read request[cite: 452]. [cite_start]Allow up to 5ms for peripheral turnaround latency[cite: 453].

## 4. Crucial Register Map & Scaling Modifiers
When generating code blocks, the agent must adhere to the following definitions:

| Address | Data Type | Operation | Scale Unit | Field Functional Context |
| :--- | :--- | :--- | :--- | :--- |
| `0x0010` | `U1` / `U4` | Read / Write | Bit Flags | [cite_start]**Read:** Status array bits[cite: 478, 493]. [cite_start]**Write:** `0x01` opens the relay to isolate the battery[cite: 478, 684]. |
| `0x0020` | `U2` | Read / Write | `0.1 V` / `0.01 V` | [cite_start]**Read:** Grid input voltage[cite: 478, 493]. [cite_start]**Write:** Set runtime UVP threshold limit[cite: 478, 698]. |
| `0x0030` | `U2` / `U1` | Read / Write | `0.01 A` / Scalar | [cite_start]**Read:** Current load drain[cite: 478, 493]. [cite_start]**Write:** `0x01` mutes the buzzer, `0x00` unmutes[cite: 478, 687, 688]. |
| `0x0040` | `U2` | Read Only | `0.01 V` | [cite_start]Total combined battery series string voltage[cite: 478, 493]. |
| `0x0050` | `U2` Array | Read Only | `0.01 V` | [cite_start]8-byte cell array[cite: 493, 665]. [cite_start]Unpack only indices 0-1 (Battery 1) and 2-3 (Battery 2)[cite: 665]. |
| `0x0060` | `U2` | Read Only | `0.01 V` | [cite_start]Read current hardware low-voltage protection limit[cite: 478, 493]. |

## 5. Architectural Guardrails & Coding Constraints
* **Asynchronous Concurrency:** MicroPython code must execute cooperatively via `uasyncio`. The network daemon must never block or halt the primary hardware UART instruction cycles.
* [cite_start]**Volatile Register Writes:** Remind the developer or sub-agents that register modification packages (e.g., changing UVP limits or toggling buzzer mutes) target live processor RAM[cite: 540]. [cite_start]They do not commit to non-volatile flash and will clear back to factory defaults when system power cycles[cite: 540].
* **Memory Management:** Constrained RP2040 system RAM requires aggressive socket tracking. Every web server client thread must explicitly hit `writer.close()` and invoke `await writer.wait_closed()` to prevent dangling resource leaks.
* [cite_start]**Safety Isolation Requirement:** Direct the sub-agents to always emphasize the installation of a physical, inline safety fuse on the high-current `BAT+` terminal wire to handle dead shorts safely[cite: 63, 71, 76, 80, 90].