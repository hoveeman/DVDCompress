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
    assert "<dvdauthor" in xml
    assert "<vob file=\"/tmp/title1.mpg\"" in xml
    assert "chapters=\"00:00:00.000,00:05:00.000,00:10:00.000\"" in xml
    assert 'format="ntsc"' in xml
    assert "<post>jump title 1;</post>" in xml


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
    assert "<post>jump title 2;</post>" in xml
    assert "<post>jump title 1;</post>" in xml


def test_dvdauthor_xml_empty_chapters():
    xml = generate_dvdauthor_xml(
        titles_mpg=["/tmp/title1.mpg"],
        chapters_sec=[],
    )
    assert "chapters=\"00:00:00.000\"" in xml


def test_generate_tsmuxer_meta():
    meta = generate_tsmuxer_meta(["/tmp/track1.m2ts", "/tmp/track2.m2ts"])
    assert "MUXOPT --no-pcr-on-video-pid --new-audio-pes --blu-ray --vbr --auto-chapters=5" in meta
    assert 'V_MPEG4/ISO/AVC, "/tmp/track1.m2ts", fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/tmp/track1.m2ts"' in meta
    assert 'V_MPEG4/ISO/AVC, "/tmp/track2.m2ts", fps=23.976, insertSEI, contSPS' in meta
    assert 'A_AC3, "/tmp/track2.m2ts"' in meta

    meta_custom = generate_tsmuxer_meta(["/tmp/track1.m2ts"], chapters_sec=[0.0, 300.0, 600.0])
    assert "--custom-chapters=00:00:00.000;00:05:00.000;00:10:00.000" in meta_custom


def test_iso_commands():
    iso_cmd = build_genisoimage_command("/tmp/author", "/output/movie.iso", "MY_MOVIE")
    assert "-dvd-video" in iso_cmd
    assert "-udf" in iso_cmd
    assert "MY_MOVIE" in iso_cmd
    assert "-o" in iso_cmd
    assert "/output/movie.iso" in iso_cmd
    assert "/tmp/author" in iso_cmd

    bd_cmd = build_xorriso_bd_command("/tmp/bd_author", "/output/bd.iso", "MY_BLURAY")
    assert "-udf" in bd_cmd
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
