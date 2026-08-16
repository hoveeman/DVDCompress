"""System hardware telemetry reporting for CPU, RAM, and GPU."""

import os
import shutil
import subprocess
from typing import Any, Dict


def get_hardware_telemetry() -> Dict[str, Any]:
    """Retrieve current hardware telemetry for CPU, RAM, and GPU utilization."""
    cpu_percent = 0.0
    ram_used_gb = 0.0
    ram_total_gb = 0.0
    ram_percent = 0.0

    # Collect CPU and RAM metrics
    try:
        import psutil

        cpu_percent = round(psutil.cpu_percent(interval=None), 1)
        mem = psutil.virtual_memory()
        ram_used_gb = round(mem.used / (1024**3), 1)
        ram_total_gb = round(mem.total / (1024**3), 1)
        ram_percent = round(mem.percent, 1)
    except Exception:
        # Fallback reading from /proc/meminfo on Linux
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0])
                total_kb = meminfo.get("MemTotal", 0)
                avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
                used_kb = total_kb - avail_kb
                ram_total_gb = round(total_kb / (1024 * 1024), 1)
                ram_used_gb = round(used_kb / (1024 * 1024), 1)
                ram_percent = round((used_kb / total_kb) * 100.0, 1) if total_kb > 0 else 0.0
        except Exception:
            pass

        try:
            load1, _, _ = os.getloadavg()
            cpu_percent = round((load1 / (os.cpu_count() or 1)) * 100.0, 1)
        except Exception:
            pass

    telemetry: Dict[str, Any] = {
        "cpu_percent": cpu_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "ram_percent": ram_percent,
        "gpu_available": False,
        "gpu_name": None,
        "gpu_utilization_percent": 0,
        "gpu_memory_used_mb": 0,
        "gpu_memory_total_mb": 0,
        "gpu_temp_c": 0,
    }

    # Collect NVIDIA GPU metrics if nvidia-smi is present
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                first_line = res.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in first_line.split(",")]
                if len(parts) >= 5:
                    telemetry["gpu_available"] = True
                    telemetry["gpu_name"] = parts[0]
                    telemetry["gpu_utilization_percent"] = int(float(parts[1]))
                    telemetry["gpu_memory_used_mb"] = int(float(parts[2]))
                    telemetry["gpu_memory_total_mb"] = int(float(parts[3]))
                    telemetry["gpu_temp_c"] = int(float(parts[4]))
        except Exception:
            pass

    return telemetry
