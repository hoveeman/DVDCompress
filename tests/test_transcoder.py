# tests/test_transcoder.py
import pytest
from dvdcompress.models import TVStandard, AspectRatio
from dvdcompress.transcoder import (
    build_dvd_transcode_command,
    build_bluray_transcode_command,
    parse_ffmpeg_progress_line,
)

def test_dvd_ntsc_command_structure():
    cmd = build_dvd_transcode_command(
        input_file="/media/input.mkv",
        output_mpg="/tmp/output.mpg",
        video_bitrate_kbps=4500,
        audio_stream_idx=1,
        audio_channels=6,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=False,
    )
    cmd_str = " ".join(cmd)
    assert "-target ntsc-dvd" in cmd_str
    assert "-b:v 4500k" in cmd_str
    assert "-aspect 16:9" in cmd_str
    assert "-c:a ac3" in cmd_str
    assert "-ar 48000" in cmd_str
    assert "-ac 6" in cmd_str
    assert "-b:a 384k" in cmd_str
    assert "pad=720:480" in cmd_str
    assert "setsar=32/27" in cmd_str
    assert "setdar=16/9" in cmd_str
    assert cmd[-1] == "/tmp/output.mpg"

def test_dvd_gpu_decode_flag():
    cmd = build_dvd_transcode_command(
        input_file="/media/input.mkv",
        output_mpg="/tmp/output.mpg",
        video_bitrate_kbps=4500,
        audio_stream_idx=1,
        audio_channels=2,
        tv_standard=TVStandard.PAL,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=True,
    )
    cmd_str = " ".join(cmd)
    assert "-hwaccel cuda" in cmd_str
    assert "-target pal-dvd" in cmd_str
    assert "pad=720:576" in cmd_str
    assert "setsar=64/45" in cmd_str
    assert "setdar=16/9" in cmd_str
    assert "-ac 2" in cmd_str
    assert "-b:a 192k" in cmd_str

def test_dvd_auto_standard_and_4_3_aspect():
    cmd = build_dvd_transcode_command(
        input_file="/media/input.mkv",
        output_mpg="/tmp/output.mpg",
        video_bitrate_kbps=3000,
        audio_stream_idx=2,
        audio_channels=2,
        tv_standard=TVStandard.AUTO,
        aspect_ratio=AspectRatio.RATIO_4_3,
        use_gpu=False,
    )
    cmd_str = " ".join(cmd)
    assert "-target ntsc-dvd" in cmd_str
    assert "pad=720:480" in cmd_str
    assert "setsar=8/9" in cmd_str
    assert "setdar=4/3" in cmd_str
    assert "-aspect 4:3" in cmd_str
    assert "-map 0:2" in cmd_str

def test_bluray_nvenc_command():
    cmd = build_bluray_transcode_command(
        input_file="/media/input.mkv",
        output_m2ts="/tmp/output.m2ts",
        video_bitrate_kbps=25000,
        audio_stream_idx=1,
        audio_channels=6,
        use_gpu=True,
    )
    cmd_str = " ".join(cmd)
    assert "-hwaccel cuda" in cmd_str
    assert "h264_nvenc" in cmd_str
    assert "-b:v 25000k" in cmd_str
    assert "-profile:v high" in cmd_str
    assert "-level 4.1" in cmd_str
    assert "-c:a ac3" in cmd_str
    assert "-ac 6" in cmd_str
    assert "-b:a 448k" in cmd_str
    assert cmd[-1] == "/tmp/output.m2ts"

def test_bluray_cpu_libx264_command():
    cmd = build_bluray_transcode_command(
        input_file="/media/input.mkv",
        output_m2ts="/tmp/output.m2ts",
        video_bitrate_kbps=20000,
        audio_stream_idx=0,
        audio_channels=2,
        use_gpu=False,
    )
    cmd_str = " ".join(cmd)
    assert "libx264" in cmd_str
    assert "-bluray-compat 1" in cmd_str
    assert "-profile:v high" in cmd_str
    assert "-level 4.1" in cmd_str
    assert "-b:v 20000k" in cmd_str
    assert "-ac 2" in cmd_str
    assert "-b:a 192k" in cmd_str
    assert "-hwaccel" not in cmd_str


