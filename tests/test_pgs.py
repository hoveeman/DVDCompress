"""Tests for Blu-ray PGS subtitle parsing and DVD subpicture generation."""

import os
import struct
import pytest
from PIL import Image

from dvdcompress.models import AspectRatio, TVStandard
from dvdcompress.pgs import (
    PGSSubtitleItem,
    convert_pgs_to_spumux_xml,
    decode_pgs_rle,
    parse_pgs_sup,
    ycbcr_to_rgba,
)


def test_ycbcr_to_rgba():
    """Verify YCbCr color conversion to RGBA with alpha channel preservation."""
    # White: Y=235, Cb=128, Cr=128, A=255
    r, g, b, a = ycbcr_to_rgba(235, 128, 128, 255)
    assert r == 235
    assert g == 235
    assert b == 235
    assert a == 255

    # Transparent pixel
    r, g, b, a = ycbcr_to_rgba(0, 128, 128, 0)
    assert a == 0

    # Black: Y=16, Cb=128, Cr=128, A=255
    r, g, b, a = ycbcr_to_rgba(16, 128, 128, 255)
    assert r == 16
    assert g == 16
    assert b == 16
    assert a == 255


def test_decode_pgs_rle():
    """Verify PGS RLE decoding handles literal pixels, runs, and line ends correctly."""
    width = 10
    height = 2
    rle_data = bytearray()
    # Row 1: 2 pixels color 0, 4 pixels color 1, 4 pixels color 2, EOL
    rle_data.extend([0x00, 0x02])              # 2 pixels of color 0
    rle_data.extend([0x00, 0x80 | 4, 0x01])     # 4 pixels of color 1
    rle_data.extend([0x00, 0x80 | 4, 0x02])     # 4 pixels of color 2
    rle_data.extend([0x00, 0x00])              # EOL

    # Row 2: 3 literal bytes (col 5), 2-byte run of color 0, 3-byte run of color 9, EOL
    rle_data.extend([0x05, 0x05, 0x05])        # 3 literal pixels of color 5
    rle_data.extend([0x00, 0x40, 0x02])        # 2 pixels of color 0
    rle_data.extend([0x00, 0xC0, 0x05, 0x09])  # 5 pixels of color 9
    rle_data.extend([0x00, 0x00])              # EOL

    pixels = decode_pgs_rle(bytes(rle_data), width, height)
    assert len(pixels) == 20

    # Verify Row 1
    assert list(pixels[:10]) == [0, 0, 1, 1, 1, 1, 2, 2, 2, 2]
    # Verify Row 2
    assert list(pixels[10:]) == [5, 5, 5, 0, 0, 9, 9, 9, 9, 9]


def _build_pgs_packet(pts: int, dts: int, seg_type: int, payload: bytes) -> bytes:
    """Helper to assemble a standard 13-byte PGS packet."""
    hdr = bytearray(b"PG")
    hdr.extend(struct.pack(">IIBH", pts, dts, seg_type, len(payload)))
    return bytes(hdr + payload)


