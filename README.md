# AP230 Magnetometer

A lightweight desktop app for live three-axis magnetic-field readings. It
shows the current X/Y/Z values and total magnitude, graphs the latest 300
samples, records measurements to CSV, and saves a graph image as PNG.

## Run on Windows

Install Python 3.10 or newer, then run these commands in PowerShell from this
folder:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Run on Ubuntu / Linux

Install Python, Tkinter, and pip using your distribution's package manager.
On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-tk python3-venv python3-pip
```

Then, from this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

If the sensor appears as `/dev/ttyUSB0` or `/dev/ttyACM0` but cannot be
opened, add your user to the serial-device group and sign in again:

```bash
sudo usermod -a -G dialout "$USER"
```

## Build a standalone app

PyInstaller builds for the operating system on which it is run; it does not
cross-compile. Build a separate app on Windows and Ubuntu/Linux.

From an active Python environment with the requirements installed, build on
the target operating system:

```powershell
.\build_windows.ps1
```

On Ubuntu/Linux:

```bash
bash build_linux.sh
```

On Windows the executable is created at `dist/AP230-Magnetometer.exe`. On
Ubuntu/Linux it is created at `dist/AP230-Magnetometer`. The Linux binary
requires a graphical desktop and its system Tk libraries. You can copy each
platform's build to other machines running a compatible OS; do not copy a
Windows executable to Linux or vice versa.

## Use

Connect the sensor, select its serial port and baud rate, then click
**Connect**. Use **Refresh** after plugging in the sensor. **Record CSV**
opens a save dialog and starts recording; click **Stop recording** when done.
The CSV has timestamp, elapsed seconds, X, Y, Z, and magnitude columns.
**Save graph PNG** saves the currently visible axes and recent samples to an
image. The values are shown above the graph while it is running.

## Serial format

The reader expects one human-readable ASCII line per sample containing at
least three numbers, in X, Y, Z order. Commas, spaces, and labels are
accepted, for example:

```text
X=12.3, Y=-4.5, Z=38.0
```

The initial baud rate is 9600 and can be changed in the app. The AP230 model
name alone does not establish its baud rate, units, or wire protocol. If the
device sends binary packets or needs a setup command, the device manual or a
sample of its serial output is needed to adapt the reader.
