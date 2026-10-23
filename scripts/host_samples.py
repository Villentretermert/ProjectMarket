"""Windows host sampling for load evidence; shared-machine CPU/RAM, not process isolation."""

import ctypes
import os
import shutil
import threading
from datetime import UTC, datetime
from typing import Any


class Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong)
        for name in (
            "total",
            "available",
            "total_page",
            "available_page",
            "total_virtual",
            "available_virtual",
            "available_extended",
        )
    ]


class HostSamples:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.samples: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        if os.name != "nt":
            return
        # Windows FILETIME can be read as a 64-bit counter of 100ns ticks.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        previous: tuple[int, int] | None = None
        while not self.stop.is_set():
            idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
            if not kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            ):
                return
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            if not kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                return
            total = kernel.value + user.value
            cpu = None
            if previous and total > previous[1]:
                cpu = 100 * (1 - (idle.value - previous[0]) / (total - previous[1]))
            previous = idle.value, total
            self.samples.append(
                {
                    "time": datetime.now(UTC).isoformat(),
                    "cpu_percent": cpu,
                    "total_ram_bytes": memory.total,
                    "available_ram_bytes": memory.available,
                    "disk_free_bytes": shutil.disk_usage(os.getcwd()).free,
                }
            )
            self.stop.wait(5)

    def start(self) -> None:
        self.thread.start()

    def finish(self) -> list[dict[str, Any]]:
        self.stop.set()
        self.thread.join(timeout=6)
        return self.samples