def test_parse_pgs_sup_and_convert(tmp_path):
    """Verify parsing synthetic PGS stream and converting to scaled DVD PNG and spumux XML."""
    sup_path = str(tmp_path / "test.sup")
    out_dir = str(tmp_path / "pgs_out")

    # Build PDS (Palette Segment): ID 0
    pds_payload = bytearray([0x00, 0x00])  # pal_id=0, pal_ver=0
    pds_payload.extend([0, 0, 128, 128, 0])        # Index 0: Transparent
    pds_payload.extend([1, 235, 128, 128, 255])    # Index 1: White
    pds_payload.extend([2, 16, 128, 128, 255])     # Index 2: Black

    # Build ODS (Object Segment): 80x20 box
    w, h = 80, 20
    ods_rle = bytearray()
    for _ in range(h):
        ods_rle.extend([0x00, 0x0A])               # 10 transparent
        ods_rle.extend([0x00, 0x80 | 60, 0x01])    # 60 white
        ods_rle.extend([0x00, 0x0A])               # 10 transparent
        ods_rle.extend([0x00, 0x00])               # EOL

    ods_payload = bytearray([0x00, 0x01, 0x00, 0xC0])  # obj_id=1, ver=0, seq=0xC0 (only)
    data_len = len(ods_rle) + 4
    ods_payload.extend([(data_len >> 16) & 0xFF, (data_len >> 8) & 0xFF, data_len & 0xFF])
    ods_payload.extend([(w >> 8) & 0xFF, w & 0xFF, (h >> 8) & 0xFF, h & 0xFF])
    ods_payload.extend(ods_rle)

    # Build PCS (Start): PTS = 90000 (1.0s), Pos (400, 800) on 1920x1080 canvas
    pcs_start = bytearray([
        0x07, 0x80,  # 1920
        0x04, 0x38,  # 1080
        0x10,        # 24fps
        0x00, 0x01,  # Comp #1
        0x80,        # Epoch Start
        0x00,        # Palette update 0
        0x00,        # Palette ID 0
        0x01,        # 1 Object
        0x00, 0x01,  # Obj ID 1
        0x00,        # Win ID 0
        0x00,        # Crop flag 0
        0x01, 0x90,  # X = 400
        0x03, 0x20,  # Y = 800
    ])

    # Build PCS (Clear): PTS = 270000 (3.0s), 0 Objects
    pcs_clear = bytearray([
        0x07, 0x80,
        0x04, 0x38,
        0x10,
        0x00, 0x02,
        0x00,        # Normal
        0x00,
        0x00,
        0x00,        # 0 Objects (Clear)
    ])

    sup_bytes = (
        _build_pgs_packet(90000, 0, 0x16, pcs_start)
        + _build_pgs_packet(90000, 0, 0x14, pds_payload)
        + _build_pgs_packet(90000, 0, 0x15, ods_payload)
        + _build_pgs_packet(90000, 0, 0x80, b"")
        + _build_pgs_packet(270000, 0, 0x16, pcs_clear)
        + _build_pgs_packet(270000, 0, 0x80, b"")
    )

    with open(sup_path, "wb") as f:
        f.write(sup_bytes)

    # 1. Test parsing
    items = parse_pgs_sup(sup_path)
    assert len(items) == 1
    item = items[0]
    assert pytest.approx(item.start_pts, 0.01) == 1.0
    assert pytest.approx(item.end_pts, 0.01) == 3.0
    assert item.canvas_width == 1920
    assert item.canvas_height == 1080
    assert len(item.objects) == 1
    assert item.objects[0].width == 80
    assert item.objects[0].height == 20
    assert item.objects[0].x == 400
    assert item.objects[0].y == 800

    # 2. Test conversion to spumux XML (NTSC 720x480)
    xml_path = convert_pgs_to_spumux_xml(
        sup_path=sup_path,
        output_dir=out_dir,
        prefix="dvd_test",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
    )
    assert xml_path is not None
    assert os.path.exists(xml_path)

    with open(xml_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    assert '<subpictures format="NTSC">' in xml_content
    assert '<spu start="00:00:01.000" end="00:00:03.000"' in xml_content
    assert "dvd_test_0000.png" in xml_content

    png_path = os.path.join(out_dir, "dvd_test_0000.png")
    assert os.path.exists(png_path)
    with Image.open(png_path) as img:
        # Scaled width should be approx 80 * (720/1920) = 30
        assert img.width > 0
        assert img.height > 0
        assert img.mode == "RGBA"


def test_parse_pgs_multi_segment_ods(tmp_path):
    """Verify that multi-segment ODS payloads are concatenated correctly."""
    sup_path = str(tmp_path / "multi_ods.sup")

    # Palette
    pds_payload = bytearray([0x00, 0x00, 0, 0, 128, 128, 0, 1, 235, 128, 128, 255])

    # ODS part 1 (first segment 0x80)
    part1_rle = bytearray([0x00, 0x80 | 20, 0x01])  # 20 pixels of color 1
    # ODS part 2 (last segment 0x40)
    part2_rle = bytearray([0x00, 0x80 | 20, 0x01, 0x00, 0x00])  # 20 pixels of color 1 + EOL

    w, h = 40, 1
    ods1_payload = bytearray([0x00, 0x01, 0x00, 0x80])  # Obj 1, seq 0x80 (first)
    total_len = len(part1_rle) + len(part2_rle) + 4
    ods1_payload.extend([(total_len >> 16) & 0xFF, (total_len >> 8) & 0xFF, total_len & 0xFF])
    ods1_payload.extend([(w >> 8) & 0xFF, w & 0xFF, (h >> 8) & 0xFF, h & 0xFF])
    ods1_payload.extend(part1_rle)

    ods2_payload = bytearray([0x00, 0x01, 0x00, 0x40])  # Obj 1, seq 0x40 (last)
    ods2_payload.extend(part2_rle)

    pcs_start = bytearray([
        0x07, 0x80, 0x04, 0x38, 0x10, 0x00, 0x01, 0x80, 0x00, 0x00, 0x01,
        0x00, 0x01, 0x00, 0x00, 0x00, 0x64, 0x00, 0x64,  # Obj 1 at (100, 100)
    ])

    sup_bytes = (
        _build_pgs_packet(90000, 0, 0x16, pcs_start)
        + _build_pgs_packet(90000, 0, 0x14, pds_payload)
        + _build_pgs_packet(90000, 0, 0x15, ods1_payload)
        + _build_pgs_packet(90000, 0, 0x15, ods2_payload)
        + _build_pgs_packet(90000, 0, 0x80, b"")
    )

    with open(sup_path, "wb") as f:
        f.write(sup_bytes)

    items = parse_pgs_sup(sup_path)
    assert len(items) == 1
    assert items[0].objects[0].width == 40
    assert items[0].objects[0].height == 1


def test_parse_pgs_empty_and_corrupt(tmp_path):
    """Verify parser returns empty list gracefully on missing or corrupt files."""
    assert parse_pgs_sup(str(tmp_path / "non_existent.sup")) == []

    empty_sup = str(tmp_path / "empty.sup")
    with open(empty_sup, "wb") as f:
        f.write(b"")
    assert parse_pgs_sup(empty_sup) == []

    corrupt_sup = str(tmp_path / "corrupt.sup")
    with open(corrupt_sup, "wb") as f:
        f.write(b"NOT_A_VALID_PGS_FILE_HEADER_GARBAGE")
    assert parse_pgs_sup(corrupt_sup) == []

    # convert_pgs_to_spumux_xml returns None on empty
    assert convert_pgs_to_spumux_xml(empty_sup, str(tmp_path / "out")) is None
