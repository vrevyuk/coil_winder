# Coil winder

Coil winder that use electric screw-driver Xiaomi to wind air inductors. To prevent over heating of screw-driver I plan use 3d printed gear.
Rate can be 1/2 or 1/3. Use an optical sensor to counting turns on the folled axe. Supply for display and optical sensor provides by usb-c 5 volt of rp2040.

## Parts
- RP2040-Zero
- Optical encoder/sensor with amp
- 7 segments display based on TM1637 (red, with full column)

## Schematic

The RP2040-Zero is the controller and power hub. It is powered from USB-C (5 V),
reads the optical sensor to count turns, and drives the TM1637 display to show the
count.

```
                          USB-C 5V
                             │
                  ┌──────────┴───────────┐
                  │     RP2040-Zero      │
                  │                      │
   ┌──── 3V3  ────┤ 3V3              5V  ├──── 5V ───┐
   │              │                      │           │
   │   ┌─── GND ──┤ GND             GND  ├─── GND ─┐ │
   │   │          │                      │         │ │
   │   │   CLK ◄──┤ GP0             GP1  ├──► DIO  │ │
   │   │          │                      │         │ │
   │   │   OUT ──►┤ GP2             GP3  ├──┐      │ │
   │   │          └──────────────────────┘  │      │ │
   │   │                                     │      │ │
   │   │            Reset button             │      │ │
   │   │             ┌───o o───┐             │      │ │
   │   │       GP3 ──┤         ├── GND       │      │ │
   │   │             └─────────┘   │         │      │ │
   │   │       (button bridges GP3 to GND)   │      │ │
   │   │                                            │ │
   │   │     ┌───────────────────────┐              │ │
   │   │     │  Optical sensor + amp │              │ │
   └───┼─────┤ VCC                   │              │ │
       └─────┤ GND               OUT ├──► (to GP2)  │ │
             └───────────────────────┘              │ │
                                                    │ │
             ┌───────────────────────┐              │ │
             │   TM1637 7-seg disp.  │              │ │
             │ VCC               CLK ├◄── (GP0)     │ │
        ┌────┤ GND               DIO ├◄── (GP1)     │ │
        │    └──┬────────────────────┘              │ │
        │       └── VCC ◄─────────────────── 5V ────┘ │
        └────────── GND ◄─────────────────────────────┘
```

### Pin mapping

| RP2040-Zero | Connects to            | Notes                                  |
|-------------|------------------------|----------------------------------------|
| 5V (USB)    | TM1637 VCC             | Display runs from 5 V for full brightness |
| GP0         | TM1637 CLK             | Clock line (MCU → display)             |
| GP1         | TM1637 DIO             | Data line (MCU ↔ display)              |
| 3V3         | Optical sensor VCC     | See voltage note below                 |
| GP2         | Optical sensor OUT     | Turn pulses; use edge interrupt to count |
| GP3         | Reset button           | Other side to GND; internal pull-up, active-low |
| GP16        | Onboard WS2812 RGB LED | On-board addressable LED; lit green at startup |
| GND         | TM1637 GND, sensor GND, button | Common ground for all devices  |

### Voltage note

RP2040 GPIO are **3.3 V tolerant only** — do not feed them a 5 V signal. Power the
optical sensor/amp board from the **3V3** rail so its output swings 0–3.3 V and can
drive GP2 directly. If the sensor must run at 5 V, add a divider or level shifter on
the OUT line before GP2.

The TM1637 is driven by the MCU (MCU outputs on CLK/DIO), so the 3.3 V logic levels
are fine even though the display module itself is powered at 5 V.

### Sensor signal note (RC filter)

The optical sensor's comparator has no hysteresis, so as a slot edge slowly crosses
the beam its OUT line **chatters** (oscillates near the threshold). Turned slowly,
this makes one slot read as several counts; turned fast it reads correctly. The
firmware rejects the chatter in software (see below), but a hardware RC low-pass on
the OUT line cleans the signal at the source and is recommended insurance for fast
winding:

```
   sensor OUT ──[ R ]──┬── GP2
                       │
                     [ C ]
                       │
                      GND
```

- Start with **R = 1 kΩ, C = 100 nF** → time constant τ = R·C = 100 µs, −3 dB ≈ 1.6 kHz.
  This smooths the sub-300 µs chatter bursts while passing the real slot rate
  (~tens of Hz when winding) untouched.
- Keep τ well **below** the real slot period at top speed:
  `slot_period_us = 60e6 / (max_coil_rpm * PULSES_PER_REV)`. With 40 pulses/coil-turn
  even 1500 coil-rpm gives a 1000 µs slot period, comfortably above τ = 100 µs.
- If chatter persists, increase C (e.g. 220 nF) or R, or feed the filtered line through
  a Schmitt-trigger input (e.g. 74HC14) for a clean square edge. Adjusting the sensor
  board's threshold potentiometer also helps.

## Firmware

MicroPython, in `firmware/`:

- `main.py` — counts coil turns from GP2 and shows the live count on the TM1637.
  A reset button on GP3 zeros the count. To stay accurate at any speed despite the
  comparator chatter (see the sensor signal note above), it counts **one pulse per
  slot**: a rising edge is counted only while "armed", then it disarms and re-arms
  only after the line has settled LOW for `REARM_US` (re-arm is driven by a hardware
  timer at `REARM_SAMPLE_HZ`). Tunables at the top: `PULSES_PER_REV` (sensor pulses
  per coil turn — 40 here, = 20-slot disk × the 2:1 gear, calibrated directly against
  the coil so the gear ratio is folded in), `COIL_TURNS_NUM`/`COIL_TURNS_DEN` (left
  1/1), `REARM_US`, `REARM_SAMPLE_HZ`, `RESET_DEBOUNCE_US`.
- `test_count.py` — anti-chatter counter used to (re)calibrate `PULSES_PER_REV`:
  turn the coil a known number of turns and divide the reported count.
- `tm1637.py` — minimal 4-digit TM1637 display driver.

Flash the MicroPython UF2 to the RP2040-Zero, then copy both files to the board
(e.g. with `mpremote` or Thonny). `main.py` runs on boot.

## 3D printer files
