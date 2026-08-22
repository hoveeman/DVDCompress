"""Optical drive discovery and disc burning manager for DVDCompress."""

import glob
import os
import re
import subprocess
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from dvdcompress.layer_break import calculate_dvd9_layer_break


class OpticalDrive(BaseModel):
    device_path: str
    sg_device: Optional[str] = None
    vendor: str = "Generic"
    model: str = "Optical Writer"
    is_writable: bool = True
    media_status: str = "Ready"


def parse_lsscsi_output(output: str) -> List[OpticalDrive]:
    """Parse lsscsi -g output for cd/dvd devices and associated generic SCSI nodes."""
    drives = []
    for line in output.strip().splitlines():
        if "cd/dvd" in line:
            parts = line.split()
            # Find /dev/sr* and /dev/sg*
            sr_dev = next((p for p in parts if p.startswith("/dev/sr")), None)
            sg_dev = next((p for p in parts if p.startswith("/dev/sg")), None)
            if sr_dev:
                vendor = parts[2] if len(parts) > 2 else "Generic"
                model = " ".join(parts[3:5]) if len(parts) > 4 else "Drive"
                drives.append(
                    OpticalDrive(
                        device_path=sr_dev,
                        sg_device=sg_dev,
                        vendor=vendor,
                        model=model,
                    )
                )
    return drives


def scan_optical_drives() -> List[OpticalDrive]:
    """Discover attached optical drives using lsscsi or /dev/sr* device node fallback."""
    # Try lsscsi first
    try:
        res = subprocess.run(["lsscsi", "-g"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            drives = parse_lsscsi_output(res.stdout)
            if drives:
                return drives
    except Exception:
        pass

    # Fallback to checking /dev/sr*
    found = []
    for dev in sorted(glob.glob("/dev/sr*")):
        found.append(
            OpticalDrive(
                device_path=dev,
                vendor="Standard",
                model=os.path.basename(dev),
            )
        )
    return found


def build_burn_command(
    device_path: str,
    iso_path: str,
    speed: int = 4,
    is_bluray: bool = False,
    layer_break_sector: Optional[int] = None,
) -> List[str]:
    """Generate command line arguments for growisofs (DVD) or cdrskin (Blu-ray)."""
    if is_bluray:
        return [
            "cdrskin",
            "-v",
            f"dev={device_path}",
            f"speed={speed}",
            "gracetime=2",
            "-dao",
            iso_path,
        ]
    else:
        # Auto-calculate DVD-9 layer break if not explicitly provided
        lb = layer_break_sector
        if lb is None and os.path.exists(iso_path):
            lb = calculate_dvd9_layer_break(iso_path)

        cmd = [
            "growisofs",
            "-dvd-compat",
            f"-speed={speed}",
        ]
        if lb is not None:
            cmd.append(f"-use-the-force-luke=break:{lb}")

        cmd.extend([
            "-Z",
            f"{device_path}={iso_path}",
        ])
        return cmd


def parse_burn_progress_line(line: str) -> Dict[str, Any]:
    """Parse real-time progress, speed, and time remaining from growisofs / cdrskin output."""
    res = {}
    # Match growisofs percentage: " ( 3.1%) @3.9x, remaining 14:12"
    m = re.search(r"\(\s*([\d\.]+)%\)\s*@([\d\.]+)x.*?remaining\s*([\d:]+)", line)
    if m:
        res["percent"] = float(m.group(1))
        res["speed"] = f"{m.group(2)}x"
        res["remaining"] = m.group(3)
        return res

    # Match cdrskin progress: "Track 01:   25 of  450 MB written (fifo 100%)"
    m2 = re.search(r"(\d+)\s+of\s+(\d+)\s+MB written", line)
    if m2:
        written = float(m2.group(1))
        total = float(m2.group(2))
        res["percent"] = round((written / total) * 100.0, 1) if total > 0 else 0.0

    return res
