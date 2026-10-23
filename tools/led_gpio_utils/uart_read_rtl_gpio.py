#!/usr/bin/env python3
"""Watch the GPIO inputs of a live RTL837x switch over its serial console.

This is the serial-console counterpart of ``i2c_read_rtl_gpio.py``: instead of
polling the GPIO input registers over I2C, it reads them with the firmware's own
``regget`` command, so it needs no dongle - only the USB-to-serial adapter that
is already used as the switch console. It prints the same lines: the input
registers as bytes followed by the GPIO pins that changed since the last read.

The console handling (paced characters, retries, login-prompt detection and the
two accepted ``regget`` forms) comes from ``dec_leds_from_rtl837x_uart.py``.

Notes on the console:

  * The stock console drops characters when a command arrives as one burst, so
    the characters are paced (``--char-delay``). A command that was not echoed
    back intact is sent again.
  * The console must be free - stop minicom/screen on the port first.
  * Some boards protect their console with a login/password prompt. The script
    cannot log in for you, so log in on the console first and run it afterwards;
    a console that is still waiting for a password is reported instead of being
    fed a whole run of commands.

Requirements: Python 3, pyserial (``apt install python3-serial``).
"""

import argparse
import sys
import time

from dec_leds_from_rtl837x_uart import ConsoleError, RtlConsole, read_registers

# GPIO input registers, named as in rtl837x_regs.h. GPIO_IN0 holds GPIO0..31,
# GPIO_IN1 GPIO32..63 - the same two words i2c_read_rtl_gpio.py reads from
# address 0x0044.
GPIO_IN0 = 0x0044
GPIO_IN1 = 0x0048
INPUT_REGS = [GPIO_IN0, GPIO_IN1]

# Handle command line arguments for ignored IOs
# default to ignore IOs related to SYS_LED, UART, SMI, SPI
IGNORED_IOS = [28, 31, 32, 34, 35, 42, 43, 44, 45]
SLEEP_INTERVAL = 1


def read_inputs(console):
    """The GPIO_IN0/GPIO_IN1 words, read with the console's regget."""
    values = read_registers(console, INPUT_REGS, quiet=True)
    return [values[GPIO_IN0], values[GPIO_IN1]]


def format_inputs(words):
    """The input words as bytes, least significant first, as I2C prints them."""
    return " ".join(
        f"{(word >> (8 * byte)) & 0xFF:02x}" for word in words for byte in range(4)
    )


def changed_gpios(delta_words, ignored_ios):
    """The GPIO pins whose input bit changed since the previous read."""
    changed = []
    for word_index, delta in enumerate(delta_words):
        for bit in range(32):
            if delta & (1 << bit):
                gpio = word_index * 32 + bit
                if gpio not in ignored_ios:
                    changed.append(gpio)
    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Read RTL GPIO input registers over the switch's serial console"
    )
    parser.add_argument(
        "-p",
        "--port",
        default="/dev/ttyUSB0",
        help="serial port of the switch console (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=57600,
        help="console baudrate (default: 57600)",
    )
    parser.add_argument(
        "-s",
        "--sleep-interval",
        type=float,
        default=SLEEP_INTERVAL,
        help=f"sleep interval in seconds (default: {SLEEP_INTERVAL})",
    )
    parser.add_argument(
        "-i",
        "--ignored-ios",
        nargs="*",
        type=int,
        default=IGNORED_IOS,
        help=f"list of GPIO pins to ignore (default: {IGNORED_IOS})",
    )
    parser.add_argument(
        "--cmd",
        action="append",
        metavar="TEMPLATE",
        help="register read command, {addr} is replaced by the hex address; "
        "repeatable, the forms are tried in order until one answers "
        "(default: 'regget 0x{addr:04x}', then 'regget {addr:04x}')",
    )
    parser.add_argument(
        "--char-delay",
        type=float,
        default=0.05,
        help="seconds between the characters of a command; the stock console "
        "drops characters if a command arrives as one burst, 0.05 measured "
        "clean while 0.03 lost one in eight (default: 0.05)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="seconds to wait for a command answer (default: 5)",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=0.4,
        help="quiet seconds that end an answer without a prompt (default: 0.4)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=4,
        help="attempts per register, the console can drop a command (default: 4)",
    )
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="also accept a bare hex value, for firmware that does not name the "
        "register in its answer; a mangled answer can be misread as a value",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print every console exchange on stderr",
    )
    args = parser.parse_args()

    cmds = args.cmd or ["regget 0x{addr:04x}", "regget {addr:04x}"]
    for template in cmds:
        if "{addr" not in template:
            parser.error(f"--cmd {template!r} has no {{addr}} placeholder")
    if not 0 <= args.char_delay <= 1:
        parser.error("--char-delay must be between 0 and 1 second")
    if args.settle > args.timeout:
        parser.error("--settle must not be larger than --timeout")

    try:
        console = RtlConsole(
            args.port,
            args.baudrate,
            cmds,
            args.char_delay,
            args.timeout,
            args.settle,
            args.retries,
            args.verbose,
            args.lenient,
        )
    except ConsoleError as exc:
        sys.exit(f"error: {exc}")

    first_read = True
    last_data = [0 for _ in INPUT_REGS]
    try:
        console.drain()
        while True:
            new_data = read_inputs(console)
            if first_read:
                delta_data = [0 for _ in INPUT_REGS]
                first_read = False
            else:
                delta_data = [new ^ old for new, old in zip(new_data, last_data)]
            last_data = new_data

            deltastr = "".join(
                f"\n{'  ':8s}GPIO{gpio}"
                for gpio in changed_gpios(delta_data, args.ignored_ios)
            )
            print(f"{GPIO_IN0:04x}: {format_inputs(new_data)}{deltastr}", flush=True)
            time.sleep(args.sleep_interval)
    except ConsoleError as exc:
        sys.exit(f"error: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        console.close()


if __name__ == "__main__":
    main()
