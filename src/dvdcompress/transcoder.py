"""Transcoding command builder for DVD-Video and Blu-ray encoding with hardware acceleration."""

import re
from typing import Any, Dict, List, Optional
from dvdcompress.models import AspectRatio, TVStandard



def build_dvd_transcode_command(
    input_file: str,
    output_mpg: str,
    video_bitrate_kbps: int,
    audio_stream_idx: int = 1,
    audio_channels: int = 2,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    use_gpu: bool = False,
    is_hdr: bool = False,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
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
        is_hdr: Enable HDR/Dolby Vision to SDR filmic tone-mapping and color conversion.
        seek_start_sec: Optional seek start timestamp in seconds for preview clipping.
        duration_sec: Optional duration in seconds for preview clipping.

    Returns:
        List of command-line arguments starting with 'ffmpeg'.
    """
    cmd = ["ffmpeg", "-y"]

    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])

    if seek_start_sec is not None and seek_start_sec > 0:
        cmd.extend(["-ss", str(seek_start_sec)])

    cmd.extend(["-i", input_file])

    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])

    # Video stream mapping and audio mapping
    cmd.extend(["-map", "0:v:0"])
    cmd.extend(["-map", f"0:{audio_stream_idx}"])

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target = "ntsc-dvd" if is_ntsc else "pal-dvd"
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_ntsc:
        final_w, final_h = 720, 480
        sar_val, dar_val = ("32/27", "16/9") if is_16_9 else ("8/9", "4/3")
    else:
        final_w, final_h = 720, 576
        sar_val, dar_val = ("64/45", "16/9") if is_16_9 else ("16/15", "4/3")

    dar_str = "16/9" if is_16_9 else "4/3"
    scale_expr = (
        f"scale=w='if(gte(dar,{dar_str}),{final_w},max(2,min({final_w},trunc({final_w}*dar/({dar_str})/2)*2)))':"
        f"h='if(gte(dar,{dar_str}),max(2,min({final_h},trunc({final_h}*({dar_str})/dar/2)*2)),{final_h})'"
    )
    pad_expr = f"pad={final_w}:{final_h}:(ow-iw)/2:(oh-ih)/2"

    matrix_val = "smpte170m" if is_ntsc else "bt470bg"
    if is_hdr:
        vf_filter = (
            f"{scale_expr},{pad_expr},"
            f"zscale=t=linear:npl=100,tonemap=tonemap=mobius:desat=0.5:peak=100,"
            f"zscale=p={matrix_val}:t={matrix_val}:m={matrix_val}:r=limited,"
            f"setsar={sar_val},setdar={dar_val},format=yuv420p"
        )
    else:
        vf_filter = f"{scale_expr},{pad_expr},setsar={sar_val},setdar={dar_val},format=yuv420p"

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


def build_gpu_hdr_intermediate_command(
    input_file: str,
    output_file: str,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    audio_stream_idx: int = 1,
    audio_channels: int = 2,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> List[str]:
    """Build FFmpeg command line for Phase 1 GPU hardware HDR/Dolby Vision tone-mapping and downscaling.

    Produces a visually lossless 480p/576p SDR H.264 intermediate file with Rec.601 color matrix.
    """
    cmd = ["ffmpeg", "-y", "-hwaccel", "cuda"]

    if seek_start_sec is not None and seek_start_sec > 0:
        cmd.extend(["-ss", str(seek_start_sec)])

    cmd.extend(["-i", input_file])

    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])

    cmd.extend(["-map", "0:v:0"])
    cmd.extend(["-map", f"0:{audio_stream_idx}"])

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_ntsc:
        final_w, final_h = 720, 480
        sar_val, dar_val = ("32/27", "16/9") if is_16_9 else ("8/9", "4/3")
    else:
        final_w, final_h = 720, 576
        sar_val, dar_val = ("64/45", "16/9") if is_16_9 else ("16/15", "4/3")

    dar_str = "16/9" if is_16_9 else "4/3"
    scale_expr = (
        f"scale=w='if(gte(dar,{dar_str}),{final_w},max(2,min({final_w},trunc({final_w}*dar/({dar_str})/2)*2)))':"
        f"h='if(gte(dar,{dar_str}),max(2,min({final_h},trunc({final_h}*({dar_str})/dar/2)*2)),{final_h})'"
    )
    pad_expr = f"pad={final_w}:{final_h}:(ow-iw)/2:(oh-ih)/2"
    matrix_val = "smpte170m" if is_ntsc else "bt470bg"

    vf_filter = (
        f"{scale_expr},{pad_expr},"
        f"zscale=t=linear:npl=100,tonemap=tonemap=mobius:desat=0.5:peak=100,"
        f"zscale=p={matrix_val}:t={matrix_val}:m={matrix_val}:r=limited,"
        f"setsar={sar_val},setdar={dar_val},format=yuv420p"
    )

    cmd.extend(["-c:v", "h264_nvenc", "-preset", "p7", "-cq", "10", "-vf", vf_filter])

    cmd.extend(["-c:a", "ac3", "-ar", "48000"])
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "384k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_file)
    return cmd


def build_dvd_from_intermediate_command(
    intermediate_file: str,
    output_mpg: str,
    video_bitrate_kbps: int,
    tv_standard: TVStandard = TVStandard.NTSC,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    audio_channels: int = 2,
) -> List[str]:
    """Build fast CPU FFmpeg command to transcode 480p/576p SDR intermediate to DVD-Video MPEG-2."""
    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target = "ntsc-dvd" if is_ntsc else "pal-dvd"
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_ntsc:
        sar_val, dar_val = ("32/27", "16/9") if is_16_9 else ("8/9", "4/3")
    else:
        sar_val, dar_val = ("64/45", "16/9") if is_16_9 else ("16/15", "4/3")

    cmd = [
        "ffmpeg", "-y",
        "-i", intermediate_file,
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-target", target,
        "-b:v", f"{video_bitrate_kbps}k",
        "-maxrate", "8500k",
        "-bufsize", "1835k",
        "-aspect", aspect_ratio.value,
        "-vf", f"setsar={sar_val},setdar={dar_val},format=yuv420p",
        "-c:a", "ac3", "-ar", "48000",
    ]
    if audio_channels >= 6:
        cmd.extend(["-ac", "6", "-b:a", "384k"])
    else:
        cmd.extend(["-ac", "2", "-b:a", "192k"])

    cmd.append(output_mpg)
    return cmd


def build_bluray_transcode_command(
    input_file: str,
    output_video: Optional[str] = None,
    video_bitrate_kbps: int = 25000,
    output_audio: Optional[str] = None,
    audio_stream_idx: int = 1,
    audio_channels: int = 6,
    use_gpu: bool = False,
    is_hdr: bool = False,
    seek_start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    fps: Optional[float] = None,
    output_m2ts: Optional[str] = None,
) -> List[str]:
    """Build FFmpeg command line arguments for Blu-ray compliant H.264/AVC transcoding.

    Args:
        input_file: Source video file path.
        output_video: Target video file path (.264, .hevc, or .m2ts).
        video_bitrate_kbps: Target video bitrate in kbps.
        output_audio: Optional target audio elementary stream path (.ac3). If None, multiplexes into output_video.
        audio_stream_idx: Zero-based stream index of audio in input file.
        audio_channels: Number of audio channels (e.g. 2 for stereo, 6 for 5.1).
        use_gpu: Enable NVENC hardware acceleration for encoding.
        is_hdr: Enable HDR/Dolby Vision to SDR filmic tone-mapping and BT.709 color conversion.
        seek_start_sec: Optional seek start timestamp in seconds for preview clipping.
        duration_sec: Optional duration in seconds for preview clipping.
        fps: Optional source/target framerate to determine compliant GOP size.
        output_m2ts: Deprecated legacy alias for output_video.

    Returns:
        List of command-line arguments starting with 'ffmpeg'.
    """
    target_video = output_video or output_m2ts or "output.m2ts"
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])
        if seek_start_sec is not None and seek_start_sec > 0:
            cmd.extend(["-ss", str(seek_start_sec)])
        cmd.extend(["-i", input_file])
        if duration_sec is not None and duration_sec > 0:
            cmd.extend(["-t", str(duration_sec)])
        cmd.extend(["-c:v", "h264_nvenc", "-profile:v", "high", "-level", "4.1"])
    else:
        if seek_start_sec is not None and seek_start_sec > 0:
            cmd.extend(["-ss", str(seek_start_sec)])
        cmd.extend(["-i", input_file])
        if duration_sec is not None and duration_sec > 0:
            cmd.extend(["-t", str(duration_sec)])
        cmd.extend(["-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-bluray-compat", "1"])

    cmd.extend(["-map", "0:v:0"])
    cmd.extend(["-b:v", f"{video_bitrate_kbps}k", "-maxrate", "35000k", "-bufsize", "30000k"])

    gop_size = max(12, int(round(fps))) if (fps and fps > 0) else 24
    cmd.extend(["-g", str(gop_size), "-keyint_min", "1", "-bf", "3"])

    if is_hdr:
        vf_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "zscale=t=linear:npl=100,tonemap=tonemap=mobius:desat=0.5:peak=100,"
            "zscale=p=bt709:t=bt709:m=bt709:r=limited,format=yuv420p"
        )
    else:
        vf_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"

    cmd.extend(["-vf", vf_filter])

    if output_audio:
        # Separate elementary streams mode
        cmd.append(target_video)
        cmd.extend(["-map", f"0:{audio_stream_idx}"])
        cmd.extend(["-c:a", "ac3", "-ar", "48000"])
        if audio_channels >= 6:
            cmd.extend(["-ac", "6", "-b:a", "448k"])
        else:
            cmd.extend(["-ac", "2", "-b:a", "192k"])
        cmd.append(output_audio)
    else:
        # Single multiplexed container mode (e.g. preview video)
        cmd.extend(["-map", f"0:{audio_stream_idx}"])
        cmd.extend(["-c:a", "ac3", "-ar", "48000"])
        if audio_channels >= 6:
            cmd.extend(["-ac", "6", "-b:a", "448k"])
        else:
            cmd.extend(["-ac", "2", "-b:a", "192k"])
        cmd.append(target_video)

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
