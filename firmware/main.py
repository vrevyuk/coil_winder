"""Coil winder firmware (RP2040-Zero, MicroPython).

Counts turns from the optical sensor and shows the live count on a TM1637
7-segment display. Pin assignments match spec.md / the schematic.

Counting method (anti-chatter):
    The optical comparator has no hysteresis, so as a slot edge slowly crosses
    the beam its output CHATTERS (oscillates) near the threshold. A plain per-
    edge counter therefore over-counts at slow speed (1 turn read as 2-4) while
    reading correctly when turned fast. To be speed-independent we count ONE
    pulse per slot: a rising edge is counted only while 'armed', then we disarm
    and re-arm only after the line has settled cleanly LOW for REARM_US. Chatter
    never holds a sustained low, so it is ignored. Re-arming is done from a
    hardware timer so it stays accurate even while the display is being written.
    (A hardware fix -- adding hysteresis via the sensor's threshold pot, an RC
    filter, or a 74HC14 Schmitt trigger on OUT -- would let a plain counter work
    too, and is worth doing if you ever wind fast enough to drop counts.)

Wiring (RP2040-Zero):
    GP0  -> TM1637 CLK
    GP1  -> TM1637 DIO
    GP2  -> Optical sensor OUT (pulse per slot)
    GP3  -> Reset button (other side to GND)
    3V3  -> sensor VCC      5V -> TM1637 VCC      GND -> common
"""

from machine import Pin, Timer
from neopixel import NeoPixel
from time import ticks_us, ticks_diff, ticks_ms, ticks_add, sleep_ms
import tm1637

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PIN_CLK = 0          # TM1637 clock
PIN_DIO = 1          # TM1637 data
PIN_SENSOR = 2       # optical sensor output
PIN_RESET = 3        # reset button to GND
PIN_RGB = 16         # onboard WS2812 RGB LED (RP2040-Zero)

# Colors for the RGB LED, as (R, G, B), 0-255 each. Kept dim so the single
# onboard LED isn't blinding.
RGB_START_COLOR = (0, 40, 0)    # green: shown at startup / idle between turns
RGB_TURN_COLOR = (40, 0, 40)    # purple: flashed briefly on each counted turn

# How long the purple flash stays on per counted turn, in milliseconds.
RGB_BLINK_MS = 60

# Sensor pulses per ONE full turn of the COIL (output) axle. Measured on
# 2026-06-20 with the anti-chatter counter (firmware/test_count.py): 10 slow
# turns -> 400, 10 fast turns -> 401, i.e. 40 pulses/coil-turn. That matches the
# hardware: a 20-slot disk on the screwdriver axle x the 2:1 (50/25) gear = 40.
# Because it is measured against the coil, the gear ratio is already folded in.
# Re-calibrate with firmware/test_count.py if the disk or gearing changes.
PULSES_PER_REV = 40

# Gear ratio is already baked into PULSES_PER_REV above (calibrated directly
# against the coil), so this stays 1/1.
COIL_TURNS_NUM = 1
COIL_TURNS_DEN = 1

# Anti-chatter re-arm: after a slot is counted, the next slot is only counted
# once the sensor line has been settled LOW for at least this long. It must be
# LONGER than the comparator's chatter bursts (<300 us observed) and SHORTER
# than the real low-gap between slots at top winding speed:
#   min_low_us ~= 60e6 / (max_coil_rpm * PULSES_PER_REV) / 2
# At 500 us this is comfortable for any hand/screwdriver winding speed here.
REARM_US = 500

# Rate at which the timer samples the line to re-arm, in Hz (2000 Hz = 500 us).
REARM_SAMPLE_HZ = 2000

# Debounce window for the reset button press, in microseconds.
RESET_DEBOUNCE_US = 50000

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_pulse_count = 0           # counted slots since reset
_armed = True              # True when ready to count the next slot's rising edge
_last_edge_us = 0          # timestamp of the most recent sensor transition
_last_reset_us = 0         # timestamp of last accepted reset press
_sensor = None             # Pin object, shared with the re-arm timer ISR


def _on_edge(pin):
    """ISR (both edges): count one slot per armed rising edge, then disarm.

    Every transition refreshes _last_edge_us so the timer can tell when the
    line has truly settled. Chatter edges arrive while disarmed and are ignored.
    """
    global _pulse_count, _armed, _last_edge_us
    _last_edge_us = ticks_us()
    if _armed and pin.value():          # armed + rising == start of a real slot
        _pulse_count += 1
        _armed = False


def _rearm_tick(t):
    """Timer ISR: re-arm once the line has been settled LOW past REARM_US."""
    global _armed
    if (not _armed and _sensor.value() == 0
            and ticks_diff(ticks_us(), _last_edge_us) > REARM_US):
        _armed = True


def turns():
    """Coil turns derived from counted slots, with the gear ratio folded in.

    coil_turns = slots / PULSES_PER_REV * (COIL_TURNS_NUM / COIL_TURNS_DEN)

    Done as integer math so the displayed count never drifts from rounding.
    """
    return (_pulse_count * COIL_TURNS_NUM) // (PULSES_PER_REV * COIL_TURNS_DEN)


def reset(pin=None):
    """Zero the counter. Usable as a button ISR or called directly."""
    global _pulse_count, _last_reset_us, _armed
    if pin is not None:                      # debounce button presses
        now = ticks_us()
        if ticks_diff(now, _last_reset_us) < RESET_DEBOUNCE_US:
            return
        _last_reset_us = now
    _pulse_count = 0
    _armed = True


def main():
    global _sensor

    # Light the onboard RGB LED green to signal the firmware is up.
    rgb = NeoPixel(Pin(PIN_RGB), 1)
    rgb[0] = RGB_START_COLOR
    rgb.write()

    display = tm1637.TM1637(clk=Pin(PIN_CLK), dio=Pin(PIN_DIO))
    display.brightness(5)

    _sensor = Pin(PIN_SENSOR, Pin.IN, Pin.PULL_UP)
    _sensor.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_on_edge)

    button = Pin(PIN_RESET, Pin.IN, Pin.PULL_UP)
    button.irq(trigger=Pin.IRQ_FALLING, handler=reset)

    # Drive re-arm from a hardware timer so counting stays accurate even while
    # the main loop is busy bit-banging the display.
    Timer(freq=REARM_SAMPLE_HZ, mode=Timer.PERIODIC, callback=_rearm_tick)

    last_shown = -1
    blink_off_at = 0       # when to revert the purple flash to green
    blinking = False
    while True:
        count = turns()
        if count != last_shown:
            display.number(count % 10000)   # display is 4 digits
            last_shown = count
            # Flash purple to mark the new turn; revert to green later.
            rgb[0] = RGB_TURN_COLOR
            rgb.write()
            blinking = True
            blink_off_at = ticks_add(ticks_ms(), RGB_BLINK_MS)
        elif blinking and ticks_diff(ticks_ms(), blink_off_at) >= 0:
            rgb[0] = RGB_START_COLOR
            rgb.write()
            blinking = False
        sleep_ms(10)


if __name__ == "__main__":
    main()
