"""Minimal TM1637 4-digit 7-segment driver for MicroPython.

Subset of the well-known mcauser/micropython-tm1637 driver (MIT) covering
exactly what the coil winder needs: brightness, integer display, and the
column/colon segment. Drop-in: place next to main.py on the RP2040.
"""

from machine import Pin
from time import sleep_us

TM1637_CMD1 = const(0x40)   # data command: auto address increment
TM1637_CMD2 = const(0xC0)   # address command: start at digit 0
TM1637_CMD3 = const(0x80)   # display control command base
TM1637_DSP_ON = const(0x08) # display on bit

# Segment maps for 0-9 (bit order: .GFEDCBA)
_SEGMENTS = bytearray(
    b'\x3F\x06\x5B\x4F\x66\x6D\x7D\x07\x7F\x6F'
)


class TM1637:
    def __init__(self, clk, dio, brightness=7):
        self.clk = clk
        self.dio = dio
        self._brightness = brightness & 0x07
        self.clk.init(Pin.OUT, value=0)
        self.dio.init(Pin.OUT, value=0)
        self._write_data_cmd()
        self._write_dsp_ctrl()

    # --- low level ---------------------------------------------------------
    def _start(self):
        self.dio(0)
        self.clk(0)

    def _stop(self):
        self.dio(0)
        self.clk(1)
        self.dio(1)

    def _write_byte(self, b):
        for _ in range(8):
            self.dio(b & 1)
            sleep_us(1)
            self.clk(1)
            sleep_us(1)
            self.clk(0)
            b >>= 1
        # ack
        self.clk(0)
        sleep_us(1)
        self.clk(1)
        sleep_us(1)
        self.clk(0)

    def _write_data_cmd(self):
        self._start()
        self._write_byte(TM1637_CMD1)
        self._stop()

    def _write_dsp_ctrl(self):
        self._start()
        self._write_byte(TM1637_CMD3 | TM1637_DSP_ON | self._brightness)
        self._stop()

    # --- public API --------------------------------------------------------
    def brightness(self, val):
        self._brightness = max(0, min(7, val))
        self._write_data_cmd()
        self._write_dsp_ctrl()

    def write(self, segments, pos=0):
        self._write_data_cmd()
        self._start()
        self._write_byte(TM1637_CMD2 | (pos & 0x03))
        for seg in segments:
            self._write_byte(seg)
        self._stop()
        self._write_dsp_ctrl()

    def number(self, num, colon=False):
        """Display an integer right-aligned across the 4 digits."""
        num = max(0, min(9999, int(num)))
        digits = bytearray(4)
        for i in range(3, -1, -1):
            digits[i] = _SEGMENTS[num % 10]
            num //= 10
        if colon:
            digits[1] |= 0x80   # column/colon bit on second digit
        self.write(digits)
