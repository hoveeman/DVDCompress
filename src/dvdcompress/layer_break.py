"""Automated DVD-9 (Dual-Layer) layer break detection and calculation engine."""

import math
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

# Physical constants for DVD media
DVD_SECTOR_SIZE = 2048
DVD5_MAX_SECTORS = 2295104  # ~4.7 GB (Single Layer)
DVD9_MAX_L0_SECTORS = 2084960  # Maximum capacity of Layer 0 on DVD+R DL / DVD-R DL
ECC_BLOCK_SECTORS = 16  # 1 ECC block = 16 sectors = 32 KB


def parse_vts_ifo_cell_offsets(ifo_bytes: bytes) -> List[int]:
    """
    Parse relative starting sectors of video cells/chapters from VTS_01_0.IFO binary data.

    Reads the Cell Address Table (VTS_C_ADT) pointer at offset 0x00E0 and extracts
    the starting sector (C_FVOBU_SA) for each cell descriptor.
    """
    if len(ifo_bytes) < 0x0100:
        return []

    # Check DVD-Video VTS IFO magic header
    if not ifo_bytes.startswith(b"DVDVIDEO-VTS"):
        return []

    # Offset 0x00E0: Start sector of VTS_C_ADT within IFO (in 2048-byte blocks)
    vts_c_adt_sec = struct.unpack(">I", ifo_bytes[0x00E0:0x00E4])[0]
    table_offset = vts_c_adt_sec * DVD_SECTOR_SIZE

    if table_offset + 8 > len(ifo_bytes):
        return []

    # In DVD-Video VTS_C_ADT header:
    # Offset 0..1: Number of VOBs
    # Offset 2..3: Reserved (0x0000)
    # Offset 4..7: End byte offset of table (relative to VTS_C_ADT start)
    end_byte = struct.unpack(">I", ifo_bytes[table_offset + 4:table_offset + 8])[0]
    num_cells = (end_byte + 1 - 8) // 12 if end_byte >= 19 else 0

    # Fallback to offset 2..3 if end_byte is 0
    if num_cells <= 0:
        raw_num = struct.unpack(">H", ifo_bytes[table_offset + 2:table_offset + 4])[0]
        if raw_num > 0:
            num_cells = raw_num

    cell_offsets: List[int] = []

    for i in range(num_cells):
        entry_offset = table_offset + 8 + (i * 12)
        if entry_offset + 8 > len(ifo_bytes):
            break
        cell_start_sec = struct.unpack(">I", ifo_bytes[entry_offset + 4:entry_offset + 8])[0]
        cell_offsets.append(cell_start_sec)

    return cell_offsets


def _parse_iso_directory_records(data: bytes, dir_size: int) -> Dict[str, Tuple[int, int]]:
    """Parse ISO 9660 directory records from sector bytes and return mapping of name -> (LBA, size)."""
    entries: Dict[str, Tuple[int, int]] = {}
    pos = 0
    total_len = min(len(data), dir_size)

    while pos < total_len:
        # ISO directory records cannot span 2048-byte sector boundaries
        sec_offset = pos % DVD_SECTOR_SIZE
        rec_len = data[pos]

        if rec_len == 0:
            # Skip remainder of this 2048-byte sector
            pos += DVD_SECTOR_SIZE - sec_offset
            continue

        if pos + rec_len > total_len:
            break

        file_lba = struct.unpack("<I", data[pos + 2:pos + 6])[0]
        file_size = struct.unpack("<I", data[pos + 10:pos + 14])[0]
        name_len = data[pos + 32]
        name_raw = data[pos + 33:pos + 33 + name_len]

        if name_raw == b"\x00":
            clean_name = "."
        elif name_raw == b"\x01":
            clean_name = ".."
        else:
            # Strip version numbers like ';1' and whitespace
            clean_name = name_raw.decode("latin-1", errors="ignore").split(";")[0].strip().upper()

        entries[clean_name] = (file_lba, file_size)
        pos += rec_len

    return entries


