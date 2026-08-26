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
    audio_stream_indices: Optional[List[int]] = None,
    audio_stream_channels: Optional[List[int]] = None,
) -> List[str]:
    """Build FFmpeg command line arguments for DVD-Video compliant MPEG-2 transcoding.

    Args:
        input_file: Source video file path.
        output_mpg: Target MPEG-2 program stream file path (.mpg).
        video_bitrate_kbps: Target video bitrate in kbps.
        audio_stream_idx: Zero-based stream index of audio in input file (fallback if audio_stream_indices not given).
        audio_channels: Number of audio channels for fallback audio stream.
        tv_standard: TV standard (NTSC or PAL, AUTO defaults to NTSC).
        aspect_ratio: Display aspect ratio (16:9 or 4:3).
        use_gpu: Enable CUDA hardware acceleration for decoding.
        is_hdr: Enable HDR/Dolby Vision to SDR filmic tone-mapping and color conversion.
        seek_start_sec: Optional seek start timestamp in seconds for preview clipping.
        duration_sec: Optional duration in seconds for preview clipping.
        audio_stream_indices: Optional list of zero-based stream indices for all selected audio tracks.
        audio_stream_channels: Optional list of channel counts corresponding to audio_stream_indices.

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

    # Video stream mapping
    cmd.extend(["-map", "0:v:0"])

    # Determine audio stream mapping
    target_audio_indices = (
        audio_stream_indices
        if (audio_stream_indices is not None and len(audio_stream_indices) > 0)
        else [audio_stream_idx]
    )
    target_audio_channels = (
        audio_stream_channels
        if (audio_stream_channels is not None and len(audio_stream_channels) == len(target_audio_indices))
        else ([audio_channels] * len(target_audio_indices))
    )

    for a_idx in target_audio_indices:
        cmd.extend(["-map", f"0:{a_idx}"])

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

    # Audio encoding for all mapped audio streams
    if len(target_audio_indices) > 1:
        for i, ch in enumerate(target_audio_channels):
            cmd.extend(["-c:a:" + str(i), "ac3", "-ar:a:" + str(i), "48000"])
            if ch >= 6:
                cmd.extend(["-ac:a:" + str(i), "6", "-b:a:" + str(i), "384k"])
            else:
                cmd.extend(["-ac:a:" + str(i), "2", "-b:a:" + str(i), "192k"])
    else:
        ch = target_audio_channels[0] if target_audio_channels else audio_channels
        cmd.extend(["-c:a", "ac3", "-ar", "48000"])
        if ch >= 6:
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
    audio_stream_indices: Optional[List[int]] = None,
    audio_stream_channels: Optional[List[int]] = None,
) -> List[str]:
    """Build FFmpeg command line for Phase 1 zero-copy GPU hardware HDR/Dolby Vision tone-mapping and downscaling.

    Maintains video frames entirely in CUDA VRAM (NVDEC -> tonemap_cuda -> scale_cuda -> h264_nvenc)
    for maximum speed (200-500+ FPS) without CPU PCIe transfer bottleneck.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-hwaccel_output_format", "cuda",
    ]

    if seek_start_sec is not None and seek_start_sec > 0:
        cmd.extend(["-ss", str(seek_start_sec)])

    cmd.extend(["-i", input_file])

    if duration_sec is not None and duration_sec > 0:
        cmd.extend(["-t", str(duration_sec)])

    cmd.extend(["-map", "0:v:0"])

    target_audio_indices = (
        audio_stream_indices
        if (audio_stream_indices is not None and len(audio_stream_indices) > 0)
        else [audio_stream_idx]
    )
    target_audio_channels = (
        audio_stream_channels
        if (audio_stream_channels is not None and len(audio_stream_channels) == len(target_audio_indices))
        else ([audio_channels] * len(target_audio_indices))
    )

    for a_idx in target_audio_indices:
        cmd.extend(["-map", f"0:{a_idx}"])

    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    final_w, final_h = (720, 480) if is_ntsc else (720, 576)

    # Pure GPU zero-copy CUDA filter pipeline: Mobius tone-mapping + CUDA downscaling to DVD resolution
    vf_filter = f"tonemap_cuda=tonemap=mobius:format=nv12,scale_cuda=w={final_w}:h={final_h}:format=yuv420p"

    cmd.extend(["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "16", "-vf", vf_filter])

    if len(target_audio_indices) > 1:
        for i, ch in enumerate(target_audio_channels):
            cmd.extend(["-c:a:" + str(i), "ac3", "-ar:a:" + str(i), "48000"])
            if ch >= 6:
                cmd.extend(["-ac:a:" + str(i), "6", "-b:a:" + str(i), "384k"])
            else:
                cmd.extend(["-ac:a:" + str(i), "2", "-b:a:" + str(i), "192k"])
    else:
        ch = target_audio_channels[0] if target_audio_channels else audio_channels
        cmd.extend(["-c:a", "ac3", "-ar", "48000"])
        if ch >= 6:
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
    audio_stream_channels: Optional[List[int]] = None,
) -> List[str]:
    """Build fast CPU FFmpeg command to transcode 480p/576p SDR intermediate to DVD-Video MPEG-2."""
    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    target = "ntsc-dvd" if is_ntsc else "pal-dvd"
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_ntsc:
        sar_val, dar_val = ("32/27", "16/9") if is_16_9 else ("8/9", "4/3")
    else:
        sar_val, dar_val = ("64/45", "16/9") if is_16_9 else ("16/15", "4/3")

    target_audio_channels = (
        audio_stream_channels
        if (audio_stream_channels is not None and len(audio_stream_channels) > 0)
        else [audio_channels]
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", intermediate_file,
        "-map", "0:v:0",
    ]
    for i in range(len(target_audio_channels)):
        cmd.extend(["-map", f"0:a:{i}"])

    cmd.extend([
        "-target", target,
        "-b:v", f"{video_bitrate_kbps}k",
        "-maxrate", "8500k",
        "-bufsize", "1835k",
        "-aspect", aspect_ratio.value,
        "-vf", f"setsar={sar_val},setdar={dar_val},format=yuv420p",
    ])

    if len(target_audio_channels) > 1:
        for i, ch in enumerate(target_audio_channels):
            cmd.extend(["-c:a:" + str(i), "ac3", "-ar:a:" + str(i), "48000"])
            if ch >= 6:
                cmd.extend(["-ac:a:" + str(i), "6", "-b:a:" + str(i), "384k"])
            else:
                cmd.extend(["-ac:a:" + str(i), "2", "-b:a:" + str(i), "192k"])
    else:
        ch = target_audio_channels[0]
        cmd.extend(["-c:a", "ac3", "-ar", "48000"])
        if ch >= 6:
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
    audio_stream_indices: Optional[List[int]] = None,
    audio_stream_channels: Optional[List[int]] = None,
    output_audio_files: Optional[List[str]] = None,
) -> List[str]:
    """Build FFmpeg command line arguments for Blu-ray compliant H.264/AVC transcoding."""
    target_video = output_video or output_m2ts or "output.m2ts"
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd.extend(["-hwaccel", "cuda"])
        if is_hdr:
            cmd.extend(["-hwaccel_output_format", "cuda"])
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

    if is_hdr and use_gpu:
        vf_filter = "tonemap_cuda=tonemap=mobius:format=nv12,scale_cuda=w=1920:h=1080:format=yuv420p"
    elif is_hdr:
        vf_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "zscale=t=linear:npl=100,tonemap=tonemap=mobius:desat=0.5:peak=100,"
            "zscale=p=bt709:t=bt709:m=bt709:r=limited,format=yuv420p"
        )
    else:
        vf_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"

    cmd.extend(["-vf", vf_filter])

    if output_audio_files and len(output_audio_files) > 0:
        # Multiple separate elementary audio streams mode
        target_audio_indices = (
            audio_stream_indices
            if (audio_stream_indices is not None and len(audio_stream_indices) == len(output_audio_files))
            else [audio_stream_idx] * len(output_audio_files)
        )
        target_audio_channels = (
            audio_stream_channels
            if (audio_stream_channels is not None and len(audio_stream_channels) == len(output_audio_files))
            else ([audio_channels] * len(output_audio_files))
        )
        cmd.append(target_video)
        for a_idx, a_out, a_ch in zip(target_audio_indices, output_audio_files, target_audio_channels):
            cmd.extend(["-map", f"0:{a_idx}", "-c:a", "ac3", "-ar", "48000"])
            if a_ch >= 6:
                cmd.extend(["-ac", "6", "-b:a", "448k"])
            else:
                cmd.extend(["-ac", "2", "-b:a", "192k"])
            cmd.append(a_out)
    elif output_audio:
        # Single separate elementary stream mode
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
        target_audio_indices = (
            audio_stream_indices
            if (audio_stream_indices is not None and len(audio_stream_indices) > 0)
            else [audio_stream_idx]
        )
        target_audio_channels = (
            audio_stream_channels
            if (audio_stream_channels is not None and len(audio_stream_channels) == len(target_audio_indices))
            else ([audio_channels] * len(target_audio_indices))
        )
        if len(target_audio_indices) > 1:
            for i, (a_idx, a_ch) in enumerate(zip(target_audio_indices, target_audio_channels)):
                cmd.extend(["-map", f"0:{a_idx}"])
                cmd.extend(["-c:a:" + str(i), "ac3", "-ar:a:" + str(i), "48000"])
                if a_ch >= 6:
                    cmd.extend(["-ac:a:" + str(i), "6", "-b:a:" + str(i), "448k"])
                else:
                    cmd.extend(["-ac:a:" + str(i), "2", "-b:a:" + str(i), "192k"])
        else:
            a_idx = target_audio_indices[0]
            a_ch = target_audio_channels[0]
            cmd.extend(["-map", f"0:{a_idx}"])
            cmd.extend(["-c:a", "ac3", "-ar", "48000"])
            if a_ch >= 6:
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
