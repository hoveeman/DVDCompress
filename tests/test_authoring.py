import pytest
from dvdcompress.models import MenuMode, TVStandard
from dvdcompress.authoring import generate_dvdauthor_xml, generate_tsmuxer_meta, format_chapter_time
from dvdcompress.iso import build_genisoimage_command, build_xorriso_bd_command


def test_format_chapter_time():
    assert format_chapter_time(0.0) == "00:00:00.000"
    assert format_chapter_time(300.0) == "00:05:00.000"
    assert format_chapter_time(3661.5) == "01:01:01.500"


def test_dvdauthor_xml_single_title_autoplay():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0, 600.0]],
        menu_mode=MenuMode.AUTOPLAY,
        tv_standard=TVStandard.NTSC,
    )
    assert 'dest="VIDEO_TS"' in xml
    assert "<vob file=\"/tmp/title1.mpg\"" in xml
    assert "chapters=\"00:00:00.000,00:05:00.000,00:10:00.000\"" in xml
    assert 'format="ntsc"' in xml
    assert "<post>jump pgc 1;</post>" in xml


def test_dvdauthor_xml_multi_titles():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/ep1.mpg", "/tmp/ep2.mpg"],
        chapters_sec=[[0.0, 300.0], [0.0, 300.0]],
        menu_mode=MenuMode.AUTOPLAY,
        tv_standard=TVStandard.PAL,
    )
    assert "<vob file=\"/tmp/ep1.mpg\"" in xml
    assert "<vob file=\"/tmp/ep2.mpg\"" in xml
    assert 'format="pal"' in xml
    assert "<post>jump pgc 2;</post>" in xml
    assert "<post>jump pgc 1;</post>" in xml


def test_dvdauthor_xml_empty_chapters():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[],
    )
    assert "chapters=\"00:00:00.000\"" in xml


def test_dvdauthor_xml_with_title_menu_single_title():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0]],
        menu_mode=MenuMode.MENU,
        menu_vob="/tmp/menu.mpg",
        tv_standard=TVStandard.NTSC,
    )
    assert '<dvdauthor dest="VIDEO_TS" jumppad="1">' in xml
    assert "<vmgm>" in xml
    assert "<menus>" in xml
    assert '<pgc entry="title">' in xml
    assert '<vob file="/tmp/menu.mpg" pause="inf" />' in xml
    assert "<button name=\"1\">jump title 1;</button>" in xml
    assert "<post>jump cell 1;</post>" in xml
    assert '<pgc entry="root">' in xml
    assert "<pre>jump vmgm menu entry title;</pre>" in xml
    assert "<post>call vmgm menu entry title;</post>" in xml


def test_dvdauthor_xml_with_title_menu_multi_titles():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/ep1.mpg", "/tmp/ep2.mpg", "/tmp/ep3.mpg"],
        chapters_sec=[[0.0], [0.0], [0.0]],
        menu_mode=MenuMode.MENU,
        menu_vob="/tmp/menu.mpg",
        tv_standard=TVStandard.PAL,
    )
    assert '<dvdauthor dest="VIDEO_TS" jumppad="1">' in xml
    assert '<vob file="/tmp/menu.mpg" pause="inf" />' in xml
    assert "<button name=\"1\">jump title 1;</button>" in xml
    assert "<button name=\"2\">jump title 2;</button>" in xml
    assert "<button name=\"3\">jump title 3;</button>" in xml
    assert '<pgc entry="root">' in xml
    assert "<pre>jump vmgm menu entry title;</pre>" in xml
    assert xml.count("<post>call vmgm menu entry title;</post>") == 3