def test_bluray_separate_elementary_streams():
    cmd = build_bluray_transcode_command(
        input_file="/media/input.mp4",
        output_video="/tmp/output.264",
        video_bitrate_kbps=22000,
        output_audio="/tmp/output.ac3",
        audio_stream_idx=1,
        audio_channels=6,
        use_gpu=False,
        fps=29.97,
    )
    cmd_str = " ".join(cmd)
    assert "-map 0:v:0" in cmd_str
    assert "-map 0:1" in cmd_str
    assert "-g 30" in cmd_str
    assert "/tmp/output.264" in cmd
    assert "/tmp/output.ac3" in cmd
    assert cmd[-1] == "/tmp/output.ac3"

def test_parse_ffmpeg_progress():
    line = "frame= 1450 fps= 85.4 q=2.0 size=   45056kB time=00:01:00.45 bitrate=6104.2kbits/s speed=3.56x"
    progress = parse_ffmpeg_progress_line(line)
    assert progress["frame"] == 1450
    assert progress["fps"] == 85.4
    assert progress["speed"] == "3.56x"
    assert progress["time_sec"] == pytest.approx(60.45, 0.1)

def test_parse_ffmpeg_progress_empty_or_partial():
    line = "frame= 50 fps= 0.0 q=0.0 size= 0kB time=00:00:02.00 speed=N/A"
    progress = parse_ffmpeg_progress_line(line)
    assert progress["frame"] == 50
    assert progress["fps"] == 0.0
    assert progress["time_sec"] == pytest.approx(2.0, 0.01)
    assert "speed" not in progress

    line_no_match = "Input #0, matroska,webm, from '/media/input.mkv':"
    progress_empty = parse_ffmpeg_progress_line(line_no_match)
    assert progress_empty == {}

def test_dvd_transcode_command_with_seek_and_duration():
    cmd = build_dvd_transcode_command(
        input_file="/media/test.mkv",
        output_mpg="/output/preview.mpg",
        video_bitrate_kbps=6000,
        seek_start_sec=120.0,
        duration_sec=60.0,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        use_gpu=False,
    )
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    i_idx = cmd.index("-i")
    assert ss_idx < i_idx
    assert cmd[ss_idx + 1] == "120.0"
    assert "-t" in cmd
    t_idx = cmd.index("-t")
    assert t_idx > i_idx
    assert cmd[t_idx + 1] == "60.0"
    assert cmd[-1] == "/output/preview.mpg"

def test_bluray_transcode_command_with_seek_and_duration():
    cmd = build_bluray_transcode_command(
        input_file="/media/test.mkv",
        output_m2ts="/output/preview.m2ts",
        video_bitrate_kbps=25000,
        seek_start_sec=300.5,
        duration_sec=60.0,
        use_gpu=False,
    )
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    i_idx = cmd.index("-i")
    assert ss_idx < i_idx
    assert cmd[ss_idx + 1] == "300.5"
    assert "-t" in cmd
    t_idx = cmd.index("-t")
    assert t_idx > i_idx
    assert cmd[t_idx + 1] == "60.0"
    assert cmd[-1] == "/output/preview.m2ts"


def test_hdr_and_dolby_vision_filter_format():
    """Verify that dvd and bluray filtergraphs force standard yuv420p SDR format."""
    dvd_cmd = build_dvd_transcode_command(
        input_file="/media/wolf_hdr.mkv",
        output_mpg="/output/wolf.mpg",
        video_bitrate_kbps=5400,
        audio_stream_idx=1,
        audio_channels=6,
    )
    dvd_str = " ".join(dvd_cmd)
    assert "format=yuv420p" in dvd_str
    assert "-map 0:s?" not in dvd_str

    bd_cmd = build_bluray_transcode_command(
        input_file="/media/wolf_hdr.mkv",
        output_m2ts="/output/wolf.m2ts",
        video_bitrate_kbps=25000,
        audio_stream_idx=1,
        audio_channels=6,
    )
    bd_str = " ".join(bd_cmd)
    assert "format=yuv420p" in bd_str
    assert "-map 0:s?" not in bd_str


