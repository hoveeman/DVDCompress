"""Transcoding command builder for DVD-Video and Blu-ray encoding with hardware acceleration."""

import re
from typing import List, Dict, Any
from dvdcompress.models import TVStandard, AspectRatio


def build_dvd_transcode_command(
    input_file: str,
    output_mpg: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 2,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    use_gpu: bool = False,
) -> List[str]:
    """Build FFmpeg command line arguments for DVD-Video compliant MPEG-2 transcoding.

    Args:
        input_file: Source video file path.
        output_mpg: Target MPEG-2 program stream file path (.mpg).
        video_bitrate_kbps: Target video bitrate in kbps.
        audio_stream_idx: Zero-based stream index of audio in input file.
        audio_channels: Number of audio channels (e.g. 2 for stereo, 6 for 5.1).
        tv_standard: TV standard (NTSC or PAL, AUTO defaults to NTSC).
        aspect_ratio: Display aspect ratio (16:9 or 4:3).
        use_gpu: Enable CUDA hardware acceleration for decoding.

    Returns:
        List of command-line arguments starting with 'ffmpeg'.
    """
    cmd = ["ffmpeg", "-y"]

    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])

    cmd.extend(["-i", input_file])

    # Video stream mapping, audio mapping, and subtitle mapping
    cmd.extend(["-map", "0:v:0"])
    cmd.extend(["-map", f"0:{audio_stream_idx}"])
    cmd.extend(["-map", "0:s?", "-c:s", "dvdsub"])

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target = "ntsc-dvd" if is_ntsc else "pal-dvd"
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_ntsc:
        final_w, final_h = 720, 480
        sar_val, dar_val = ("32/27", "16/9") if is_16_9 else ("8/9", "4/3")
    else:
        final_w, final_h = 720, 576
        sar_val, dar_val = ("64/45", "16/9") if is_16_9 else ("16/15", "4/3")

    vf_filter = f"scale={final_w}:{final_h},setsar={sar_val},setdar={dar_val}"

    # High quality MPEG-2 video encoding
    cmd.extend(["-target", target])
    cmd.extend(["-b:v", f"{video_bitrate_kbps}k"])
    cmd.extend(["-maxrate", "8500k", "-bufsize", "1835k"])
    cmd.extend(["-aspect", aspect_ratio.value])
    cmd.extend(["-vf", vf_filter])

    # Audio encoding
    cmd.extend(["-c:a", "ac3", "-ar", "48000"])
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "384k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_mpg)
    return cmd


def build_bluray_transcode_command(
    input_file: str,
    output_m2ts: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 6,
    use_gpu: bool = False,
) -> List[str]:
    """Build FFmpeg command line arguments for Blu-ray compliant H.264/AVC transcoding.

    Args:
        input_file: Source video file path.
        output_m2ts: Target MPEG-2 transport stream file path (.m2ts).
        video_bitrate_kbps: Target video bitrate in kbps.
        audio_stream_idx: Zero-based stream index of audio in input file.
        audio_channels: Number of audio channels (e.g. 2 for stereo, 6 for 5.1).
        use_gpu: Enable NVENC hardware acceleration for encoding.

    Returns:
        List of command-line arguments starting with 'ffmpeg'.
    """
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd.extend(["-hwaccel", "cuda", "-i", input_file])
        cmd.extend(["-c:v", "h264_nvenc", "-profile:v", "high", "-level", "4.1"])
    else:
        cmd.extend(["-i", input_file])
        cmd.extend(["-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-bluray-compat", "1"])

    cmd.extend(["-map", "0:v:0", "-map", f"0:{audio_stream_idx}"])
    cmd.extend(["-map", "0:s?", "-c:s", "copy"])
    cmd.extend(["-b:v", f"{video_bitrate_kbps}k", "-maxrate", "35000k", "-bufsize", "30000k"])
    cmd.extend(["-g", "24", "-keyint_min", "1", "-bf", "3"])
    cmd.extend(["-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"])
    cmd.extend(["-c:a", "ac3", "-ar", "48000"])
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "448k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_m2ts)
    return cmd


def parse_ffmpeg_progress_line(line: str) -> Dict[str, Any]:
    """Parse FFmpeg stderr progress output line.

    Args:
        line: Single line of output from FFmpeg execution.

    Returns:
        Dictionary containing extracted progress metrics (frame, fps, time_sec, speed).
    """
    res: Dict[str, Any] = {}
    frame_m = re.search(r"frame=\s*(\d+)", line)
    if frame_m:
        res["frame"] = int(frame_m.group(1))

    fps_m = re.search(r"fps=\s*([\d\.]+)", line)
    if fps_m:
        res["fps"] = float(fps_m.group(1))

    time_m = re.search(r"time=\s*(\d+):(\d+):([\d\.]+)", line)
    if time_m:
        h = int(time_m.group(1))
        m = int(time_m.group(2))
        s = float(time_m.group(3))
        res["time_sec"] = h * 3600 + m * 60 + s

    speed_m = re.search(r"speed=\s*([\d\.]+)x", line)
    if speed_m:
        res["speed"] = f"{speed_m.group(1)}x"

    return res
