"""System hardware telemetry reporting."""

import shutil
import subprocess
from typing import Any, Dict


def get_hardware_telemetry() -> Dict[str, Any]:
    """Retrieve current hardware telemetry for GPU utilization, VRAM, and temperature."""
    telemetry: Dict[str, Any] = {
        "gpu_available": False,
        "gpu_name": None,
        "gpu_utilization_percent": 0,
        "gpu_memory_used_mb": 0,
        "gpu_memory_total_mb": 0,
        "gpu_temp_c": 0,
    }

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
