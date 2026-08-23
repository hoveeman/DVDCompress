"""Blu-ray PGS (Presentation Graphic Stream) subtitle parser and DVD subpicture converter."""

import os
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
from dvdcompress.models import AspectRatio, TVStandard


@dataclass
class PGSObject:
    """Represents a decoded subtitle graphical object."""
    object_id: int
    x: int
    y: int
    width: int
    height: int
    image: Image.Image


@dataclass
class PGSSubtitleItem:
    """Represents a timed subtitle event with one or more graphical objects."""
    start_pts: float  # in seconds
    end_pts: float    # in seconds
    canvas_width: int
    canvas_height: int
    objects: List[PGSObject] = field(default_factory=list)


def ycbcr_to_rgba(y: int, cb: int, cr: int, a: int) -> Tuple[int, int, int, int]:
    """Convert ITU-R YCbCr with alpha to standard 8-bit RGBA."""
    r = max(0, min(255, int(round(y + 1.402 * (cr - 128)))))
    g = max(0, min(255, int(round(y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)))))
    b = max(0, min(255, int(round(y + 1.772 * (cb - 128)))))
    return (r, g, b, a)


def quantize_to_dvd_subpicture(img_rgba: Image.Image) -> Image.Image:
    """Quantize an RGBA subtitle image into a standard 4-color indexed DVD subpicture (Mode P).

    DVD subpictures strictly support at most 4 discrete colors per frame:
      Index 0: Transparent background (alpha < 32)
      Index 1: Primary text fill (White / Bright text)
      Index 2: Dark outline / shadow (Black)
      Index 3: Anti-aliasing / edge transition (Gray)
    """
    img = img_rgba.convert("RGBA")
    w, h = img.size

    out = Image.new("P", (w, h), 0)
    pal = [
        0, 0, 0,        # 0: Transparent background
        255, 255, 255,  # 1: Primary text fill (White)
        0, 0, 0,        # 2: Dark outline / shadow (Black)
        128, 128, 128,  # 3: Anti-aliasing (Gray)
    ]
    pal.extend([0] * (768 - len(pal)))
    out.putpalette(pal)
    out.info["transparency"] = 0

    pixels = img.load()
    out_pixels = out.load()

    # Detect if subtitle has colored/yellow text
    has_yellow = False
    step_y = max(1, h // 10)
    step_x = max(1, w // 10)
    for y in range(0, h, step_y):
        for x in range(0, w, step_x):
            r, g, b, a = pixels[x, y]
            if a >= 128 and r > 180 and g > 180 and b < 100:
                has_yellow = True
                break
        if has_yellow:
            break

    if has_yellow:
        pal[3] = 255
        pal[4] = 255
        pal[5] = 0
        out.putpalette(pal)

    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a < 32:
                out_pixels[x, y] = 0
            else:
                lum = int(0.299 * r + 0.587 * g + 0.114 * b)
                if lum > 170:
                    out_pixels[x, y] = 1
                elif lum < 75:
                    out_pixels[x, y] = 2
                else:
                    out_pixels[x, y] = 3

    return out


def decode_pgs_rle(rle_data: bytes, width: int, height: int) -> bytearray:
    """Decode PGS run-length encoded bitmap stream into a raw palette index buffer."""
    total_pixels = width * height
    pixels = bytearray(total_pixels)
    out_idx = 0
    in_idx = 0
    n = len(rle_data)

    while in_idx < n and out_idx < total_pixels:
        b1 = rle_data[in_idx]
        in_idx += 1
        if b1 != 0:
            pixels[out_idx] = b1
            out_idx += 1
        else:
            if in_idx >= n:
                break
            b2 = rle_data[in_idx]
            in_idx += 1
            if b2 == 0:
                # End of line: advance to next row boundary
                rem = out_idx % width
                if rem != 0:
                    out_idx += (width - rem)
            elif (b2 & 0xC0) == 0x00:
                # 1-byte run of color 0
                run_len = b2 & 0x3F
                out_idx += run_len
            elif (b2 & 0xC0) == 0x40:
                # 2-byte run of color 0
                if in_idx >= n:
                    break
                b3 = rle_data[in_idx]
                in_idx += 1
                run_len = ((b2 & 0x3F) << 8) | b3
                out_idx += run_len
            elif (b2 & 0xC0) == 0x80:
                # 2-byte run of color b3
                if in_idx >= n:
                    break
                b3 = rle_data[in_idx]
                in_idx += 1
                run_len = b2 & 0x3F
                end_pos = min(total_pixels, out_idx + run_len)
                pixels[out_idx:end_pos] = bytes([b3]) * (end_pos - out_idx)
                out_idx += run_len
            elif (b2 & 0xC0) == 0xC0:
                # 3-byte run of color b4
                if in_idx + 1 >= n:
                    break
                b3 = rle_data[in_idx]
                b4 = rle_data[in_idx + 1]
                in_idx += 2
                run_len = ((b2 & 0x3F) << 8) | b3
                end_pos = min(total_pixels, out_idx + run_len)
                pixels[out_idx:end_pos] = bytes([b4]) * (end_pos - out_idx)
                out_idx += run_len

    return pixels


def parse_pgs_sup(sup_path: str) -> List[PGSSubtitleItem]:
    """Parse a Blu-ray PGS .sup file and extract timed subtitle items with RGBA images.

    Args:
        sup_path: Path to the .sup binary file.

    Returns:
        List of parsed PGSSubtitleItem objects.
    """
    if not os.path.exists(sup_path) or os.path.getsize(sup_path) == 0:
        return []

    try:
        with open(sup_path, "rb") as f:
            data = f.read()
    except Exception:
        return []

    offset = 0
    n = len(data)
    palettes: Dict[int, Dict[int, Tuple[int, int, int, int]]] = {}
    objects: Dict[int, Dict[str, Any]] = {}
    items: List[PGSSubtitleItem] = []
    current_ds: Optional[Dict[str, Any]] = None

    while offset + 13 <= n:
        if data[offset:offset + 2] != b"PG":
            offset += 1
            continue

        try:
            pts, dts, seg_type, length = struct.unpack(">IIBH", data[offset + 2:offset + 13])
        except struct.error:
            break

        payload = data[offset + 13:offset + 13 + length]
        offset += 13 + length
        pts_sec = pts / 90000.0

        if seg_type == 0x14:  # Palette Definition Segment (PDS)
            if len(payload) >= 2:
                pal_id = payload[0]
                pal: Dict[int, Tuple[int, int, int, int]] = {}
                for p_idx in range(2, len(payload), 5):
                    if p_idx + 5 <= len(payload):
                        e_id, y, cr, cb, a = payload[p_idx:p_idx + 5]
                        pal[e_id] = ycbcr_to_rgba(y, cb, cr, a)
                palettes[pal_id] = pal

        elif seg_type == 0x15:  # Object Definition Segment (ODS)
            if len(payload) >= 4:
                obj_id, obj_ver, seq_desc = struct.unpack(">HBB", payload[:4])
                if seq_desc & 0x80:  # First or only segment
                    if len(payload) >= 11:
                        obj_w, obj_h = struct.unpack(">HH", payload[7:11])
                        rle_bytes = payload[11:]
                        objects[obj_id] = {
                            "width": obj_w,
                            "height": obj_h,
                            "rle": bytearray(rle_bytes),
                        }
                else:
                    if obj_id in objects:
                        objects[obj_id]["rle"].extend(payload[4:])

        elif seg_type == 0x16:  # Presentation Composition Segment (PCS)
            if len(payload) >= 11:
                v_w, v_h, fps, comp_num, comp_state, pal_upd, pal_id, num_objs = struct.unpack(">HHBHBBBB", payload[:11])
                obj_entries = []
                p_offset = 11
                for _ in range(num_objs):
                    if p_offset + 8 <= len(payload):
                        o_id, win_id, crop_flag, o_x, o_y = struct.unpack(">HBBHH", payload[p_offset:p_offset + 8])
                        p_offset += 8
                        if crop_flag & 0x40 and p_offset + 8 <= len(payload):
                            p_offset += 8
                        obj_entries.append({"id": o_id, "x": o_x, "y": o_y})

                if num_objs > 0:
                    # If we had a previously active unclosed display set, close it now
                    if current_ds is not None:
                        current_ds["end_pts"] = pts_sec
                        _finalize_display_set(current_ds, palettes, objects, items)
                    current_ds = {
                        "start_pts": pts_sec,
                        "v_w": v_w or 1920,
                        "v_h": v_h or 1080,
                        "pal_id": pal_id,
                        "obj_entries": obj_entries,
                    }
                else:
                    # Clear screen (end of subtitle display)
                    if current_ds is not None:
                        current_ds["end_pts"] = pts_sec
                        _finalize_display_set(current_ds, palettes, objects, items)
                        current_ds = None

    # Finalize any trailing open display set
    if current_ds is not None:
        current_ds["end_pts"] = current_ds["start_pts"] + 4.0
        _finalize_display_set(current_ds, palettes, objects, items)

    return items


def _finalize_display_set(
    ds: Dict[str, Any],
    palettes: Dict[int, Dict[int, Tuple[int, int, int, int]]],
    objects: Dict[int, Dict[str, Any]],
    items: List[PGSSubtitleItem],
) -> None:
    """Helper to decode and attach PGSSubtitleItem to the items list."""
    start_pts = ds.get("start_pts", 0.0)
    end_pts = ds.get("end_pts", start_pts + 3.0)
    if end_pts <= start_pts:
        end_pts = start_pts + 2.0

    pal_id = ds.get("pal_id", 0)
    palette = palettes.get(pal_id, {})
    v_w = ds.get("v_w", 1920)
    v_h = ds.get("v_h", 1080)

    decoded_objs: List[PGSObject] = []
    for entry in ds.get("obj_entries", []):
        o_id = entry["id"]
        if o_id in objects:
            obj_data = objects[o_id]
            ow = obj_data["width"]
            oh = obj_data["height"]
            if ow > 0 and oh > 0:
                raw_pixels = decode_pgs_rle(obj_data["rle"], ow, oh)
                img = Image.new("RGBA", (ow, oh))
                rgba_buf = [palette.get(p, (0, 0, 0, 0)) for p in raw_pixels]
                img.putdata(rgba_buf)
                decoded_objs.append(PGSObject(
                    object_id=o_id,
                    x=entry["x"],
                    y=entry["y"],
                    width=ow,
                    height=oh,
                    image=img,
                ))

    if decoded_objs:
        items.append(PGSSubtitleItem(
            start_pts=start_pts,
            end_pts=end_pts,
            canvas_width=v_w,
            canvas_height=v_h,
            objects=decoded_objs,
        ))


def convert_pgs_to_spumux_xml(
    sup_path: str,
    output_dir: str,
    prefix: str = "pgs_sub",
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    pts_offset: float = 0.0,
    max_duration_sec: Optional[float] = None,
    preview_label: Optional[str] = None,
) -> Optional[str]:
    """Convert a Blu-ray PGS .sup subtitle stream to scaled DVD subpicture PNGs and spumux XML.

    Args:
        sup_path: Path to the input .sup file.
        output_dir: Directory where scaled PNGs and spumux XML will be saved.
        prefix: Filename prefix for generated PNG images.
        tv_standard: NTSC (720x480) or PAL (720x576).
        aspect_ratio: 16:9 widescreen or 4:3.
        pts_offset: Timestamp offset in seconds to subtract (used if timestamps require adjustment).
        max_duration_sec: Maximum duration in seconds for filtering preview events.
        preview_label: Label to display on fallback preview subtitle.

    Returns:
        Path to the generated spumux XML file, or None if no subtitles were found.
    """
    items = parse_pgs_sup(sup_path)
    if not items and max_duration_sec is None:
        return None

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target_w = 720
    target_h = 480 if is_ntsc else 576
    fmt_str = "NTSC" if is_ntsc else "PAL"

    os.makedirs(output_dir, exist_ok=True)
    spu_lines = [f'<subpictures format="{fmt_str}">', '  <stream>']

    valid_spu_count = 0
    if items:
        for idx, item in enumerate(items):
            if not item.objects:
                continue

            # Adjust start and end times by pts_offset if applicable
            start_s = item.start_pts - pts_offset
            end_s = item.end_pts - pts_offset

            if max_duration_sec is not None:
                if end_s <= 0.0 or start_s >= max_duration_sec:
                    continue
                start_s = max(0.0, start_s)
                end_s = min(max_duration_sec, end_s)
            else:
                if end_s <= 0.0:
                    continue
                start_s = max(0.0, start_s)

            end_s = max(start_s + 0.5, end_s)

            src_w = max(1, item.canvas_width)
            src_h = max(1, item.canvas_height)
            src_dar = src_w / float(src_h)
            target_dar = 16.0 / 9.0 if aspect_ratio == AspectRatio.RATIO_16_9 else 4.0 / 3.0

            if src_dar >= target_dar - 0.01:
                active_w = target_w
                active_h = min(target_h, max(2, int(round(target_h * (target_dar / src_dar))) & ~1))
                offset_x = 0
                offset_y = max(0, (target_h - active_h) // 2)
            else:
                active_w = min(target_w, max(2, int(round(target_w * (src_dar / target_dar))) & ~1))
                active_h = target_h
                offset_x = max(0, (target_w - active_w) // 2)
                offset_y = 0

            scale_x = active_w / float(src_w)
            scale_y = active_h / float(src_h)

            # If there are multiple objects in the display set, combine them into a composite image
            if len(item.objects) == 1:
                obj = item.objects[0]
                ow, oh = obj.width, obj.height
                if ow <= 0 or oh <= 0:
                    continue

                scaled_w = max(2, int(round(ow * scale_x)))
                scaled_h = max(2, int(round(oh * scale_y)))
                scaled_x = max(0, min(target_w - scaled_w, offset_x + int(round(obj.x * scale_x))))
                scaled_y = max(0, min(target_h - scaled_h, offset_y + int(round(obj.y * scale_y))))

                # Force even coordinates and dimensions for DVD MPEG-2 interlaced subpicture chroma alignment
                scaled_x &= ~1
                scaled_y &= ~1
                scaled_w = max(2, (scaled_w + 1) & ~1)
                scaled_h = max(2, (scaled_h + 1) & ~1)
                if scaled_x + scaled_w > target_w:
                    scaled_w = target_w - scaled_x
                if scaled_y + scaled_h > target_h:
                    scaled_h = target_h - scaled_y

                resized_img = obj.image.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                quantized_img = quantize_to_dvd_subpicture(resized_img)
                png_filename = f"{prefix}_{idx:04d}.png"
                png_path = os.path.join(output_dir, png_filename)
                quantized_img.save(png_path, "PNG", transparency=0)

            else:
                # Multi-object display set: compute bounding box in source canvas
                min_src_x = min(o.x for o in item.objects)
                min_src_y = min(o.y for o in item.objects)
                max_src_x = max(o.x + o.width for o in item.objects)
                max_src_y = max(o.y + o.height for o in item.objects)
                comp_src_w = max(1, max_src_x - min_src_x)
                comp_src_h = max(1, max_src_y - min_src_y)

                composite_src = Image.new("RGBA", (comp_src_w, comp_src_h), (0, 0, 0, 0))
                for o in item.objects:
                    composite_src.paste(o.image, (o.x - min_src_x, o.y - min_src_y), o.image)

                scaled_w = max(2, int(round(comp_src_w * scale_x)))
                scaled_h = max(2, int(round(comp_src_h * scale_y)))
                scaled_x = max(0, min(target_w - scaled_w, offset_x + int(round(min_src_x * scale_x))))
                scaled_y = max(0, min(target_h - scaled_h, offset_y + int(round(min_src_y * scale_y))))

                scaled_x &= ~1
                scaled_y &= ~1
                scaled_w = max(2, (scaled_w + 1) & ~1)
                scaled_h = max(2, (scaled_h + 1) & ~1)
                if scaled_x + scaled_w > target_w:
                    scaled_w = target_w - scaled_x
                if scaled_y + scaled_h > target_h:
                    scaled_h = target_h - scaled_y

                resized_img = composite_src.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
                quantized_img = quantize_to_dvd_subpicture(resized_img)
                png_filename = f"{prefix}_{idx:04d}.png"
                png_path = os.path.join(output_dir, png_filename)
                quantized_img.save(png_path, "PNG", transparency=0)

            # Format start and end timestamps in HH:MM:SS.mmm format for spumux
            sh = int(start_s // 3600)
            sm = int((start_s % 3600) // 60)
            ss = start_s % 60
            start_str = f"{sh:02d}:{sm:02d}:{ss:06.3f}"

            eh = int(end_s // 3600)
            em = int((end_s % 3600) // 60)
            es = end_s % 60
            end_str = f"{eh:02d}:{em:02d}:{es:06.3f}"

            spu_lines.append(
                f'    <spu start="{start_str}" end="{end_str}" image="{png_path}" xoffset="{scaled_x}" yoffset="{scaled_y}" />'
            )
            valid_spu_count += 1

    if valid_spu_count == 0:
        if max_duration_sec is not None:
            # Generate fallback subtitle preview box so user can always verify subpicture rendering
            from PIL import ImageDraw
            preview_png = os.path.join(output_dir, f"{prefix}_preview.png")
            box_w, box_h = 360, 48
            preview_img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(preview_img)
            draw.rectangle([0, 0, box_w - 1, box_h - 1], fill=(0, 0, 0, 255), outline=(255, 255, 255, 255), width=2)
            lbl = preview_label or "Subtitles"
            draw.text((16, 14), f"[{lbl}]", fill=(255, 255, 255, 255))
            quantized_preview = quantize_to_dvd_subpicture(preview_img)
            x_off = ((target_w - box_w) // 2) & ~1
            y_off = (target_h - 70) & ~1
            quantized_preview.save(preview_png, "PNG", transparency=0)
            spu_lines.append(
                f'    <spu start="00:00:02.000" end="00:00:08.000" image="{preview_png}" xoffset="{x_off}" yoffset="{y_off}" />'
            )
            valid_spu_count += 1
        else:
            return None

    spu_lines.extend(["  </stream>", "</subpictures>"])
    xml_path = os.path.join(output_dir, f"{prefix}_spumux.xml")
    with open(xml_path, "w", encoding="utf-8") as xf:
        xf.write("\n".join(spu_lines))

    return xml_path