def test_dvdauthor_xml_with_title_menu_play_next_action():
    from dvdcompress.models import MenuEndAction
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/ep1.mpg", "/tmp/ep2.mpg", "/tmp/ep3.mpg"],
        chapters_sec=[[0.0], [0.0], [0.0]],
        menu_mode=MenuMode.MENU,
        menu_vob="/tmp/menu.mpg",
        menu_end_action=MenuEndAction.PLAY_NEXT,
        tv_standard=TVStandard.NTSC,
    )
    # Title 1 and 2 jump to the next title in sequence
    assert "<post>jump pgc 2;</post>" in xml
    assert "<post>jump pgc 3;</post>" in xml
    # Title 3 (last title) returns to the menu
    assert "<post>call vmgm menu entry title;</post>" in xml
    assert xml.count("<post>call vmgm menu entry title;</post>") == 1


def test_generate_tsmuxer_meta():
    meta = generate_tsmuxer_meta(["/tmp/track1.m2ts", "/tmp/track2.m2ts"])
    assert "MUXOPT --no-pcr-on-video-pid --new-audio-pes --blu-ray --vbr --auto-chapters=5" in meta
    assert 'V_MPEG4/ISO/AVC, "/tmp/track1.m2ts", track=4113, fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/tmp/track1.m2ts", track=4352' in meta
    assert 'V_MPEG4/ISO/AVC, "/tmp/track2.m2ts", track=4113, fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/tmp/track2.m2ts", track=4352' in meta

    meta_custom = generate_tsmuxer_meta(["/tmp/track1.m2ts"], chapters_sec=[0.0, 300.0, 600.0])
    assert "--custom-chapters=00:00:00.000;00:05:00.000;00:10:00.000" in meta_custom


def test_iso_commands():
    from dvdcompress.iso import (
        build_dvd_fallback_iso_command,
        build_dvd_iso_command,
        build_genisoimage_command,
        build_xorriso_bd_command,
        build_xorriso_dvd_command,
    )

    iso_cmd = build_genisoimage_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "-dvd-video" in iso_cmd
    assert "-udf" in iso_cmd
    assert "MY_MOVIE" in iso_cmd
    assert "-o" in iso_cmd
    assert "/output/movie.iso" in iso_cmd
    assert "/tmp/author" in iso_cmd

    xorriso_dvd = build_xorriso_dvd_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "xorriso" in xorriso_dvd
    assert "-dvd-video" not in xorriso_dvd
    assert "-udf" not in xorriso_dvd
    assert "MY_MOVIE" in xorriso_dvd
    assert "/tmp/author" in xorriso_dvd

    dvd_auto = build_dvd_iso_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "-dvd-video" in dvd_auto
    assert "-udf" in dvd_auto

    fallback_cmd = build_dvd_fallback_iso_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "-udf" in fallback_cmd
    assert "-dvd-video" not in fallback_cmd
    assert "MY_MOVIE" in fallback_cmd
    assert "-o" in fallback_cmd
    assert "/output/movie.iso" in fallback_cmd
    assert "/tmp/author" in fallback_cmd

    bd_cmd = build_xorriso_bd_command("/tmp/bd_author", "/output/bd.iso", "MY_BLURAY")
    assert "MY_BLURAY" in bd_cmd
    assert "-iso-level" in bd_cmd
    assert "3" in bd_cmd
    assert "/tmp/bd_author" in bd_cmd


def test_iso_label_sanitization():
    # Long label with spaces and special chars
    long_label = "My Super Movie Name (2026) Extended Edition Special Cut"
    iso_cmd = build_genisoimage_command("/tmp/author", "/output/movie.iso", long_label)
    idx = iso_cmd.index("-V")
    sanitized = iso_cmd[idx + 1]
    assert len(sanitized) <= 32
    assert sanitized == "MY_SUPER_MOVIE_NAME__2026__EXTEN"
    assert all(c.isalnum() or c == '_' for c in sanitized)


