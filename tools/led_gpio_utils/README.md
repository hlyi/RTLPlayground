# LED GPIO Utilities

This directory contains utilities to monitor and decode the GPIO and LED
configuration of an RTL837x switch. Scripts 1 to 3 talk to the IC over the I2C
bus through a dongle, scripts 4 to 7 use the switch's own serial console
instead.
(Only tested in Linux)

## Hardware requirements

To use the I2C utilities (scripts 1 to 3), you need:

  - A hardware dongle that can communicate with I2C devices. One example is the [I2C-Pico-USB](https://github.com/dquadros/I2C-Pico-USB) which provides USB-to-I2C connectivity.
  - Connection between the hardware dongle and the RTL837x's I2C communication port.

`dec_leds_from_rtl837x_uart.py`, `uart_read_rtl_gpio.py` and
`uart_dump_rtl_regs.py` need no dongle, only the USB-to-serial adapter that is
already used as the switch console.

## Scripts

### 1. `i2c_read_rtl_gpio.py`

This script reads RTL GPIO register values via I2C and displays changes in GPIO states.

**Features:**

  - Reads live RTL GPIO register values via I2C (default address 0x5C)
  - Monitors GPIO changes with delta detection
  - Allows specification of I2C bus, sleep interval, and ignored GPIO pins
  - Shows changes in real-time with GPIO index display

**Usage:**
```bash
# Basic usage (defaults to I2C bus 1, 2s sleep interval)
python3 i2c_read_rtl_gpio.py

# Specify I2C bus
python3 i2c_read_rtl_gpio.py --i2c-bus 0

# Specify sleep interval in seconds
python3 i2c_read_rtl_gpio.py --sleep-interval 5

# Ignore specific GPIO pins
python3 i2c_read_rtl_gpio.py --ignored-ios 28 31 34 44

# Combine options
python3 i2c_read_rtl_gpio.py --i2c-bus 2 --sleep-interval 1 --ignored-ios 28 31
```

**Output Format:**

  - Displays register address and data in hex format
  - Shows GPIO pins that have changed since last read
  - Example: `0044: 00 00 00 00 00 00 00 00`

### 2. `i2c_dump_rtl_regs.py`

This script dumps all register values from an RTL device via I2C.

**Features:**

  - Dumps registers sequentially from address 0x0000 to 0xFFFF
  - Reads 16 bytes at a time for efficiency
  - Configurable I2C bus number
  - Provides complete register dump in hex format

**Usage:**
```bash
# Basic usage (defaults to I2C bus 1)
python3 i2c_dump_rtl_regs.py >reg_dump.txt

# Specify I2C bus
python3 i2c_dump_rtl_regs.py --bus 0 >reg_dump.txt

# Or using short option
python3 i2c_dump_rtl_regs.py -b 2 >reg_dump.txt
```

**Output Format:**

  - Displays address and 16 bytes of data in hex format
  - Example: `0000: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00`

### 3. `dec_leds_from_dump.py`

This script decodes LED configuration from a register dump file ( the output from `i2c_dump_rtl_regs.py`).

**Features:**

  - Parses register dump files (reg_dump.txt format)
  - Decodes LED pad configurations and LED sets
  - Maps LED types to bit positions based on configuration
  - Outputs LED mux configuration and set mappings
  - Decodes the pin mux registers (`PIN_MUX_0/1/2`, `0x7f8c`-`0x7f94`) and
    prints the function of every GPIO pin
  - Decodes the high LEDs (`LED_27`, the system LED `LED_28_SYS` and `LED_29`)
    from `PIN_MUX_0` and `LED_GLB_IO_EN` (`0x65dc`) and prints the
    `.high_leds = { .mux = ..., .enable = ... }` line of a machine definition

**Usage:**
```bash
# Must be run in same directory as reg_dump.txt
python3 dec_leds_from_dump.py
```

**Output Format:**

  - LED pad configuration (hex values for each pad)
  - LED set configurations with descriptions of LED types
  - Port selection mappings
  - Pin mux configuration: the three mux registers, then one row per pin
    with its register and field, the field value and the function it selects
  - High LEDs (`LED_27`, `LED_28_SYS`, `LED_29`): one row per pad with its
    `PIN_MUX_0` bit, its `LED_GLB_IO_EN` enable bit and its function, then the
    `.high_leds` line of a machine definition

**Requirements:**

  - Requires a `reg_dump.txt` file containing the register dump output

### 4. `dec_leds_from_rtl837x_uart.py`

This script decodes the LED configuration from a live switch over its serial
console, using the firmware's own `regget` command - no I2C dongle and no
register dump file. It prints the same report as `dec_leds_from_dump.py`, so it
is the quick way to read the wiring of a device that still runs its stock
firmware.

**Prerequisites:**

  - The console must be free: stop `minicom`/`screen` on that port first.
  - Some boards protect their console with a login/password prompt. The script
    does not know the password and cannot log in for you, so log in on the
    console first (enter the password in your terminal program) and only then
    run the script - on those boards it executes commands once the console
    session is authenticated. If the console is still waiting for a password, it
    stops as soon as the console answers with its login prompt instead of
    retrying, so a run does not turn into a series of failed login attempts.

**Features:**

  - Reads the LED registers with `regget` and prints `.led_mux`, the four LED
    sets and the LED set each port uses
  - Prints the high LEDs (`LED_27`, `LED_28_SYS`, `LED_29`) and the
    `.high_leds` line, the same way as `dec_leds_from_dump.py`
  - Takes the port range from the chip model in register 0x0004: ports 0..8 on
    an RTL8373 (upper 16 bits `0x8373`), ports 3..8 on the RTL8372 boards;
    `--ports` overrides it
  - `--gpio` also dumps the GPIO output/input/direction registers
  - Sends the address as `regget 0x65e0` (falling back to the plain form for
    firmwares whose parser rejects the `0x`) and only accepts an answer that
    names the register it asked for
  - Paces the characters of a command and resends it when the console drops
    one, because the stock console loses input that arrives as one burst

**Usage:**
```bash
# Default console port (/dev/ttyUSB0) and baudrate (57600)
python3 dec_leds_from_rtl837x_uart.py

# Another port, plus the GPIO registers
python3 dec_leds_from_rtl837x_uart.py -p /dev/ttyUSB1 --gpio

# A console that copes with fast input, with a log of every exchange
python3 dec_leds_from_rtl837x_uart.py --char-delay 0 -v
```

**Options:**

  - `-p` / `--port`: serial port (default: `/dev/ttyUSB0`)
  - `-b` / `--baudrate`: console baudrate (default: 57600)
  - `--cmd TEMPLATE`: register read command, repeatable and tried in order
    (default: `regget 0x{addr:04x}`, then `regget {addr:04x}`)
  - `--char-delay`: seconds between the characters of a command (default: 0.05,
    which measured clean on the stock console while 0.03 lost one command in
    eight)
  - `--ports MIN MAX`: port range resolved to LED sets (default: from the chip
    model, see above)
  - `--gpio`: also dump the GPIO registers
  - `--timeout`, `--settle`, `--retries`: console timing, see `--help`
  - `--lenient`: also accept a bare hex value, for firmware that does not name
    the register in its answer (a mangled answer can then be misread)
  - `-v` / `--verbose`: print every console exchange, `-q` / `--quiet`: no progress

**Output Format:**

  - Same report as `dec_leds_from_dump.py`, ready to paste into a machine
    definition, plus the GPIO registers with `--gpio`
  - The port range that was used is reported on stderr, e.g.
    `Decoding ports 0..8 (from model 0x83737000)`

### 5. `uart_read_rtl_gpio.py`

This is the serial-console counterpart of `i2c_read_rtl_gpio.py`: it reads the
GPIO input registers (`GPIO_IN0` at 0x0044 and `GPIO_IN1` at 0x0048) with the
firmware's `regget` command and prints them as bytes followed by the GPIO pins
that changed since the previous read. No I2C dongle is needed, only the console
adapter. The console handling is shared with `dec_leds_from_rtl837x_uart.py`, so
the same `--cmd`, `--char-delay`, `--timeout`, `--settle`, `--retries`,
`--lenient` and `-v` options apply; the console must be free, and on boards that
password-protect it you must log in on the console first (see the prerequisites
of script 4).

**Usage:**
```bash
# Default console port (/dev/ttyUSB0) and baudrate (57600)
python3 uart_read_rtl_gpio.py

# Another port, one second between reads, ignoring extra pins
python3 uart_read_rtl_gpio.py -p /dev/ttyUSB1 -s 1 -i 28 31 34

# Log every console exchange
python3 uart_read_rtl_gpio.py -v
```

**Options:**

  - `-p` / `--port`: serial port (default: `/dev/ttyUSB0`)
  - `-b` / `--baudrate`: console baudrate (default: 57600)
  - `-s` / `--sleep-interval`: seconds between reads (default: 1); each read is
    two `regget` commands, so the console may need longer than this
  - `-i` / `--ignored-ios`: GPIO pins to hide from the change list (default:
    `28 31 32 34 35 42 43 44 45`, the SYS_LED, UART, SMI and SPI pins)
  - the console timing options of script 4, see its section above and `--help`

**Output Format:**

  - Same line per read as `i2c_read_rtl_gpio.py`, followed by the changed pins
  - Example:
    ```
    0044: 01 00 00 00 00 00 00 00
    0044: 81 00 00 00 00 00 01 00
            GPIO7
            GPIO48
    ```

### 6. `uart_dump_rtl_regs.py`

This is the serial-console counterpart of `i2c_dump_rtl_regs.py`: it walks the
register space with `regget` and prints the same 16-bytes-per-line dump, so the
output can be saved as `reg_dump.txt` and decoded with `dec_leds_from_dump.py`.
A console read is much slower than an I2C read - roughly a second per register -
so a full dump of 0x0000-0xffff takes hours. `--start`/`--end` limit it to the
range of interest; the LED and pin mux registers sit around 0x6500-0x7f94.

**Usage:**
```bash
# All registers to reg_dump.txt (takes hours)
python3 uart_dump_rtl_regs.py > reg_dump.txt

# Only the LED and pin-mux registers
python3 uart_dump_rtl_regs.py --start 0x6500 --end 0x7f94 > reg_dump.txt

# Another port, without progress output on stderr
python3 uart_dump_rtl_regs.py -p /dev/ttyUSB1 -q --start 0x6500 --end 0x6600
```

**Options:**

  - `-p` / `--port`: serial port (default: `/dev/ttyUSB0`)
  - `-b` / `--baudrate`: console baudrate (default: 57600)
  - `--start ADDR` / `--end ADDR`: first and last register, 4-byte aligned
    (default: 0x0000 and 0xffff)
  - the console timing options of script 4, plus `-q` / `--quiet` to drop the
    progress output and `-v` / `--verbose` to log every exchange

**Output Format:**

  - Same as `i2c_dump_rtl_regs.py`: address, then 16 bytes per line (fewer on
    the last line), e.g. `6500: 01 00 00 00 ...`

### 7. `probe_leds_from_rtl837x_uart.py`

Maps the LEDs of a board to the GPIO pads that drive them by driving one pin at
a time and asking which LED changed, then decodes the answers into which GPIO
switches which colour and at what level. It needs RTLPlayground firmware, since
it drives the pads with `regset`, and restores the registers it touched when the
run ends.

Usage, answer codes, output and troubleshooting have their own document:
[`probe_leds_from_rtl837x_uart.md`](probe_leds_from_rtl837x_uart.md).

## Requirements

The I2C scripts (1 to 3) require:

  - Python 3
  - `smbus2` Python package

The UART scripts (`dec_leds_from_rtl837x_uart.py`, `uart_read_rtl_gpio.py`,
`uart_dump_rtl_regs.py`, `probe_leds_from_rtl837x_uart.py`) require:

  - Python 3
  - `pyserial`
  - an unlocked switch console: on boards that password-protect it, log in on
    the console before starting the script (see the prerequisites above)

(Depend upon Linux distribution) Install with:
```bash
apt install python3-smbus2 python3-serial
```
OR
```bash
pip3 install smbus2 pyserial
```


## Common Use Cases

`i2c_read_rtl_gpio.py`, `i2c_dump_rtl_regs.py`, `dec_leds_from_rtl837x_uart.py`,
`uart_read_rtl_gpio.py` and `uart_dump_rtl_regs.py` shall run with the
**original** firmware, not RTLPlayground firmware: RTLPlayground overwrites the
LED registers with the machine definition of its build at boot, so reading them
there only shows the definition that is already flashed.


### Monitoring GPIO Changes
```bash
# Monitor GPIO changes on bus 1 with 1-second intervals
python3 i2c_read_rtl_gpio.py --i2c-bus 1 --sleep-interval 1

# Monitor GPIO changes over the serial console, no I2C dongle
python3 uart_read_rtl_gpio.py -p /dev/ttyUSB0
```

### Register Analysis
```bash
# Dump all device registers
python3 i2c_dump_rtl_regs.py --bus 2 > reg_dump.txt

# Dump the LED and pin-mux registers over the serial console instead
python3 uart_dump_rtl_regs.py --start 0x6500 --end 0x7f94 > reg_dump.txt

# Analyze the register dump to understand LED configuration
python3 dec_leds_from_dump.py
```

### LED configuration without an I2C dongle
```bash
# Read the LED and GPIO configuration of the running (stock) firmware
python3 dec_leds_from_rtl837x_uart.py --gpio
```

## Configuration

The I2C scripts support command-line arguments for flexible configuration:

  - `--i2c-bus` or `-b`: Specify I2C bus (default: 1)
  - `--sleep-interval` or `-s`: Sleep between reads in seconds (default: 2)
  - `--ignored-ios` or `-i`: GPIO pins to ignore (default: [28, 31, 34, 44])

The UART scripts (`dec_leds_from_rtl837x_uart.py`, `uart_read_rtl_gpio.py`,
`uart_dump_rtl_regs.py`) have their own options, listed in their sections above
and in `--help`. The options of `probe_leds_from_rtl837x_uart.py` are in its
[own document](probe_leds_from_rtl837x_uart.md) and in `--help`.