def test_hdr_color_matrix_adaptation_filtergraph():
    """Verify that is_hdr=True injects zscale linearization, Mobius filmic tone-mapping, and target SDR color space conversion."""
    # 1. DVD NTSC with HDR
    dvd_hdr = build_dvd_transcode_command(
        input_file="/media/hdr_clip.mkv",
        output_mpg="/output/hdr_dvd.mpg",
        video_bitrate_kbps=5000,
        is_hdr=True,
    )
    dvd_hdr_str = " ".join(dvd_hdr)
    assert "zscale=t=linear:npl=100" in dvd_hdr_str
    assert "tonemap=tonemap=mobius:desat=0.5:peak=100" in dvd_hdr_str
    assert "zscale=p=smpte170m:t=smpte170m:m=smpte170m:r=limited" in dvd_hdr_str
    assert "format=yuv420p" in dvd_hdr_str

    # 2. DVD PAL with HDR
    dvd_pal_hdr = build_dvd_transcode_command(
        input_file="/media/hdr_clip.mkv",
        output_mpg="/output/hdr_pal.mpg",
        video_bitrate_kbps=5000,
        tv_standard=TVStandard.PAL,
        is_hdr=True,
    )
    dvd_pal_hdr_str = " ".join(dvd_pal_hdr)
    assert "zscale=p=bt470bg:t=bt470bg:m=bt470bg:r=limited" in dvd_pal_hdr_str

    # 3. Blu-ray with HDR
    bd_hdr = build_bluray_transcode_command(
        input_file="/media/hdr_clip.mkv",
        output_m2ts="/output/hdr_bd.m2ts",
        video_bitrate_kbps=25000,
        is_hdr=True,
    )
    bd_hdr_str = " ".join(bd_hdr)
    assert "zscale=t=linear:npl=100" in bd_hdr_str
    assert "tonemap=tonemap=mobius:desat=0.5:peak=100" in bd_hdr_str
    assert "zscale=p=bt709:t=bt709:m=bt709:r=limited" in bd_hdr_str
    assert "format=yuv420p" in bd_hdr_str

    # 4. SDR input should NOT have tonemap or zscale overhead
    dvd_sdr = build_dvd_transcode_command(
        input_file="/media/sdr_clip.mp4",
        output_mpg="/output/sdr_dvd.mpg",
        video_bitrate_kbps=5000,
        is_hdr=False,
    )
    dvd_sdr_str = " ".join(dvd_sdr)
    assert "tonemap" not in dvd_sdr_str
    assert "zscale" not in dvd_sdr_str


def test_dvd_transcode_maps_only_video_and_audio():
    """Verify that DVD transcode maps only video 0:v:0 and audio 0:a, never subtitles."""
    cmd = build_dvd_transcode_command(
        input_file="/media/movie_with_subs.mkv",
        output_mpg="/output/movie.mpg",
        video_bitrate_kbps=5400,
        audio_stream_idx=1,
        audio_channels=6,
    )
    cmd_str = " ".join(cmd)
    assert "-map 0:v:0" in cmd_str
    assert "-map 0:1" in cmd_str
    assert "-map 0:2" not in cmd_str
    assert "-map 0:s" not in cmd_str


