# Coil winder

A turn counter for winding air-core inductors with a **Xiaomi electric screwdriver**.
A 3D-printed reduction gear (1/2 or 1/3) keeps the screwdriver from overheating, an
optical sensor counts turns on the driven axle, and an **RP2040-Zero** shows the live
coil-turn count on a **TM1637** 7-segment display.

## Hardware

- **RP2040-Zero** — controller and power hub (USB-C 5 V)
- **Optical encoder/sensor** with comparator amp (slotted disk)
- **TM1637** 4-digit 7-segment display (red)
- Reduction gear between the screwdriver and the coil (3D printed)
- Momentary push button (count reset)

### Wiring

| RP2040-Zero | Connects to            | Notes                                            |
|-------------|------------------------|--------------------------------------------------|
| 5V (USB)    | TM1637 VCC             | Display runs from 5 V for full brightness        |
| GP0         | TM1637 CLK             | Clock (MCU → display)                            |
| GP1         | TM1637 DIO             | Data (MCU ↔ display)                             |
| 3V3         | Optical sensor VCC     | Powers the sensor so OUT swings 0–3.3 V          |
| GP2         | Optical sensor OUT     | Turn pulses (edge interrupt)                      |
| GP3         | Reset button → GND     | Internal pull-up, active-low                      |
| GP16        | Onboard WS2812 RGB LED | Green at idle, purple flash per counted turn      |
| GND         | All device grounds     | Common ground                                    |

> **3.3 V only:** RP2040 GPIO are not 5 V tolerant — power the sensor from **3V3**
> (or add a divider/level shifter on OUT). See [`spec.md`](spec.md) for the full
> schematic and voltage notes.

## Firmware

MicroPython, in [`firmware/`](firmware/):

- **`main.py`** — counts coil turns and drives the display. A reset button on GP3
  zeros the count.
- **`test_count.py`** — calibration helper for `PULSES_PER_REV`.
- **`tm1637.py`** — minimal 4-digit TM1637 driver.

### Anti-chatter counting

The sensor's comparator has no hysteresis, so as a slot edge slowly crosses the beam
its output **chatters** — turned slowly, one slot reads as several counts; turned fast
it reads correctly. The firmware fixes this by counting **one pulse per slot**: a
rising edge is counted only while *armed*, then it disarms and re-arms only after the
line has settled cleanly LOW (driven by a hardware timer). The result is
speed-independent — verified at 40 pulses/coil-turn for both slow and fast winding.

An optional hardware **RC low-pass** on the OUT line (start with R = 1 kΩ, C = 100 nF)
cleans the signal at the source; see the sensor signal note in [`spec.md`](spec.md).

### Key tunables (top of `main.py`)

| Setting            | Meaning                                                            |
|--------------------|-------------------------------------------------------------------|
| `PULSES_PER_REV`   | Sensor pulses per coil turn (40 = 20-slot disk × 2:1 gear)         |
| `COIL_TURNS_NUM/DEN` | Extra gear ratio (1/1 — gearing already folded into the rate)    |
| `REARM_US`         | Line must be settled LOW this long before the next slot counts     |
| `REARM_SAMPLE_HZ`  | Re-arm timer sample rate                                           |
| `RESET_DEBOUNCE_US`| Reset-button debounce                                             |

## Install

1. Flash the [MicroPython UF2](https://micropython.org/download/RPI_PICO/) to the
   RP2040-Zero (hold BOOTSEL, plug in USB, copy the UF2).
2. Copy the firmware to the board, e.g. with [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html):

   ```sh
   mpremote connect /dev/ttyACM0 fs cp firmware/main.py :main.py
   mpremote connect /dev/ttyACM0 fs cp firmware/tm1637.py :tm1637.py
   mpremote connect /dev/ttyACM0 reset
   ```

   `main.py` runs on boot.

## Calibrate

If you change the disk or gearing, re-measure `PULSES_PER_REV`:

```sh
mpremote connect /dev/ttyACM0 run firmware/test_count.py
```

Turn the coil a known number of full turns, then divide the reported count by that
number and put the result in `PULSES_PER_REV`.

## Usage

1. Power the RP2040-Zero over USB-C — the display shows `0`, RGB LED green.
2. Wind the coil; the display tracks turns and the LED flashes purple per turn.
3. Press the reset button to zero the count.
