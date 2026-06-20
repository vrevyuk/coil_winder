"""Test the anti-chatter 'settle-low' counter.

Counts ONE pulse per slot: a rising edge counts only when 'armed'; after a count
we disarm and only re-arm once the line has been settled LOW for REARM_US. The
comparator's edge chatter never holds a sustained low, so it is ignored.

Goal of the test: slow and fast turns of the same N turns should give the SAME
count (unlike the per-edge counter, which inflates on slow turns).
"""
from machine import Pin
from time import ticks_us, ticks_ms, ticks_diff

REARM_US = 500          # line must be quiet-LOW this long before next slot counts

count = 0
armed = True
last_edge_us = 0

def _on_edge(pin):
    # Fires on BOTH edges. last_edge_us tracks the most recent transition so the
    # main loop can tell when the line has truly settled.
    global count, armed, last_edge_us
    last_edge_us = ticks_us()
    if armed and pin.value():       # armed + rising == the start of a real slot
        count += 1
        armed = False

sensor = Pin(2, Pin.IN, Pin.PULL_UP)
sensor.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_on_edge)

print("READY -- turn N full COIL turns; auto-stops 3s after you stop")
prev = 0
started = False
idle_ms = ticks_ms()
while True:
    # Re-arm once the line is settled LOW (tight poll so fast turns aren't missed).
    if not armed and sensor.value() == 0 and ticks_diff(ticks_us(), last_edge_us) > REARM_US:
        armed = True
    if count != prev:
        prev = count
        started = True
        idle_ms = ticks_ms()
    if started and ticks_diff(ticks_ms(), idle_ms) > 3000:
        break
print("DONE count =", count)