def test_build_subtitle_extraction_command():
    from dvdcompress.authoring import build_subtitle_extraction_command

    # Text subtitle extraction (to .srt)
    cmd_text = build_subtitle_extraction_command(
        input_file="/media/movie.mkv",
        stream_index=2,
        output_sub_path="/tmp/sub.srt",
        is_bitmap=False,
    )
    assert cmd_text == ["ffmpeg", "-y", "-i", "/media/movie.mkv", "-map", "0:2", "-c:s", "srt", "/tmp/sub.srt"]

    # Bitmap PGS subtitle extraction (to .sup) with seek & duration
    cmd_bitmap = build_subtitle_extraction_command(
        input_file="/media/movie.mkv",
        stream_index=3,
        output_sub_path="/tmp/sub.sup",
        is_bitmap=True,
        seek_start_sec=120.0,
        duration_sec=60.0,
    )
    assert cmd_bitmap == ["ffmpeg", "-y", "-ss", "120.0", "-i", "/media/movie.mkv", "-t", "60.0", "-map", "0:3", "-c:s", "copy", "/tmp/sub.sup"]


def test_generate_spumux_xml():
    from dvdcompress.authoring import generate_spumux_xml, get_spumux_font_path
    from dvdcompress.models import AspectRatio, TVStandard

    font = get_spumux_font_path()
    assert font is not None

    xml_ntsc = generate_spumux_xml(
        srt_path="/tmp/sub.srt",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        font_path="/usr/share/fonts/DejaVuSans.ttf",
    )
    assert '<subpictures format="NTSC">' in xml_ntsc
    assert '<textsub filename="/tmp/sub.srt"' in xml_ntsc
    assert 'font="/usr/share/fonts/DejaVuSans.ttf"' in xml_ntsc
    assert 'aspect="16:9"' in xml_ntsc

    xml_pal = generate_spumux_xml(
        srt_path="/tmp/sub_pal.srt",
        tv_standard=TVStandard.PAL,
        aspect_ratio=AspectRatio.RATIO_4_3,
    )
    assert '<subpictures format="PAL">' in xml_pal
    assert 'aspect="4:3"' in xml_pal


def test_generate_tsmuxer_meta_with_subtitles():
    subs = [
        {"path": "/tmp/sub1.srt", "lang": "eng", "is_bitmap": False},
        {"path": "/tmp/sub2.sup", "lang": "spa", "is_bitmap": True},
    ]
    meta = generate_tsmuxer_meta(
        video_files=["/tmp/track1.m2ts"],
        subtitle_files=subs,
    )
    assert 'S_TEXT/UTF8, "/tmp/sub1.srt", font-name="Arial", font-size=65, font-color=0x00ffffff, bottom-offset=24, lang=eng' in meta
    assert 'S_HDMV/PGS, "/tmp/sub2.sup", lang=spa' in meta


def test_generate_dvdauthor_xml_with_subpictures():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0]],
        subtitles_lang=["eng", "eng", "spa"],
    )
    # Both English tracks and Spanish track should be declared
    assert xml.count('<subpicture lang="en" />') == 2
    assert xml.count('<subpicture lang="es" />') == 1


def test_generate_tsmuxer_meta_hevc_uhd():
    meta = generate_tsmuxer_meta(
        video_files=["/media/uhd_remux.mkv"],
        video_codecs=["hevc"],
    )
    assert 'V_MPEGH/ISO/HEVC, "/media/uhd_remux.mkv", track=1, fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/media/uhd_remux.mkv", track=2' in meta


def test_generate_tsmuxer_meta_elementary_streams():
    meta = generate_tsmuxer_meta(
        video_files=["/tmp/stream.264"],
        video_codecs=["h264"],
    )
    assert 'V_MPEG4/ISO/AVC, "/tmp/stream.264", fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/tmp/stream.264"' in meta