def test_dvd_aspect_ratio_filter_letterbox_and_pillarbox():
    """Verify DVD transcode video filter expressions for widescreen anamorphic and standard DAR."""
    # 1. NTSC 16:9 widescreen
    cmd_ntsc_16_9 = build_dvd_transcode_command(
        input_file="/media/scope_movie.mkv",
        output_mpg="/output/scope.mpg",
        video_bitrate_kbps=5000,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
    )
    vf_ntsc_16_9 = cmd_ntsc_16_9[cmd_ntsc_16_9.index("-vf") + 1]
    assert "scale=w='if(gte(dar,16/9),720,max(2,min(720,trunc(720*dar/(16/9)/2)*2)))'" in vf_ntsc_16_9
    assert "h='if(gte(dar,16/9),max(2,min(480,trunc(480*(16/9)/dar/2)*2)),480)'" in vf_ntsc_16_9
    assert "pad=720:480:(ow-iw)/2:(oh-ih)/2" in vf_ntsc_16_9
    assert "setsar=32/27" in vf_ntsc_16_9
    assert "setdar=16/9" in vf_ntsc_16_9

    # 2. PAL 16:9 widescreen
    cmd_pal_16_9 = build_dvd_transcode_command(
        input_file="/media/scope_movie.mkv",
        output_mpg="/output/scope_pal.mpg",
        video_bitrate_kbps=5000,
        tv_standard=TVStandard.PAL,
        aspect_ratio=AspectRatio.RATIO_16_9,
    )
    vf_pal_16_9 = cmd_pal_16_9[cmd_pal_16_9.index("-vf") + 1]
    assert "scale=w='if(gte(dar,16/9),720,max(2,min(720,trunc(720*dar/(16/9)/2)*2)))'" in vf_pal_16_9
    assert "h='if(gte(dar,16/9),max(2,min(576,trunc(576*(16/9)/dar/2)*2)),576)'" in vf_pal_16_9
    assert "pad=720:576:(ow-iw)/2:(oh-ih)/2" in vf_pal_16_9
    assert "setsar=64/45" in vf_pal_16_9

    # 3. NTSC 4:3 fullscreen
    cmd_ntsc_4_3 = build_dvd_transcode_command(
        input_file="/media/tv_show.mkv",
        output_mpg="/output/tv.mpg",
        video_bitrate_kbps=5000,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_4_3,
    )
    vf_ntsc_4_3 = cmd_ntsc_4_3[cmd_ntsc_4_3.index("-vf") + 1]
    assert "scale=w='if(gte(dar,4/3),720,max(2,min(720,trunc(720*dar/(4/3)/2)*2)))'" in vf_ntsc_4_3
    assert "h='if(gte(dar,4/3),max(2,min(480,trunc(480*(4/3)/dar/2)*2)),480)'" in vf_ntsc_4_3
    assert "pad=720:480:(ow-iw)/2:(oh-ih)/2" in vf_ntsc_4_3
    assert "setsar=8/9" in vf_ntsc_4_3
    assert "setdar=4/3" in vf_ntsc_4_3


def test_build_gpu_hdr_intermediate_command():
    from dvdcompress.transcoder import build_gpu_hdr_intermediate_command

    cmd = build_gpu_hdr_intermediate_command(
        input_file="/media/4k_hdr_movie.mkv",
        output_file="/tmp/scratch/intermediate_sdr_1.mp4",
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        audio_stream_idx=1,
        audio_channels=6,
        seek_start_sec=10.0,
        duration_sec=60.0,
    )
    cmd_str = " ".join(cmd)
    assert "-hwaccel cuda" in cmd_str
    assert "-hwaccel_output_format cuda" in cmd_str
    assert "-ss 10.0" in cmd_str
    assert "-t 60.0" in cmd_str
    assert "-c:v h264_nvenc" in cmd_str
    assert "-preset p2" in cmd_str
    assert "-cq 16" in cmd_str
    assert "tonemap_cuda=tonemap=mobius:format=nv12" in cmd_str
    assert "scale_cuda=w=720:h=480:format=yuv420p" in cmd_str
    assert "-c:a ac3 -ar 48000 -ac 6 -b:a 384k" in cmd_str
    assert "/tmp/scratch/intermediate_sdr_1.mp4" in cmd_str


