#!/usr/bin/env python3
"""Dump the registers of a live RTL837x switch over its serial console.

This is the serial-console counterpart of ``i2c_dump_rtl_regs.py``: instead of
reading the registers over I2C, it uses the firmware's own ``regget`` command,
so it needs no dongle - only the USB-to-serial adapter that is already used as
the switch console. The lines it prints have the same layout as the I2C dump
(address, then the register bytes least significant first, 16 bytes per line),
so the output can be saved as ``reg_dump.txt`` and decoded with
``dec_leds_from_dump.py``.

A console read is slow: ``regget`` needs its characters paced and an answer per
register, so a full dump of 0x0000-0xffff takes hours. ``--start``/``--end``
restrict it to the range of interest (the LED and pin-mux registers live around
0x6500-0x7f94).

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

from dec_leds_from_rtl837x_uart import ConsoleError, RtlConsole

# Addresses are 32 bit registers, four bytes per register. One output line holds
# 16 bytes, the same as one read of i2c_dump_rtl_regs.py.
REG_BYTES = 4
NUM_BYTES = 16


def word_bytes(word):
    """The four bytes of a register, least significant first."""
    return [(word >> (8 * byte)) & 0xFF for byte in range(REG_BYTES)]


def register_bytes(console, first, last):
    """Read registers first..last and return their bytes, least significant first."""
    data = []
    for addr in range(first, last + 1, REG_BYTES):
        data += word_bytes(console.regget(addr))
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Dump RTL registers over the switch's serial console",
        epilog="A full dump (0x0000-0xffff) takes hours at console speed; "
        "--start/--end restrict it to the registers of interest.",
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
        "--start",
        type=lambda value: int(value, 16),
        default=0x0000,
        metavar="ADDR",
        help="first register to dump (default: 0x0000)",
    )
    parser.add_argument(
        "--end",
        type=lambda value: int(value, 16),
        default=0xFFFC,
        metavar="ADDR",
        help="last register to dump (default: 0xffff)",
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
        "-q",
        "--quiet",
        action="store_true",
        help="no progress output on stderr",
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
    for name in ("start", "end"):
        addr = getattr(args, name)
        if not 0 <= addr <= 0xFFFF or addr % REG_BYTES:
            parser.error(
                f"--{name} must be a 4-byte aligned register address "
                "between 0x0000 and 0xffff"
            )
    if args.start > args.end:
        parser.error("--start must not be larger than --end")

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

    try:
        console.drain()
        if not args.quiet:
            registers = (args.end - args.start) // REG_BYTES + 1
            estimate = registers * (args.char_delay * 12 + 0.15)
            if estimate >= 3600:
                duration = f"{estimate / 3600:.1f} h"
            elif estimate >= 60:
                duration = f"{estimate / 60:.0f} min"
            else:
                duration = f"{estimate:.0f} s"
            print(
                f"Dumping 0x{args.start:04x}-0x{args.end:04x} "
                f"({registers} registers) from {args.port} at "
                f"{args.baudrate} baud, about {duration} ...",
                file=sys.stderr,
            )
        for base in range(args.start, args.end + 1, NUM_BYTES):
            last = min(base + NUM_BYTES, args.end + 1) - 1
            if not args.quiet:
                print(
                    f"\rDumping 0x{base:04x} ...", file=sys.stderr, end="", flush=True
                )
            data = register_bytes(console, base, last)
            datastr = " ".join(f"{x:02x}" for x in data)
            print(f"{base:04x}: {datastr}", flush=True)
        if not args.quiet:
            print("\r" + " " * 40 + "\r", file=sys.stderr, end="")
    except ConsoleError as exc:
        sys.exit(f"error: {exc}")
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        console.close()


if __name__ == "__main__":
    main()
