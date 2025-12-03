# Reward_Feedback_Pointing_2025

A motor learning experiment investigating the effects of reward feedback vs. visual feedback on pointing accuracy using a touchscreen interface with PLATO goggles for vision manipulation.

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Hardware Requirements](#hardware-requirements)
- [Running the Experiment](#running-the-experiment)
- [Default Experiment Structure](#default-experiment-structure)
- [Experimental Conditions](#experimental-conditions)
- [Configuration](#configuration)
- [Data Output](#data-output)

## Requirements

This project requires [KLibs](https://github.com/a-hurst/klibs), a Python framework for running behavioral experiments.

Version numbers are those used during development; older versions would likely work fine.

- Python 3.13 or higher
- [KLibs](https://github.com/a-hurst/klibs)
- pyfirmata >= 1.1.0 (for Arduino communication)

## Installation

```bash
# Clone the repository
git clone https://github.com/brettfeltmate/Reward_Feedback_Pointing_2025.git
cd Reward_Feedback_Pointing_2025

# Dependencies can be installed from uv.lock file:
uv sync

# Alternative with pip:
pip install git+https://github.com/a-hurst/klibs.git
pip install pyfirmata>=1.1.0
```

For more information about KLibs, see the [KLibs documentation](https://github.com/a-hurst/klibs).

## Hardware Requirements

- **Touchscreen monitor** - For participant responses (mouse input also works)
- **PLATO goggles** - Liquid crystal shutter glasses for vision manipulation
- **Arduino board** - Controls PLATO goggles via serial communication

NOTE: Arduino sketch is required to control the goggles.
TODO: Find & add Arduino sketch to repo.

## Hardware Setup

### Arduino Configuration

- Program Arduino to receive serial commands for goggle control
- Baudrate: 9600
- Commands: `b'55'` (open goggles), `b'56'` (close goggles)

NOTE: 55/56 refer to the pins used on our Arduino setup; adjust as necessary.

### Serial Port Configuration

The default serial port is set to `COM6` (Windows). You may need to adjust this based on your system:

- **Windows**: Check Device Manager → Ports (COM & LPT) to find your Arduino's COM port
- **macOS/Linux**: Check `/dev/tty*` devices. Common ports:
  - macOS: `/dev/tty.usbserial-*` or `/dev/tty.usbmodem-*`
  - Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`

To find your Arduino's port:

```bash
# macOS/Linux
ls /dev/tty.*  # or /dev/ttyUSB* on Linux

# Or use Python:
python -m serial.tools.list_ports
```

Update the port in `experiment.py:69` (line with `COM6 = 'COM6'`) to match your system's Arduino port.

## Running the Experiment

```bash
# Run with vision condition first
klibs run <display diagonal size; inches> -c vision
# or -c reward

# e.g.,
klibs run 27 -c reward
```

**Important:** The `-c` (condition) flag is **required** and determines the order of experimental conditions.

If wanting to pilot/test, without contaminating participant database, use `-d` or `--development` flag:

```bash
klibs run 27 -d -c vision
```

## Default Experiment Structure

- **Total trials:** 400 (8 blocks × 50 trials)
- **Practice trials:** 20 (disabled when run with -d)
- **Conditions:** 2 (vision, reward) - alternating across 6 blocks each (3 repetitions)

## Experimental Conditions

### Reward Condition

- Goggles close when movement begins (no vision during movement)
- Goggles reopen after trial completion
- Feedback shows points gained/lost and cumulative score
- No visual information about target location or movement endpoint

### Vision Condition

- Full vision throughout trial (goggles remain open)
- No feedback about points or score
- Visual information about target and movement endpoint provided

### Scoring

| Outcome | Points |
|---------|--------|
| Reward target hit | +100 |
| Penalty target hit | -600 |
| Overlap (both targets) | -500 |
| Miss (rectangle only) | 0 |
| Outside rectangle | 0 |
| Timeout (no response) | -700 |

## Configuration

Structural parameters defined in:
`ExpAssets/Config/reward_feedback_pointing_2025_params.py`

Defaults:

- `trials_per_block = 50`
- `blocks_per_experiment = 8`
- `trials_per_practice_block = 20`
- `feedback_duration = 2` (seconds)
- `run_practice_blocks = True`
- `view_distance = 57` (cm from screen)

## Data Output

Trial data is automatically saved to an SQLite database in the project's `Data` directory, including:

- **Timing data:** Reaction time and movement time
- **Spatial data:** Target locations and response coordinates  
- **Performance data:** Trial earnings and cumulative block earnings
- **Condition information:** Vision vs. reward feedback condition
- **Trial metadata:** Block number, trial number, practice vs. testing

To export data as CSV:

```bash
klibs export
```

Will create a CSV per participant, under Data/
Subsequent exports will only create files as necessary (i.e., new participants).