def test_build_dvd_from_intermediate_command():
    from dvdcompress.transcoder import build_dvd_from_intermediate_command

    cmd = build_dvd_from_intermediate_command(
        intermediate_file="/tmp/scratch/intermediate_sdr_1.mp4",
        output_mpg="/output/movie.mpg",
        video_bitrate_kbps=5400,
        tv_standard=TVStandard.NTSC,
        aspect_ratio=AspectRatio.RATIO_16_9,
        audio_channels=2,
    )
    cmd_str = " ".join(cmd)
    assert "-i /tmp/scratch/intermediate_sdr_1.mp4" in cmd_str
    assert "-target ntsc-dvd" in cmd_str
    assert "-b:v 5400k" in cmd_str
    assert "-vf setsar=32/27,setdar=16/9,format=yuv420p" in cmd_str
    assert "-c:a ac3 -ar 48000 -ac 2 -b:a 192k" in cmd_str
    assert "/output/movie.mpg" in cmd_str


def test_dvd_transcode_multi_audio_command():
    cmd = build_dvd_transcode_command(
        input_file="/media/movie.mkv",
        output_mpg="/tmp/title_1.mpg",
        video_bitrate_kbps=4500,
        audio_stream_indices=[1, 2],
        audio_stream_channels=[6, 2],
    )
    cmd_str = " ".join(cmd)
    assert "-map 0:v:0" in cmd_str
    assert "-map 0:1" in cmd_str
    assert "-map 0:2" in cmd_str
    assert "-c:a:0 ac3" in cmd_str
    assert "-b:a:0 384k" in cmd_str
    assert "-c:a:1 ac3" in cmd_str
    assert "-b:a:1 192k" in cmd_str


def test_bluray_transcode_multi_audio_command():
    cmd = build_bluray_transcode_command(
        input_file="/media/movie.mkv",
        output_video="/tmp/title_1.264",
        video_bitrate_kbps=25000,
        audio_stream_indices=[1, 2],
        audio_stream_channels=[6, 2],
        output_audio_files=["/tmp/title_1_track1.ac3", "/tmp/title_1_track2.ac3"],
    )
    assert "/tmp/title_1.264" in cmd
    assert "/tmp/title_1_track1.ac3" in cmd
    assert "/tmp/title_1_track2.ac3" in cmd
    cmd_str = " ".join(cmd)
    assert "-map 0:1" in cmd_str
    assert "-map 0:2" in cmd_str
    assert "-b:a 448k" in cmd_str
    assert "-b:a 192k" in cmd_str


def test_build_gpu_hdr_intermediate_multi_audio_command():
    from dvdcompress.transcoder import build_gpu_hdr_intermediate_command
    cmd = build_gpu_hdr_intermediate_command(
        input_file="/media/movie.mkv",
        output_file="/tmp/intermediate.mp4",
        audio_stream_indices=[1, 2],
        audio_stream_channels=[6, 2],
    )
    cmd_str = " ".join(cmd)
    assert "-map 0:v:0" in cmd_str
    assert "-map 0:1" in cmd_str
    assert "-map 0:2" in cmd_str
    assert "-c:a:0 ac3" in cmd_str
    assert "-b:a:0 384k" in cmd_str
    assert "-c:a:1 ac3" in cmd_str
    assert "-b:a:1 192k" in cmd_str


def test_build_dvd_from_intermediate_multi_audio_command():
    from dvdcompress.transcoder import build_dvd_from_intermediate_command
    cmd = build_dvd_from_intermediate_command(
        intermediate_file="/tmp/intermediate.mp4",
        output_mpg="/tmp/title_1.mpg",
        video_bitrate_kbps=5000,
        audio_stream_channels=[6, 2],
    )
    cmd_str = " ".join(cmd)
    assert "-map 0:v:0" in cmd_str
    assert "-map 0:a:0" in cmd_str
    assert "-map 0:a:1" in cmd_str
    assert "-c:a:0 ac3" in cmd_str
    assert "-b:a:0 384k" in cmd_str
    assert "-c:a:1 ac3" in cmd_str
    assert "-b:a:1 192k" in cmd_str

