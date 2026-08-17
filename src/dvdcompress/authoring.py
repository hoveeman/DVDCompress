import os
from typing import Any, Dict, List, Optional
from dvdcompress.models import AspectRatio, MenuMode, TVStandard


def format_chapter_time(seconds: float) -> str:
    """Format chapter timestamp into dvdauthor XML HH:MM:SS.mmm format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def get_spumux_font_path() -> str:
    """Locate an available TrueType font file for spumux rendering across Linux and macOS."""
    candidate_fonts = [
        # Linux / Container paths
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        # macOS paths
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Geneva.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for font_path in candidate_fonts:
        if os.path.exists(font_path):
            return font_path
    return "sans-serif"


def generate_spumux_xml(
    srt_path: str,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    font_path: Optional[str] = None,
) -> str:
    """Generate spumux XML configuration to multiplex a subtitle track into DVD MPEG-2."""
    fmt = "NTSC" if tv_standard in (TVStandard.NTSC, TVStandard.AUTO) else "PAL"
    aspect_val = "16:9" if aspect_ratio == AspectRatio.RATIO_16_9 else "4:3"
    resolved_font = font_path or get_spumux_font_path()

    return f"""<subpictures format="{fmt}">
  <stream>
    <textsub filename="{srt_path}"
             characterset="UTF-8"
             fontsize="24.0"
             font="{resolved_font}"
             aspect="{aspect_val}"
             horizontal-alignment="center"
             vertical-alignment="bottom"
             bottom-margin="36"
             outline-thickness="2.0"
             outline-color="#000000"
             fill-color="#FFFFFF" />
  </stream>
