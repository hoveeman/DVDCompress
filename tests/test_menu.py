import os
import tempfile
import pytest
from dvdcompress.models import AspectRatio, TVStandard
from dvdcompress.menu import (
    MenuButton,
    get_menu_font,
    generate_dvd_menu_assets,
    build_menu_video_command,
    generate_menu_spumux_xml,
    build_spumux_menu_command,
)


def test_get_menu_font():
    font = get_menu_font(18, bold=True)
    assert font is not None
    font_reg = get_menu_font(14, bold=False)
    assert font_reg is not None


def test_generate_dvd_menu_assets_single_title():
    with tempfile.TemporaryDirectory() as tmpdir:
        titles = [{"name": "My Great Movie", "duration": "01:45:30"}]
        bg_p, hl_p, sel_p, buttons = generate_dvd_menu_assets(
            titles=titles,
            disc_label="MY_MOVIE_DISC",
            tv_standard=TVStandard.NTSC,
            aspect_ratio=AspectRatio.RATIO_16_9,
            output_dir=tmpdir,
        )
        assert os.path.exists(bg_p)
        assert os.path.exists(hl_p)
        assert os.path.exists(sel_p)
        assert len(buttons) == 1
        btn = buttons[0]
        assert btn.name == "1"
        assert btn.x0 % 2 == 0
        assert btn.y0 % 2 == 0
        assert btn.x1 % 2 == 0
        assert btn.y1 % 2 == 0
        assert btn.up == "1"
        assert btn.down == "1"


def test_generate_dvd_menu_assets_multiple_titles():
    with tempfile.TemporaryDirectory() as tmpdir:
        titles = [
            {"name": f"Episode {i+1}", "duration": "25:00"}
            for i in range(5)
        ]
        bg_p, hl_p, sel_p, buttons = generate_dvd_menu_assets(
            titles=titles,
            disc_label="SERIES_SEASON_1",
            tv_standard=TVStandard.NTSC,
            aspect_ratio=AspectRatio.RATIO_16_9,
            output_dir=tmpdir,
        )
        assert len(buttons) == 5
        assert buttons[0].up == "5"
        assert buttons[0].down == "2"
        assert buttons[4].up == "4"
        assert buttons[4].down == "1"
        for b in buttons:
            assert b.x0 % 2 == 0
            assert b.y0 % 2 == 0
            assert b.x1 % 2 == 0
            assert b.y1 % 2 == 0
            assert b.x1 > b.x0
            assert b.y1 > b.y0


def test_generate_dvd_menu_assets_pal_resolution():
    with tempfile.TemporaryDirectory() as tmpdir:
        from PIL import Image
        titles = [{"name": "Episode 1", "duration": "45:00"}]
        bg_p, _, _, _ = generate_dvd_menu_assets(
            titles=titles,
            disc_label="PAL_PROJECT",
            tv_standard=TVStandard.PAL,
            aspect_ratio=AspectRatio.RATIO_16_9,
            output_dir=tmpdir,
        )
        with Image.open(bg_p) as img:
            assert img.size == (720, 576)


def test_generate_dvd_menu_assets_two_column_for_many_titles():
    with tempfile.TemporaryDirectory() as tmpdir:
        titles = [
            {"name": f"Short Film {i+1}", "duration": "10:00"}
            for i in range(10)
        ]
        bg_p, hl_p, sel_p, buttons = generate_dvd_menu_assets(
            titles=titles,
            disc_label="ANTHOLOGY",
            tv_standard=TVStandard.NTSC,
            aspect_ratio=AspectRatio.RATIO_16_9,
            output_dir=tmpdir,
        )
        assert len(buttons) == 10
        # Button 1 should have right pointing to Column 2 (Button 6)
        assert buttons[0].right == "6"
        # Button 6 should have left pointing to Column 1 (Button 1)
        assert buttons[5].left == "1"


def test_build_menu_video_command():
    cmd = build_menu_video_command(
        bg_image_path="/tmp/menu_bg.png",
        output_mpg_path="/tmp/menu_raw.mpg",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        duration_sec=1.0,
    )
    assert "ffmpeg" in cmd
    assert "-loop" in cmd
    assert "/tmp/menu_bg.png" in cmd
    assert "-s" in cmd
    assert "720x480" in cmd
    assert "-aspect" in cmd
    assert "16:9" in cmd
    assert "-f" in cmd
    assert "dvd" in cmd
    assert "/tmp/menu_raw.mpg" in cmd


def test_generate_menu_spumux_xml():
    buttons = [
        MenuButton(name="1", x0=80, y0=120, x1=640, y1=164, up="2", down="2", left="1", right="1"),
        MenuButton(name="2", x0=80, y0=180, x1=640, y1=224, up="1", down="1", left="2", right="2"),
    ]
    xml = generate_menu_spumux_xml(
        highlight_path="/tmp/hl.png",
        select_path="/tmp/sel.png",
        buttons=buttons,
        tv_standard=TVStandard.NTSC,
    )
    assert '<subpictures format="NTSC">' in xml
    assert 'highlight="/tmp/hl.png"' in xml
    assert 'select="/tmp/sel.png"' in xml
    assert '<button name="1" x0="80" y0="120" x1="640" y1="164" up="2" down="2" left="1" right="1" />' in xml
    assert '<button name="2" x0="80" y0="180" x1="640" y1="224" up="1" down="1" left="2" right="2" />' in xml


def test_build_spumux_menu_command():
    cmd = build_spumux_menu_command(
        input_mpg_path="/tmp/menu_raw.mpg",
        output_mpg_path="/tmp/menu.mpg",
        xml_path="/tmp/spumux_menu.xml",
    )
    assert cmd == "spumux -m dvd -v 0 /tmp/spumux_menu.xml < /tmp/menu_raw.mpg > /tmp/menu.mpg"
