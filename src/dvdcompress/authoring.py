"""Disc authoring specification and metadata generators for dvdauthor and tsMuxeR."""

from typing import List, Optional
from dvdcompress.models import MenuMode, TVStandard


def format_chapter_time(seconds: float) -> str:
    """Format chapter timestamp into dvdauthor XML HH:MM:SS.mmm format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


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
        for lang in subtitles_lang:
            clean_lang = lang[:2].lower() if lang and len(lang) >= 2 else "en"
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
    for vf in video_files:
        meta_lines.append(f'V_MPEG4/ISO/AVC, "{vf}", fps=23.976, insertSEI, contSPS')
        meta_lines.append(f'A_AC3, "{vf}"')
    return "\n".join(meta_lines)