def test_build_spumux_pipeline_command():
    from dvdcompress.authoring import build_spumux_pipeline_command
    import pytest

    # Single track pipeline
    cmd1 = build_spumux_pipeline_command(
        input_mpg_path="/tmp/input.mpg",
        output_mpg_path="/tmp/output.mpg",
        xml_paths=["/tmp/sub0.xml"],
    )
    assert cmd1 == "spumux -m dvd -s 0 -P /tmp/sub0.xml < /tmp/input.mpg > /tmp/output.mpg"

    # Multi-track chained pipeline
    cmd3 = build_spumux_pipeline_command(
        input_mpg_path="/tmp/input movie.mpg",
        output_mpg_path="/tmp/output subbed.mpg",
        xml_paths=["/tmp/sub0.xml", "/tmp/sub1.xml", "/tmp/sub2.xml"],
    )
    assert "spumux -m dvd -s 0 -P /tmp/sub0.xml < '/tmp/input movie.mpg'" in cmd3
    assert " | spumux -m dvd -s 1 -P /tmp/sub1.xml | " in cmd3
    assert "spumux -m dvd -s 2 -P /tmp/sub2.xml > '/tmp/output subbed.mpg'" in cmd3

    # Empty xmls raises ValueError
    with pytest.raises(ValueError):
        build_spumux_pipeline_command("/tmp/in.mpg", "/tmp/out.mpg", [])

    # Pipeline clamped to 32 streams (indices 0..31)
    many_xmls = [f"/tmp/sub_{i}.xml" for i in range(45)]
    cmd_many = build_spumux_pipeline_command(
        input_mpg_path="/tmp/input.mpg",
        output_mpg_path="/tmp/output.mpg",
        xml_paths=many_xmls,
    )
    assert cmd_many.count("spumux -m dvd -s ") == 32
    assert "spumux -m dvd -s 0" in cmd_many
    assert "spumux -m dvd -s 31" in cmd_many
    assert "spumux -m dvd -s 32" not in cmd_many


def test_generate_dvdauthor_xml_clamps_to_32_subpicture_streams():
    languages = [f"l{i}" for i in range(50)]
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0]],
        subtitles_lang=languages,
    )
    assert xml.count("<subpicture ") == 32


def test_generate_tsmuxer_meta_clamps_to_32_subtitles():
    subs = [{"path": f"/tmp/sub_{i}.srt", "lang": "eng", "is_bitmap": False} for i in range(40)]
    meta = generate_tsmuxer_meta(
        video_files=["/tmp/track1.m2ts"],
        subtitle_files=subs,
    )
def test_generate_dvd_palette_rgb():
    from dvdcompress.authoring import generate_dvd_palette_rgb
    pal = generate_dvd_palette_rgb()
    lines = [line.strip() for line in pal.strip().splitlines() if line.strip()]
    assert len(lines) == 16
    assert lines[0] == "000000"  # Transparent background / outline
    assert lines[1] == "FFFFFF"  # White text fill
    assert lines[4] == "FFFF00"  # Yellow subtitle text
    assert lines[5] == "38BDF8"  # Menu button highlight (Sky Blue)
    assert lines[6] == "F59E0B"  # Menu button select fill (Amber)
    assert lines[7] == "FBBF24"  # Menu button select outline (Bright Amber)
    assert lines[8] == "3B82F6"  # Menu primary badge accent (Blue)


def test_generate_dvdauthor_xml_with_palette():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[[0.0, 300.0]],
        palette_file="/tmp/palette.rgb",
    )
    assert '<pgc palette="/tmp/palette.rgb">' in xml


def test_generate_dvdauthor_xml_with_menu_and_palette():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg", "/tmp/title2.mpg"],
        chapters_sec=[[0.0, 300.0], [0.0, 600.0]],
        menu_mode=MenuMode.MENU,
        menu_vob="/tmp/menu.mpg",
        palette_file="/tmp/palette.rgb",
    )
    assert '<pgc entry="title" palette="/tmp/palette.rgb">' in xml
    assert '<vob file="/tmp/menu.mpg" pause="inf" />' in xml
    assert '<pgc palette="/tmp/palette.rgb">' in xml





