"""Unit tests for automated DVD-9 layer break calculation and ISO/IFO binary parsing."""

import os
import struct
import tempfile
import pytest
from dvdcompress.layer_break import (
    parse_vts_ifo_cell_offsets,
    extract_vts_info_from_iso,
    calculate_dvd9_layer_break,
    calculate_dvd9_layer_break_from_dir,
    DVD9_MAX_L0_SECTORS,
    DVD5_MAX_SECTORS,
)


def create_synthetic_vts_ifo(cell_start_sectors: list[int]) -> bytes:
    """Construct a minimal valid synthetic VTS_01_0.IFO binary with VTS_C_ADT."""
    # 2048 bytes header + 2048 bytes for VTS_C_ADT
    ifo = bytearray(4096)
    # Magic identifier
    ifo[0:12] = b"DVDVIDEO-VTS"
    # Offset 0x00E0: VTS_C_ADT starting sector inside IFO (sector 1)
    struct.pack_into(">I", ifo, 0x00E0, 1)

    # Offset 2048: VTS_C_ADT table
    table_offset = 2048
    num_cells = len(cell_start_sectors)
    struct.pack_into(">H", ifo, table_offset + 0, 1)  # 1 VOB
    struct.pack_into(">H", ifo, table_offset + 2, num_cells)  # num cells
    struct.pack_into(">I", ifo, table_offset + 4, 8 + num_cells * 12)  # end byte

    for i, start_sec in enumerate(cell_start_sectors):
        entry_offset = table_offset + 8 + (i * 12)
        struct.pack_into(">H", ifo, entry_offset + 0, 1)  # VOB ID 1
        struct.pack_into("B", ifo, entry_offset + 2, i + 1)  # Cell ID
        struct.pack_into("B", ifo, entry_offset + 3, 0)  # Reserved
        struct.pack_into(">I", ifo, entry_offset + 4, start_sec)  # Start sector
        struct.pack_into(">I", ifo, entry_offset + 8, start_sec + 1000)  # End sector

    return bytes(ifo)


def create_synthetic_iso9660_dvd(
    total_size_bytes: int,
    vts_vob_lba: int,
    ifo_bytes: bytes,
) -> bytes:
    """Create a mock ISO 9660 filesystem image with PVD, VIDEO_TS, VTS_01_0.IFO, and VTS_01_1.VOB."""
    ifo_sectors = (len(ifo_bytes) + 2047) // 2048
    ifo_lba = 19

    iso = bytearray(max(total_size_bytes, (vts_vob_lba + 10) * 2048))

    # PVD at Sector 16
    pvd_offset = 16 * 2048
    iso[pvd_offset] = 1  # PVD
    iso[pvd_offset + 1:pvd_offset + 6] = b"CD001"
    iso[pvd_offset + 6] = 1

    # Root directory record at pvd_offset + 156 (34 bytes)
    root_rec = pvd_offset + 156
    iso[root_rec] = 34  # length
    struct.pack_into("<I", iso, root_rec + 2, 17)  # LBA 17 (Little Endian)
    struct.pack_into(">I", iso, root_rec + 6, 17)  # LBA 17 (Big Endian)
    struct.pack_into("<I", iso, root_rec + 10, 2048)  # Size 2048
    struct.pack_into(">I", iso, root_rec + 14, 2048)
    iso[root_rec + 25] = 2  # Directory flag
    iso[root_rec + 32] = 1
    iso[root_rec + 33] = 0  # root

    # Root dir at Sector 17: contains VIDEO_TS entry
    r_offset = 17 * 2048
    # Entry 1: VIDEO_TS directory
    vts_dir_entry_len = 34 + 8  # 42 bytes
    iso[r_offset] = vts_dir_entry_len
    struct.pack_into("<I", iso, r_offset + 2, 18)  # LBA 18
    struct.pack_into(">I", iso, r_offset + 6, 18)
    struct.pack_into("<I", iso, r_offset + 10, 2048)
    struct.pack_into(">I", iso, r_offset + 14, 2048)
    iso[r_offset + 25] = 2  # Directory
    iso[r_offset + 32] = 8  # Name length
    iso[r_offset + 33:r_offset + 41] = b"VIDEO_TS"

    # VIDEO_TS dir at Sector 18: contains VTS_01_0.IFO and VTS_01_1.VOB
    vts_dir_offset = 18 * 2048
    # Entry 1: VTS_01_0.IFO
    ifo_name = b"VTS_01_0.IFO;1"
    ifo_rec_len = 33 + len(ifo_name)
    if ifo_rec_len % 2 == 1:
        ifo_rec_len += 1
    iso[vts_dir_offset] = ifo_rec_len
    struct.pack_into("<I", iso, vts_dir_offset + 2, ifo_lba)
    struct.pack_into(">I", iso, vts_dir_offset + 6, ifo_lba)
    struct.pack_into("<I", iso, vts_dir_offset + 10, len(ifo_bytes))
    struct.pack_into(">I", iso, vts_dir_offset + 14, len(ifo_bytes))
    iso[vts_dir_offset + 25] = 0  # Regular file
    iso[vts_dir_offset + 32] = len(ifo_name)
    iso[vts_dir_offset + 33:vts_dir_offset + 33 + len(ifo_name)] = ifo_name

    # Entry 2: VTS_01_1.VOB
    vob_rec_offset = vts_dir_offset + ifo_rec_len
    vob_name = b"VTS_01_1.VOB;1"
    vob_rec_len = 33 + len(vob_name)
    if vob_rec_len % 2 == 1:
        vob_rec_len += 1
    iso[vob_rec_offset] = vob_rec_len
    struct.pack_into("<I", iso, vob_rec_offset + 2, vts_vob_lba)
    struct.pack_into(">I", iso, vob_rec_offset + 6, vts_vob_lba)
    struct.pack_into("<I", iso, vob_rec_offset + 10, 1024 * 1024 * 1024)
    struct.pack_into(">I", iso, vob_rec_offset + 14, 1024 * 1024 * 1024)
    iso[vob_rec_offset + 25] = 0
    iso[vob_rec_offset + 32] = len(vob_name)
    iso[vob_rec_offset + 33:vob_rec_offset + 33 + len(vob_name)] = vob_name

    # Write IFO bytes at ifo_lba
    iso[ifo_lba * 2048:(ifo_lba * 2048) + len(ifo_bytes)] = ifo_bytes

    return bytes(iso)


