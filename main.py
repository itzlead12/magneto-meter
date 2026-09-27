"""Live three-axis magnetometer plotter for USB serial devices."""

from __future__ import annotations

import csv
import math
import queue
import re
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
HISTORY_LENGTH = 300
PLOT_COLORS = ("#ff6b6b", "#54d6a0", "#69aafc")
PLOT_BACKGROUND = "#131d26"
GRID_COLOR = "#2b3945"
TEXT_COLOR = "#94a3b2"


def parse_reading(line: str) -> tuple[float, float, float] | None:
    """Read three numeric axis values from one ASCII line."""
    values = NUMBER.findall(line)
    if len(values) < 3:
        return None
    try:
        return float(values[-3]), float(values[-2]), float(values[-1])
    except ValueError:
        return None


def save_graph_png(
    path: str | Path,
    samples: list[tuple[float, float, float]],
    width: int = 1400,
    height: int = 800,
) -> None:
    """Save the current three-axis graph as a standalone PNG image."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), PLOT_BACKGROUND)
    draw = ImageDraw.Draw(image)
    left, right, top, bottom = 86, width - 36, 74, height - 74
    draw.text((left, 24), "MAGNETIC FIELD COMPONENTS", fill=TEXT_COLOR)
    for axis, color, offset in zip(("X", "Y", "Z"), PLOT_COLORS, (0, 48, 96)):
        draw.line((right - 210 + offset, 34, right - 184 + offset, 34), fill=color, width=4)
        draw.text((right - 178 + offset, 26), axis, fill=color)

    if not samples:
        draw.text((width // 2 - 110, height // 2), "No readings to plot yet", fill=TEXT_COLOR)
        image.save(path, format="PNG")
        return

    low = min(min(row) for row in samples)
    high = max(max(row) for row in samples)
    if math.isclose(low, high):
        padding = max(abs(low) * 0.1, 1.0)
        low, high = low - padding, high + padding
    else:
        padding = (high - low) * 0.12
        low, high = low - padding, high + padding

    for index in range(5):
        fraction = index / 4
        y = round(top + (bottom - top) * fraction)
        value = high - (high - low) * fraction
        draw.line((left, y, right, y), fill=GRID_COLOR, width=1)
        draw.text((8, y - 7), f"{value:.2f}", fill=TEXT_COLOR)

    draw.text((left, height - 42), "Oldest", fill=TEXT_COLOR)
    draw.text((right - 34, height - 42), "Newest", fill=TEXT_COLOR)
    count = len(samples)
    for axis, color in enumerate(PLOT_COLORS):
        points = [
            (
                round(left + (right - left) * index / max(count - 1, 1)),
                round(bottom - (row[axis] - low) / (high - low) * (bottom - top)),
            )
            for index, row in enumerate(samples)
        ]
        if len(points) > 1:
            draw.line(points, fill=color, width=3)
        elif points:
            x, y = points[0]
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)

    image.save(path, format="PNG")


class MagnetometerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AP230 Magnetometer")
        self.root.geometry("940x660")
        self.root.minsize(760, 520)
        self.root.configure(bg="#101820")

        self.samples: deque[tuple[float, float, float]] = deque(maxlen=HISTORY_LENGTH)
        self.readings: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.reader_thread: threading.Thread | None = None
        self.csv_file = None
        self.csv_writer: csv.writer | None = None
        self.started_at = 0.0
        self.connected = False

        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="9600")
        self.status_var = tk.StringVar(value="Disconnected")
        self.value_vars = [tk.StringVar(value="—") for _ in range(3)]
        self.magnitude_var = tk.StringVar(value="—")
        self.sample_count_var = tk.StringVar(value="0 samples")

        self._style()
        self._build_ui()
        self._refresh_ports()
        self.root.after(50, self._process_readings)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#101820")
        style.configure("TLabel", background="#101820", foreground="#e6edf3")
        style.configure("TButton", padding=(12, 8))
        style.configure("TCombobox", padding=5)

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        ttk.Label(header, text="AP230 Magnetometer", font=("Segoe UI", 20, "bold"),
                  foreground="#54d6a0").pack(anchor="w")

        controls = ttk.Frame(self.root, padding=(20, 10))
        controls.pack(fill="x")
        ttk.Label(controls, text="Serial port").pack(side="left")
        self.port_box = ttk.Combobox(controls, textvariable=self.port_var, width=18, state="readonly")
        self.port_box.pack(side="left", padx=(8, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_ports).pack(side="left")
        ttk.Label(controls, text="Baud rate").pack(side="left", padx=(18, 6))
        ttk.Combobox(controls, textvariable=self.baud_var, width=10,
                     values=("9600", "19200", "38400", "57600", "115200")).pack(side="left")
        self.connect_button = ttk.Button(controls, text="Connect", command=self._connect)
        self.connect_button.pack(side="left", padx=(14, 6))
        self.disconnect_button = ttk.Button(controls, text="Disconnect", command=self._disconnect, state="disabled")
        self.disconnect_button.pack(side="left")
        self.record_button = ttk.Button(controls, text="Record CSV", command=self._record, state="disabled")
        self.record_button.pack(side="left", padx=(6, 0))
        ttk.Button(controls, text="Save graph PNG", command=self._save_graph).pack(side="left", padx=(6, 0))

        cards = ttk.Frame(self.root, padding=(20, 8))
        cards.pack(fill="x")
        names = ("X AXIS", "Y AXIS", "Z AXIS", "TOTAL FIELD")
        variables = [*self.value_vars, self.magnitude_var]
        for index, (name, variable) in enumerate(zip(names, variables)):
            card = tk.Frame(cards, bg="#192632", padx=16, pady=12)
            card.pack(side="left", fill="both", expand=True, padx=(0 if index == 0 else 8, 0))
            tk.Label(card, text=name, bg="#192632", fg="#94a3b2",
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            color = PLOT_COLORS[index] if index < 3 else "#f4c95d"
            tk.Label(card, textvariable=variable, bg="#192632", fg=color,
                     font=("Consolas", 20, "bold")).pack(anchor="w", pady=(5, 0))

        chart_panel = tk.Frame(self.root, bg="#192632", padx=12, pady=10)
        chart_panel.pack(fill="both", expand=True, padx=20, pady=(8, 12))
        legend = tk.Frame(chart_panel, bg="#192632")
        legend.pack(fill="x", pady=(0, 8))
        tk.Label(legend, text="LIVE GRAPH", bg="#192632", fg="#94a3b2",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        for axis, color in zip(("X", "Y", "Z"), PLOT_COLORS):
            tk.Label(legend, text=f"● {axis}", bg="#192632", fg=color,
                     font=("Segoe UI", 9, "bold")).pack(side="right", padx=(12, 0))
        self.canvas = tk.Canvas(chart_panel, bg="#131d26", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_plot())

        footer = ttk.Frame(self.root, padding=(20, 0, 20, 14))
        footer.pack(fill="x")
        self.status_label = ttk.Label(footer, textvariable=self.status_var, foreground="#94a3b2")
        self.status_label.pack(side="left")
        ttk.Label(footer, textvariable=self.sample_count_var,
                  foreground="#718096").pack(side="right")

    def _refresh_ports(self) -> None:
        try:
            from serial.tools import list_ports
        except ImportError:
            self.status_var.set("Install dependencies with: pip install -r requirements.txt")
            return
        ports = list(list_ports.comports())
        self.port_box["values"] = [port.device for port in ports]
        if ports and self.port_var.get() not in self.port_box["values"]:
            self.port_var.set(ports[0].device)
        elif not ports:
            self.port_var.set("")
            if not self.connected:
                self.status_var.set("No serial ports found — connect the sensor and refresh")

    def _connect(self) -> None:
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("Select a port", "Connect the magnetometer and select its serial port.")
            return
        try:
            baud_rate = int(self.baud_var.get())
            if baud_rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid baud rate", "Enter a positive integer baud rate.")
            return
        self.stop_event.clear()
        self.started_at = time.monotonic()
        self.reader_thread = threading.Thread(target=self._read_serial, args=(port, baud_rate), daemon=True)
        self.reader_thread.start()
        self.connected = True
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="normal")
        self.record_button.configure(state="normal")
        self.status_var.set(f"Connecting to {port} at {baud_rate} baud…")
        self.status_label.configure(foreground="#f4c95d")

    def _read_serial(self, port: str, baud_rate: int) -> None:
        try:
            import serial

            with serial.Serial(port, baud_rate, timeout=0.5) as device:
                self.readings.put(("status", f"Connected · {port} · {baud_rate} baud"))
                while not self.stop_event.is_set():
                    line = device.readline().decode("ascii", errors="replace").strip()
                    if not line:
                        continue
                    reading = parse_reading(line)
                    if reading is not None:
                        self.readings.put(("data", reading))
        except ImportError:
            self.readings.put(("error", "pyserial is not installed. Run: pip install -r requirements.txt"))
        except Exception as error:
            self.readings.put(("error", f"Serial error: {error}"))

    def _process_readings(self) -> None:
        try:
            while True:
                kind, payload = self.readings.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                    self.status_label.configure(foreground="#54d6a0")
                elif kind == "data":
                    reading = payload
                    assert isinstance(reading, tuple)
                    self.samples.append(reading)
                    self.sample_count_var.set(f"{len(self.samples)} / {HISTORY_LENGTH} samples")
                    for variable, value in zip(self.value_vars, reading):
                        variable.set(f"{value:.3f}")
                    magnitude = math.sqrt(sum(value * value for value in reading))
                    self.magnitude_var.set(f"{magnitude:.3f}")
                    if self.csv_writer is not None:
                        elapsed = time.monotonic() - self.started_at
                        self.csv_writer.writerow((datetime.now().isoformat(timespec="milliseconds"),
                                                  f"{elapsed:.3f}", *reading, f"{magnitude:.6f}"))
                        self.csv_file.flush()
                    self._draw_plot()
                elif kind == "error":
                    self._disconnect()
                    self.status_var.set(str(payload))
                    self.status_label.configure(foreground="#ff6b6b")
        except queue.Empty:
            pass
        self.root.after(50, self._process_readings)

    def _record(self) -> None:
        if self.csv_writer is not None:
            self._stop_recording()
            return
        path = filedialog.asksaveasfilename(
            title="Save magnetometer readings",
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),),
            initialfile=f"magnetometer-{datetime.now():%Y%m%d-%H%M%S}.csv",
        )
        if not path:
            return
        try:
            self.csv_file = Path(path).open("w", newline="", encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Could not save CSV", str(error))
            return
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(("timestamp", "elapsed_seconds", "x", "y", "z", "magnitude"))
        self.record_button.configure(text="Stop recording")
        self.status_var.set(f"Recording to {path}")

    def _stop_recording(self) -> None:
        if self.csv_file is not None:
            self.csv_file.close()
        self.csv_file = None
        self.csv_writer = None
        self.record_button.configure(text="Record CSV")
        if self.connected:
            self.status_var.set("Connected · CSV recording stopped")

    def _save_graph(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save graph image",
            defaultextension=".png",
            filetypes=(("PNG image", "*.png"),),
            initialfile=f"magnetometer-graph-{datetime.now():%Y%m%d-%H%M%S}.png",
        )
        if not path:
            return
        try:
            save_graph_png(path, list(self.samples))
        except ImportError:
            messagebox.showerror(
                "Missing dependency",
                "PNG export needs Pillow. Install it with: python -m pip install -r requirements.txt",
            )
            return
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not save graph", str(error))
            return
        self.status_var.set(f"Graph saved to {path}")

    def _disconnect(self) -> None:
        self.stop_event.set()
        self.connected = False
        self.connect_button.configure(state="normal")
        self.disconnect_button.configure(state="disabled")
        self.record_button.configure(state="disabled")
        self._stop_recording()
        if self.status_var.get().startswith(("Connected", "Connecting")):
            self.status_var.set("Disconnected")
            self.status_label.configure(foreground="#94a3b2")

    def _draw_plot(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 20 or height < 20:
            return
        left, right, top, bottom = 62, width - 18, 18, height - 34
        if right <= left or bottom <= top:
            return
        values = list(self.samples)
        if not values:
            canvas.create_text(width / 2, height / 2, text="Connect to the sensor to see live readings",
                               fill="#718096", font=("Segoe UI", 12))
            return
        low = min(min(row) for row in values)
        high = max(max(row) for row in values)
        if math.isclose(low, high):
            padding = max(abs(low) * 0.1, 1.0)
            low, high = low - padding, high + padding
        else:
            padding = (high - low) * 0.12
            low, high = low - padding, high + padding
        for index in range(5):
            fraction = index / 4
            y = top + (bottom - top) * fraction
            label = high - (high - low) * fraction
            canvas.create_line(left, y, right, y, fill="#2b3945")
            canvas.create_text(left - 8, y, text=f"{label:.2f}", fill="#94a3b2",
                               anchor="e", font=("Consolas", 8))
        canvas.create_text(14, (top + bottom) / 2, text="Field", fill="#94a3b2",
                           angle=90, font=("Segoe UI", 9))
        count = len(values)
        for axis, color in enumerate(PLOT_COLORS):
            points: list[float] = []
            for index, row in enumerate(values):
                x = left + (right - left) * index / max(count - 1, 1)
                y = bottom - (row[axis] - low) / (high - low) * (bottom - top)
                points.extend((x, y))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, smooth=False)
            elif points:
                canvas.create_oval(points[0] - 3, points[1] - 3, points[0] + 3, points[1] + 3,
                                   fill=color, outline=color)

    def _close(self) -> None:
        self._disconnect()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MagnetometerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