def extract_vts_info_from_iso(iso_path: str) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Traverse ISO 9660 directory structure to locate VTS_01_1.VOB starting LBA and read VTS_01_0.IFO.

    Returns:
        Tuple of (vts_vob_lba, vts_ifo_bytes) or (None, None) if not found.
    """
    if not os.path.exists(iso_path):
        return None, None

    try:
        with open(iso_path, "rb") as f:
            # Sector 16 is Primary Volume Descriptor (PVD)
            f.seek(16 * DVD_SECTOR_SIZE)
            pvd = f.read(DVD_SECTOR_SIZE)
            if len(pvd) < DVD_SECTOR_SIZE or pvd[1:6] != b"CD001":
                return None, None

            # Root Directory Record at PVD offset 156
            root_rec = pvd[156:190]
            root_lba = struct.unpack("<I", root_rec[2:6])[0]
            root_size = struct.unpack("<I", root_rec[10:14])[0]

            # Read Root Directory
            f.seek(root_lba * DVD_SECTOR_SIZE)
            root_data = f.read(max(root_size, DVD_SECTOR_SIZE))
            root_entries = _parse_iso_directory_records(root_data, root_size)

            video_ts_entry = root_entries.get("VIDEO_TS")
            if not video_ts_entry:
                return None, None

            vts_dir_lba, vts_dir_size = video_ts_entry
            f.seek(vts_dir_lba * DVD_SECTOR_SIZE)
            vts_dir_data = f.read(max(vts_dir_size, DVD_SECTOR_SIZE))
            vts_entries = _parse_iso_directory_records(vts_dir_data, vts_dir_size)

            vob_entry = vts_entries.get("VTS_01_1.VOB")
            ifo_entry = vts_entries.get("VTS_01_0.IFO")

            vob_lba = vob_entry[0] if vob_entry else None
            ifo_bytes = None

            if ifo_entry:
                ifo_lba, ifo_size = ifo_entry
                f.seek(ifo_lba * DVD_SECTOR_SIZE)
                ifo_bytes = f.read(ifo_size)

            return vob_lba, ifo_bytes
    except Exception:
        return None, None


def get_dvd9_layer_break_info(iso_path: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve detailed metadata about the DVD-9 layer break.

    Returns:
        Dict with keys 'sector', 'chapter_index', 'mb', 'percent', 'is_fallback', or None if DVD-5.
    """
    if not os.path.exists(iso_path):
        return None

    total_bytes = os.path.getsize(iso_path)
    total_sectors = total_bytes // DVD_SECTOR_SIZE

    if total_sectors <= DVD5_MAX_SECTORS:
        return None

    half_sectors = math.ceil(total_sectors / 2.0)
    min_l0_sector = int(math.ceil(half_sectors / ECC_BLOCK_SECTORS)) * ECC_BLOCK_SECTORS
    max_l0_sector = DVD9_MAX_L0_SECTORS

    vob_lba, ifo_bytes = extract_vts_info_from_iso(iso_path)

    if vob_lba is not None and ifo_bytes is not None:
        cell_offsets = parse_vts_ifo_cell_offsets(ifo_bytes)
        for idx, offset in enumerate(cell_offsets):
            abs_sec = vob_lba + offset
            ecc_aligned_sec = (abs_sec // ECC_BLOCK_SECTORS) * ECC_BLOCK_SECTORS
            if min_l0_sector <= ecc_aligned_sec <= max_l0_sector:
                return {
                    "sector": ecc_aligned_sec,
                    "chapter_index": idx + 1,
                    "mb": round((ecc_aligned_sec * DVD_SECTOR_SIZE) / (1000 * 1000), 1),
                    "percent": round((ecc_aligned_sec / total_sectors) * 100.0, 1),
                    "is_fallback": False,
                }

    # Fallback to ECC-aligned midpoint if no valid chapter is found
    return {
        "sector": min_l0_sector,
        "chapter_index": None,
        "mb": round((min_l0_sector * DVD_SECTOR_SIZE) / (1000 * 1000), 1),
        "percent": round((min_l0_sector / total_sectors) * 100.0, 1),
        "is_fallback": True,
    }


def calculate_dvd9_layer_break(iso_path: str) -> Optional[int]:
    """
    Calculate the optimal 16-sector ECC-aligned chapter layer break for DVD-9 (Dual-Layer) ISOs.

    Returns:
        Absolute layer break sector number for growisofs (-use-the-force-luke=break:N), or None.
    """
    info = get_dvd9_layer_break_info(iso_path)
    return info["sector"] if info else None


def calculate_dvd9_layer_break_from_dir(author_dir: str, total_sectors: int) -> Optional[int]:
    """
    Calculate DVD-9 layer break from a VIDEO_TS staging directory.

    Returns:
        Optimal 16-sector ECC-aligned chapter break sector within valid window.
    """
    if total_sectors <= DVD5_MAX_SECTORS:
        return None

    half_sectors = math.ceil(total_sectors / 2.0)
    min_l0_sector = int(math.ceil(half_sectors / ECC_BLOCK_SECTORS)) * ECC_BLOCK_SECTORS
    max_l0_sector = DVD9_MAX_L0_SECTORS

    candidate_ifo_paths = [
        os.path.join(author_dir, "VTS_01_0.IFO"),
        os.path.join(author_dir, "VIDEO_TS", "VTS_01_0.IFO"),
    ]

    for ifo_path in candidate_ifo_paths:
        if os.path.exists(ifo_path):
            try:
                with open(ifo_path, "rb") as f:
                    ifo_bytes = f.read()
                cell_offsets = parse_vts_ifo_cell_offsets(ifo_bytes)
                for offset in cell_offsets:
                    ecc_aligned_sec = (offset // ECC_BLOCK_SECTORS) * ECC_BLOCK_SECTORS
                    if min_l0_sector <= ecc_aligned_sec <= max_l0_sector:
                        return ecc_aligned_sec
            except Exception:
                pass

    return min_l0_sector