def test_parse_vts_ifo_cell_offsets():
    """Verify parsing relative cell offsets from VTS_01_0.IFO bytes."""
    expected_cells = [0, 100000, 500000, 1354800, 1470000]
    ifo_bytes = create_synthetic_vts_ifo(expected_cells)
    parsed = parse_vts_ifo_cell_offsets(ifo_bytes)
    assert parsed == expected_cells


def test_extract_vts_info_from_iso():
    """Verify ISO9660 filesystem parser extracts VTS_01_1.VOB LBA and IFO bytes."""
    expected_cells = [0, 500000, 1354800]
    ifo_bytes = create_synthetic_vts_ifo(expected_cells)
    vob_lba = 300
    iso_bytes = create_synthetic_iso9660_dvd(
        total_size_bytes=6000000,
        vts_vob_lba=vob_lba,
        ifo_bytes=ifo_bytes,
    )

    with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
        f.write(iso_bytes)
        iso_path = f.name

    try:
        extracted_vob_lba, extracted_ifo = extract_vts_info_from_iso(iso_path)
        assert extracted_vob_lba == vob_lba
        assert extracted_ifo is not None
        assert parse_vts_ifo_cell_offsets(extracted_ifo) == expected_cells
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)


def test_calculate_dvd9_layer_break_returns_none_for_dvd5():
    """DVD-5 ISOs (<= 4.7 GB) do not require a layer break."""
    with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
        f.seek(4300 * 1000 * 1000 - 1)
        f.write(b"\0")
        iso_path = f.name

    try:
        break_sector = calculate_dvd9_layer_break(iso_path)
        assert break_sector is None
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)


def test_calculate_dvd9_layer_break_selects_first_valid_chapter():
    """DVD-9 ISO selects the first chapter/cell sector in the valid layer break window [Total/2 .. 2084960]."""
    total_size = 5461936128
    cell_offsets = [0, 100000, 500000, 1000000, 1310000, 1354800, 1470000]
    ifo_bytes = create_synthetic_vts_ifo(cell_offsets)
    vob_lba = 304  # multiple of 16

    iso_bytes = create_synthetic_iso9660_dvd(
        total_size_bytes=total_size,
        vts_vob_lba=vob_lba,
        ifo_bytes=ifo_bytes,
    )

    with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
        f.write(iso_bytes)
        f.seek(total_size - 1)
        f.write(b"\0")
        iso_path = f.name

    try:
        break_sector = calculate_dvd9_layer_break(iso_path)
        assert break_sector is not None
        # Chapter 13 absolute sector: 304 + 1354800 = 1355104
        assert break_sector == 1355104
        assert break_sector >= 1333488
        assert break_sector <= DVD9_MAX_L0_SECTORS
        assert break_sector % 16 == 0
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)


def test_calculate_dvd9_layer_break_fallback_on_corrupt_or_empty_ifo():
    """If ISO has no valid chapters or IFO is missing, fallback to 16-sector aligned midpoint."""
    total_size = 5461936128
    with tempfile.NamedTemporaryFile(suffix=".iso", delete=False) as f:
        f.seek(total_size - 1)
        f.write(b"\0")
        iso_path = f.name

    try:
        break_sector = calculate_dvd9_layer_break(iso_path)
        assert break_sector is not None
        # Midpoint of 2,666,961 sectors is 1,333,481 -> ECC 16 aligned is 1,333,488
        assert break_sector == 1333488
        assert break_sector % 16 == 0
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)


def test_calculate_dvd9_layer_break_from_dir():
    """Verify calculating layer break from a VIDEO_TS staging directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vts_dir = os.path.join(tmpdir, "VIDEO_TS")
        os.makedirs(vts_dir)
        ifo_path = os.path.join(vts_dir, "VTS_01_0.IFO")

        cell_offsets = [0, 500000, 1000000, 1355008, 1500000]
        ifo_bytes = create_synthetic_vts_ifo(cell_offsets)
        with open(ifo_path, "wb") as f:
            f.write(ifo_bytes)

        total_sectors = 2666961
        break_sector = calculate_dvd9_layer_break_from_dir(vts_dir, total_sectors)
        assert break_sector is not None
        assert break_sector == 1355008
        assert break_sector % 16 == 0