</subpictures>
"""


MAX_DVD_SUBPICTURE_STREAMS = 32
MAX_BLURAY_SUBTITLE_STREAMS = 32


def build_spumux_pipeline_command(
    input_mpg_path: str,
    output_mpg_path: str,
    xml_paths: List[str],
) -> str:
    """Build a chained single-pass shell pipeline for multiplexing multiple DVD subtitle tracks with spumux."""
    import shlex
    if not xml_paths:
        raise ValueError("At least one spumux XML configuration path is required")

    # DVD-Video specification strictly limits to 32 subpicture streams (indices 0..31)
    clamped_xmls = xml_paths[:MAX_DVD_SUBPICTURE_STREAMS]
    stages = []
    for s_idx, xml_p in enumerate(clamped_xmls):
        stages.append(f"spumux -m dvd -s {s_idx} -P {shlex.quote(xml_p)}")

    # First stage takes stdin from input_mpg_path
    stages[0] = f"{stages[0]} < {shlex.quote(input_mpg_path)}"

    # Last stage directs stdout to output_mpg_path
    stages[-1] = f"{stages[-1]} > {shlex.quote(output_mpg_path)}"

    return " | ".join(stages)



def build_subtitle_extraction_command(
    input_file: str,
    stream_index: int,
    output_sub_path: str,
    is_bitmap: bool = False,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> List[str]:
    """Build FFmpeg command to extract a subtitle stream to .srt (text) or .sup (bitmap PGS)."""
    cmd = ["ffmpeg", "-y"]
    if seek_start_sec is not None and seek_start_sec > 0:
        cmd.extend(["-ss", str(seek_start_sec)])
    cmd.extend(["-i", input_file])
    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])
    cmd.extend(["-map", f"0:{stream_index}"])
    if is_bitmap:
        cmd.extend(["-c:s", "copy"])
    else:
        cmd.extend(["-c:s", "srt"])
    cmd.append(output_sub_path)
    return cmd


ISO_639_2_TO_1 = {
    "eng": "en",
    "spa": "es",
    "fre": "fr",
    "fra": "fr",
    "ger": "de",
    "deu": "de",
    "ita": "it",
    "jpn": "ja",
    "chi": "zh",
    "zho": "zh",
    "rus": "ru",
    "por": "pt",
    "kor": "ko",
    "dut": "nl",
    "nld": "nl",
    "swe": "sv",
    "nor": "no",
    "dan": "da",
    "fin": "fi",
    "pol": "pl",
    "cze": "cs",
    "ces": "cs",
}


def normalize_lang_code_2(lang: Optional[str]) -> str:
    """Normalize language string to 2-letter ISO 639-1 code for DVD subpictures."""
    if not lang:
        return "en"
    l_lower = lang.strip().lower()
    if l_lower in ISO_639_2_TO_1:
        return ISO_639_2_TO_1[l_lower]
    if len(l_lower) == 2:
        return l_lower
    return l_lower[:2]


def generate_dvdauthor_xml(
    titles_mpg: List[str],
    chapters_sec: List[List[float]],
    menu_mode: MenuMode = MenuMode.AUTOPLAY,
    tv_standard: TVStandard = TVStandard.NTSC,
    subtitles_lang: Optional[List[str]] = None,
) -> str:
    """Generate a standard dvdauthor.xml structure for authoring DVD-Video."""
    video_format = "ntsc" if tv_standard in (TVStandard.NTSC, TVStandard.AUTO) else "pal"

    xml_lines = [
        '<dvdauthor dest="VIDEO_TS">',
        '  <vmgm />',
        '  <titleset>',
        '    <titles>',
        f'      <video format="{video_format}" aspect="16:9" widescreen="nopanscan" />',
        '      <audio format="ac3" channels="2" />',
    ]

    if subtitles_lang:
        for lang in subtitles_lang[:MAX_DVD_SUBPICTURE_STREAMS]:
            clean_lang = normalize_lang_code_2(lang)
            xml_lines.append(f'      <subpicture lang="{clean_lang}" />')

    for idx, mpg in enumerate(titles_mpg):
        chaps = (
            chapters_sec[idx]
            if idx < len(chapters_sec) and len(chapters_sec[idx]) > 0
            else [0.0]
        )
        chap_str = ",".join([format_chapter_time(c) for c in chaps])
        xml_lines.append("      <pgc>")
        xml_lines.append(f'        <vob file="{mpg}" chapters="{chap_str}" />')
        # Play next title or loop back to title 1
        if idx < len(titles_mpg) - 1:
            xml_lines.append(f"        <post>jump title {idx + 2};</post>")
        else:
            xml_lines.append("        <post>jump title 1;</post>")
        xml_lines.append("      </pgc>")

    xml_lines.extend([
        "    </titles>",
        "  </titleset>",
        "</dvdauthor>",
    ])

    return "\n".join(xml_lines)


def generate_tsmuxer_meta(
    video_files: List[str],
    chapters_sec: Optional[List[float]] = None,
    subtitle_files: Optional[List[Dict[str, Any]]] = None,
    video_codecs: Optional[List[str]] = None,
) -> str:
    """Generate tsMuxeR .meta file content for Blu-ray BDMV muxing."""
    if chapters_sec and len(chapters_sec) > 0:
        formatted_chaps = ";".join([format_chapter_time(c) for c in chapters_sec])
        chap_opt = f"--custom-chapters={formatted_chaps}"
    else:
        chap_opt = "--auto-chapters=5"

    meta_lines = [
        f"MUXOPT --no-pcr-on-video-pid --new-audio-pes --blu-ray --vbr {chap_opt}"
    ]
    for idx, vf in enumerate(video_files):
        vcodec = video_codecs[idx] if (video_codecs and idx < len(video_codecs)) else "h264"
        if vcodec == "hevc":
            meta_lines.append(f'V_MPEGH/ISO/HEVC, "{vf}", fps=23.976, insertSEI, contSPS')
        else:
            meta_lines.append(f'V_MPEG4/ISO/AVC, "{vf}", fps=23.976, insertSEI, contSPS')
        meta_lines.append(f'A_AC3, "{vf}"')

    if subtitle_files:
        for sub in subtitle_files[:MAX_BLURAY_SUBTITLE_STREAMS]:
            sub_path = sub.get("path")
            lang = sub.get("lang", "eng")
            is_bitmap = sub.get("is_bitmap", False)
            if is_bitmap:
                meta_lines.append(f'S_HDMV/PGS, "{sub_path}", lang={lang}')
            else:
                meta_lines.append(
                    f'S_TEXT/UTF8, "{sub_path}", font-name="Arial", font-size=65, font-color=0x00ffffff, bottom-offset=24, lang={lang}'
                )

    return "\n".join(meta_lines)

