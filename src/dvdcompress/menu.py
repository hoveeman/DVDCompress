"""DVD Title Menu generation and authoring utilities using Pillow, FFmpeg, and spumux."""

import os
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from dvdcompress.models import AspectRatio, TVStandard


@dataclass
class MenuButton:
    name: str
    x0: int
    y0: int
    x1: int
    y1: int
    up: str
    down: str
    left: str
    right: str


def get_menu_font(size: int = 16, bold: bool = False) -> ImageFont.ImageFont:
    """Locate an available TrueType font for menu rendering with cross-platform fallbacks."""
    candidate_fonts = [
        # Bold Linux / Container paths
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", True),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", True),
        ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", True),
        ("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", True),
        # Bold macOS paths
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", True),
        ("/System/Library/Fonts/Helvetica.ttc", True),
        ("/Library/Fonts/Arial Bold.ttf", True),
        # Regular Linux / Container paths
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", False),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", False),
        ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", False),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", False),
        # Regular macOS paths
        ("/System/Library/Fonts/Supplemental/Arial.ttf", False),
        ("/System/Library/Fonts/Geneva.ttf", False),
        ("/Library/Fonts/Arial Unicode.ttf", False),
        ("/System/Library/Fonts/Helvetica.ttc", False),
    ]

    for path, is_bold in candidate_fonts:
        if bold and not is_bold:
            continue
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    for path, _ in candidate_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass

    return ImageFont.load_default()


