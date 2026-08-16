import pytest
from unittest.mock import patch, MagicMock
from dvdcompress.burner import (
    OpticalDrive,
    build_burn_command,
    parse_burn_progress_line,
    parse_lsscsi_output,
    scan_optical_drives,
)

SAMPLE_LSSCSI = """
[0:0:0:0]    disk    ATA      Samsung SSD 870  1B6Q  /dev/sda 
[1:0:0:0]    cd/dvd  HL-DT-ST BD-RE WH16NS40   1.05  /dev/sr0  /dev/sg0
"""

SAMPLE_LSSCSI_MULTIPLE = """
[0:0:0:0]    disk    ATA      Samsung SSD 870  1B6Q  /dev/sda 
[1:0:0:0]    cd/dvd  HL-DT-ST BD-RE WH16NS40   1.05  /dev/sr0  /dev/sg0
[2:0:0:0]    cd/dvd  ASUS     BW-16D1HT        1.01  /dev/sr1  /dev/sg1
"""


def test_parse_lsscsi_drives():
    drives = parse_lsscsi_output(SAMPLE_LSSCSI)
    assert len(drives) == 1
    assert drives[0].device_path == "/dev/sr0"
    assert drives[0].sg_device == "/dev/sg0"
    assert drives[0].vendor == "HL-DT-ST"
    assert "WH16NS40" in drives[0].model


def test_parse_lsscsi_multiple_drives():
    drives = parse_lsscsi_output(SAMPLE_LSSCSI_MULTIPLE)
    assert len(drives) == 2
    assert drives[0].device_path == "/dev/sr0"
    assert drives[1].device_path == "/dev/sr1"
    assert drives[1].vendor == "ASUS"


def test_parse_lsscsi_no_optical():
    output = "[0:0:0:0]    disk    ATA      Samsung SSD 870  1B6Q  /dev/sda"
    drives = parse_lsscsi_output(output)
    assert len(drives) == 0


def test_build_dvd_burn_command():
    cmd = build_burn_command("/dev/sr0", "/output/disc.iso", speed=4, is_bluray=False)
    cmd_str = " ".join(cmd)
    assert "growisofs" in cmd_str
    assert "-dvd-compat" in cmd_str
    assert "-speed=4" in cmd_str
    assert "/dev/sr0=/output/disc.iso" in cmd_str


def test_build_bluray_burn_command():
    cmd = build_burn_command("/dev/sr0", "/output/disc.iso", speed=2, is_bluray=True)
    cmd_str = " ".join(cmd)
    assert "cdrskin" in cmd_str
    assert "dev=/dev/sr0" in cmd_str
    assert "speed=2" in cmd_str
    assert "-dao" in cmd_str


def test_parse_growisofs_progress():
    line = " 143523840/4699979776 ( 3.1%) @3.9x, remaining 14:12 RBU 100.0% UBU   4.2%"
    prog = parse_burn_progress_line(line)
    assert prog["percent"] == 3.1
    assert prog["speed"] == "3.9x"
    assert prog["remaining"] == "14:12"


def test_parse_cdrskin_progress():
    line = "Track 01:   25 of  450 MB written (fifo 100%)"
    prog = parse_burn_progress_line(line)
    assert prog["percent"] == 5.6


def test_parse_burn_progress_unrecognized_line():
    line = "Executing 'builtin_dd if=/output/disc.iso of=/dev/sr0 obs=32k seek=0'"
    prog = parse_burn_progress_line(line)
    assert prog == {}


def test_scan_optical_drives_lsscsi():
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = SAMPLE_LSSCSI
    with patch("subprocess.run", return_value=mock_res):
        drives = scan_optical_drives()
        assert len(drives) == 1
        assert drives[0].device_path == "/dev/sr0"


def test_scan_optical_drives_fallback():
    with patch("subprocess.run", side_effect=FileNotFoundError("lsscsi not found")):
        with patch("glob.glob", return_value=["/dev/sr0"]):
            drives = scan_optical_drives()
            assert len(drives) == 1
            assert drives[0].device_path == "/dev/sr0"
            assert drives[0].vendor == "Standard"