def generate_dvd_menu_assets(
    titles: List[Dict[str, Any]],
    disc_label: str = "DVD_VIDEO",
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    output_dir: str = "/tmp",
) -> Tuple[str, str, str, List[MenuButton]]:
    """Generate menu background PNG and button highlight/selection subpicture overlays with even coordinates."""
    is_pal = tv_standard == TVStandard.PAL
    width = 720
    height = 576 if is_pal else 480

    bg = Image.new("RGB", (width, height), (15, 23, 42))
    draw_bg = ImageDraw.Draw(bg)

    # Render dark-slate gradient background
    for y in range(height):
        factor = y / float(height)
        r = int(15 * (1 - factor) + 30 * factor)
        g = int(23 * (1 - factor) + 41 * factor)
        b = int(42 * (1 - factor) + 59 * factor)
        draw_bg.line([(0, y), (width, y)], fill=(r, g, b))

    # Header bar
    header_h = 76 if is_pal else 64
    draw_bg.rectangle([0, 0, width, header_h], fill=(10, 15, 29))
    draw_bg.line([(0, header_h), (width, header_h)], fill=(59, 130, 246), width=2)

    # Header Typography
    clean_label = disc_label.replace("_", " ").strip().upper() if disc_label else "DVD VIDEO"
    font_hdr = get_menu_font(22 if is_pal else 20, bold=True)
    font_sub = get_menu_font(13 if is_pal else 12, bold=False)
    font_btn = get_menu_font(14 if is_pal else 13, bold=True)
    font_meta = get_menu_font(12 if is_pal else 11, bold=False)

    draw_bg.text(
        (width // 2, header_h // 2 - 9),
        clean_label,
        fill=(255, 255, 255),
        anchor="mm",
        font=font_hdr,
    )
    draw_bg.text(
        (width // 2, header_h // 2 + 13),
        "SELECT A TITLE TO PLAY",
        fill=(148, 163, 184),
        anchor="mm",
        font=font_sub,
    )

    # Subpicture highlight & select layers
    hl = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_hl = ImageDraw.Draw(hl)
    sel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_sel = ImageDraw.Draw(sel)

    n = max(1, min(len(titles), 12))
    buttons: List[MenuButton] = []
    is_two_col = n > 6

    if not is_two_col:
        # Single column layout (1 to 6 titles)
        y_start = header_h + (24 if is_pal else 18)
        btn_h = 44 if is_pal else 38
        spacing = 14 if n <= 4 else (10 if n <= 5 else 6)
        x0, x1 = 80, 640

        for i in range(n):
            t = titles[i] if i < len(titles) else {}
            idx = i + 1
            y0 = y_start + i * (btn_h + spacing)
            if y0 % 2 != 0:
                y0 += 1
            y1 = y0 + btn_h
            if y1 % 2 != 0:
                y1 += 1

            # Card background on backdrop
            draw_bg.rectangle([x0, y0, x1, y1], fill=(30, 41, 59), outline=(51, 65, 85), width=1)
            # Index badge
            draw_bg.rectangle([x0 + 6, y0 + 6, x0 + 42, y1 - 6], fill=(59, 130, 246))
            draw_bg.text(
                (x0 + 24, (y0 + y1) // 2),
                f"{idx:02d}",
                fill=(255, 255, 255),
                anchor="mm",
                font=font_btn,
            )

            # Title label
            t_name = t.get("name", f"Title {idx}")
            if len(t_name) > 44:
                t_name = t_name[:41] + "..."
            draw_bg.text(
                (x0 + 54, (y0 + y1) // 2),
                t_name,
                fill=(241, 245, 249),
                anchor="lm",
                font=font_btn,
            )

            # Duration
            dur = t.get("duration", "")
            if dur:
                draw_bg.text(
                    (x1 - 16, (y0 + y1) // 2),
                    dur,
                    fill=(148, 163, 184),
                    anchor="rm",
                    font=font_meta,
                )

            # Highlight & Select subpicture overlays
            draw_hl.rectangle([x0, y0, x1, y1], fill=(56, 189, 248, 80), outline=(56, 189, 248, 255), width=2)
            draw_sel.rectangle([x0, y0, x1, y1], fill=(245, 158, 11, 140), outline=(251, 191, 36, 255), width=2)

            up_btn = n if idx == 1 else idx - 1
            dn_btn = 1 if idx == n else idx + 1
            buttons.append(
                MenuButton(
                    name=str(idx),
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    up=str(up_btn),
                    down=str(dn_btn),
                    left=str(idx),
                    right=str(idx),
                )
            )
    else:
        # Two-column layout (7 to 12 titles)
        col1_count = (n + 1) // 2
        col2_count = n - col1_count
        y_start = header_h + (16 if is_pal else 12)
        btn_h = 40 if is_pal else 34
        spacing = 8 if is_pal else 6

        col1_x0, col1_x1 = 50, 350
        col2_x0, col2_x1 = 370, 670

        for i in range(n):
            t = titles[i] if i < len(titles) else {}
            idx = i + 1
            is_col2 = i >= col1_count
            row_idx = i - col1_count if is_col2 else i

            cx0 = col2_x0 if is_col2 else col1_x0
            cx1 = col2_x1 if is_col2 else col1_x1

            y0 = y_start + row_idx * (btn_h + spacing)
            if y0 % 2 != 0:
                y0 += 1
            y1 = y0 + btn_h
            if y1 % 2 != 0:
                y1 += 1

            # Card background
            draw_bg.rectangle([cx0, y0, cx1, y1], fill=(30, 41, 59), outline=(51, 65, 85), width=1)
            # Index badge
            draw_bg.rectangle([cx0 + 4, y0 + 4, cx0 + 36, y1 - 4], fill=(59, 130, 246))
            draw_bg.text(
                (cx0 + 20, (y0 + y1) // 2),
                f"{idx:02d}",
                fill=(255, 255, 255),
                anchor="mm",
                font=font_btn,
            )

            # Title label
            t_name = t.get("name", f"Title {idx}")
            if len(t_name) > 22:
                t_name = t_name[:19] + "..."
            draw_bg.text(
                (cx0 + 44, (y0 + y1) // 2),
                t_name,
                fill=(241, 245, 249),
                anchor="lm",
                font=font_btn,
            )

            # Highlight & Select subpicture overlays
            draw_hl.rectangle([cx0, y0, cx1, y1], fill=(56, 189, 248, 80), outline=(56, 189, 248, 255), width=2)
            draw_sel.rectangle([cx0, y0, cx1, y1], fill=(245, 158, 11, 140), outline=(251, 191, 36, 255), width=2)

            # Vertical navigation within column
            if not is_col2:
                up_btn = col1_count if row_idx == 0 else idx - 1
                dn_btn = 1 if row_idx == col1_count - 1 else idx + 1
                # Horizontal jump to col2
                target_col2 = min(n, col1_count + 1 + row_idx)
                r_btn = target_col2
                l_btn = idx
            else:
                up_btn = n if row_idx == 0 else idx - 1
                dn_btn = col1_count + 1 if row_idx == col2_count - 1 else idx + 1
                # Horizontal jump to col1
                target_col1 = 1 + row_idx
                l_btn = target_col1
                r_btn = idx

            buttons.append(
                MenuButton(
                    name=str(idx),
                    x0=cx0,
                    y0=y0,
                    x1=cx1,
                    y1=y1,
                    up=str(up_btn),
                    down=str(dn_btn),
                    left=str(l_btn),
                    right=str(r_btn),
                )
            )

    os.makedirs(output_dir, exist_ok=True)
    bg_path = os.path.join(output_dir, "menu_bg.png")
    hl_path = os.path.join(output_dir, "menu_highlight.png")
    sel_path = os.path.join(output_dir, "menu_select.png")

    bg.save(bg_path)
    hl.save(hl_path)
    sel.save(sel_path)

    return bg_path, hl_path, sel_path, buttons


def build_menu_video_command(
    bg_image_path: str,
    output_mpg_path: str,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    duration_sec: float = 1.0,
) -> List[str]:
    """Build FFmpeg command to transcode a menu backdrop into a DVD-compliant MPEG-2 stream with silent AC3."""
    is_pal = tv_standard == TVStandard.PAL
    res = "720x576" if is_pal else "720x480"
    fps = "25" if is_pal else "29.97"
    aspect_val = "16:9" if aspect_ratio == AspectRatio.RATIO_16_9 else "4:3"

    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        bg_image_path,
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-c:v",
        "mpeg2video",
        "-b:v",
        "6000k",
        "-minrate",
        "0",
        "-maxrate",
        "8500k",
        "-bufsize",
        "1835k",
        "-aspect",
        aspect_val,
        "-s",
        res,
        "-r",
        fps,
        "-t",
        str(duration_sec),
        "-c:a",
        "ac3",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-f",
        "dvd",
        output_mpg_path,
    ]


def generate_menu_spumux_xml(
    highlight_path: str,
    select_path: str,
    buttons: List[MenuButton],
    tv_standard: TVStandard = TVStandard.NTSC,
) -> str:
    """Generate spumux XML configuration for embedding interactive menu buttons."""
    fmt = "PAL" if tv_standard == TVStandard.PAL else "NTSC"

    btn_lines = []
    for b in buttons:
        btn_lines.append(
            f'      <button name="{b.name}" x0="{b.x0}" y0="{b.y0}" x1="{b.x1}" y1="{b.y1}" '
            f'up="{b.up}" down="{b.down}" left="{b.left}" right="{b.right}" />'
        )

    buttons_xml = "\n".join(btn_lines)

    return f"""<subpictures format="{fmt}">
  <stream>
    <spu start="00:00:00.0" end="00:00:00.0"
         highlight="{highlight_path}"
         select="{select_path}">
{buttons_xml}
    </spu>
  </stream>
</subpictures>
"""


def build_spumux_menu_command(
    input_mpg_path: str,
    output_mpg_path: str,
    xml_path: str,
) -> str:
    """Build shell command to multiplex menu button overlays into the DVD menu stream."""
    return f"spumux -m dvd -v 0 {shlex.quote(xml_path)} < {shlex.quote(input_mpg_path)} > {shlex.quote(output_mpg_path)}"
