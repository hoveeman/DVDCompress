import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from dvdcompress.models import (
    AspectRatio,
    AudioStreamInfo,
    ComplexityAnalysisResult,
    DiscType,
    MediaInfo,
    SubtitleStreamInfo,
    TVStandard,
)

async def run_ffprobe_json(file_path: str) -> Dict[str, Any]:
    """Execute ffprobe asynchronously to extract JSON metadata for a media file."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        file_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {file_path}: {stderr.decode()}")
    return json.loads(stdout.decode())

def parse_ffprobe_output(file_path: str, data: Dict[str, Any]) -> MediaInfo:
    """Parse raw ffprobe JSON output into structured MediaInfo domain model."""
    filename = os.path.basename(file_path)
    streams = data.get("streams", [])
    format_info = data.get("format", {})
    chapters = data.get("chapters", [])

    duration = float(format_info.get("duration", 0.0) or 0.0)
    size_bytes = int(format_info.get("size", 0) or 0)

    video_codec = "unknown"
    pix_fmt = None
    color_space = None
    color_transfer = None
    color_primaries = None
    is_hdr = False
    width, height = 720, 480
    dar = "16:9"
    frame_rate = 29.97

    audio_streams = []
    subtitle_streams = []

    for s in streams:
        c_type = s.get("codec_type")
        if c_type == "video" and video_codec == "unknown":
            video_codec = s.get("codec_name", "unknown")
            pix_fmt = s.get("pix_fmt")
            color_space = s.get("color_space")
            color_transfer = s.get("color_transfer") or s.get("color_trc")
            color_primaries = s.get("color_primaries")

            if color_transfer in ("smpte2084", "arib-std-b67", "smpte428"):
                is_hdr = True
            elif color_primaries == "bt2020":
                is_hdr = True
            elif pix_fmt in ("yuv420p10le", "p010le", "yuv422p10le", "yuv444p10le", "yuv420p12le"):
                is_hdr = True

            width = int(s.get("width", 720) or 720)
            height = int(s.get("height", 480) or 480)
            dar = s.get("display_aspect_ratio")
            if dar not in ("16:9", "4:3"):
                # derive from width/height
                ratio = width / height if height > 0 else 1.77
                dar = "16:9" if ratio >= 1.5 else "4:3"

            r_fps = s.get("r_frame_rate", "30/1")
            try:
                num, den = map(float, r_fps.split("/"))
                frame_rate = num / den if den > 0 else 29.97
            except Exception:
                frame_rate = 29.97

            if duration == 0.0 and "duration" in s and s.get("duration"):
                try:
                    duration = float(s.get("duration"))
                except ValueError:
                    pass

        elif c_type == "audio":
            tags = s.get("tags") or {}
            bitrate_val = s.get("bit_rate")
            bitrate = int(bitrate_val) if bitrate_val and str(bitrate_val).isdigit() else None
            audio_streams.append(
                AudioStreamInfo(
                    index=int(s.get("index", len(audio_streams))),
                    codec_name=s.get("codec_name", "unknown"),
                    channels=int(s.get("channels", 2) or 2),
                    channel_layout=s.get("channel_layout") or "stereo",
                    language=tags.get("language") or "und",
                    title=tags.get("title"),
                    bitrate=bitrate,
                )
            )
        elif c_type == "subtitle":
            tags = s.get("tags") or {}
            disp = s.get("disposition") or {}
            is_def = bool(disp.get("default", 0))
            is_forced = bool(disp.get("forced", 0))
            subtitle_streams.append(
                SubtitleStreamInfo(
                    index=int(s.get("index", len(subtitle_streams))),
                    codec_name=s.get("codec_name", "unknown"),
                    language=tags.get("language") or "und",
                    title=tags.get("title"),
                    is_default=is_def,
                    is_forced=is_forced,
                )
            )

    chapter_times = []
    for ch in chapters:
        start_t = float(ch.get("start_time", 0.0) or 0.0)
        if start_t not in chapter_times:
            chapter_times.append(start_t)
    chapter_times.sort()

    return MediaInfo(
        path=file_path,
        filename=filename,
        duration_sec=duration,
        width=width,
        height=height,
        aspect_ratio=dar,
        frame_rate=frame_rate,
        video_codec=video_codec,
        pix_fmt=pix_fmt,
        color_space=color_space,
        color_transfer=color_transfer,
        color_primaries=color_primaries,
        is_hdr=is_hdr,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
        chapters_count=len(chapters),
        chapter_times=chapter_times,
        size_bytes=size_bytes,
    )

async def probe_media_file(file_path: str) -> MediaInfo:
    """Probe a media file using ffprobe and return parsed MediaInfo."""
    data = await run_ffprobe_json(file_path)
    return parse_ffprobe_output(file_path, data)


async def sample_snippet_bitrate(
    input_file: str,
    seek_sec: float,
    sample_duration_sec: float = 2.0,
    is_dvd: bool = True,
    tv_standard: TVStandard = TVStandard.AUTO,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
    is_hdr: bool = False,
) -> Optional[float]:
    """Encode a short snippet at maximum target visual quality and return the empirical bitrate in kbps."""
    is_ntsc = tv_standard in (TVStandard.NTSC, TVStandard.AUTO)
    is_16_9 = aspect_ratio == AspectRatio.RATIO_16_9

    if is_dvd:
        if is_ntsc:
            final_w, final_h = 720, 480
            sar_val = "32/27" if is_16_9 else "8/9"
        else:
            final_w, final_h = 720, 576
            sar_val = "64/45" if is_16_9 else "16/15"

        vf = f"scale={final_w}:{final_h},setsar={sar_val},format=yuv420p"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{seek_sec:.2f}",
            "-i",
            input_file,
            "-t",
            f"{sample_duration_sec:.2f}",
            "-map",
            "0:v:0",
            "-c:v",
            "mpeg2video",
            "-b:v",
            "8000k",
            "-maxrate",
            "8500k",
            "-bufsize",
            "1835k",
            "-q:v",
            "2",
            "-vf",
            vf,
            "-f",
            "rawvideo",
            "/dev/null",
        ]
    else:
        # Blu-ray sampling at 1080p CRF 18
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{seek_sec:.2f}",
            "-i",
            input_file,
            "-t",
            f"{sample_duration_sec:.2f}",
            "-map",
            "0:v:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-maxrate",
            "35000k",
            "-bufsize",
            "30000k",
            "-vf",
            "scale=1920:1080,format=yuv420p",
            "-f",
            "rawvideo",
            "/dev/null",
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_bytes = await proc.communicate()
        stderr_text = stderr_bytes.decode(errors="replace")

        # Extract bitrate from ffmpeg stats line
        match = re.search(r"bitrate=\s*([0-9.]+)\s*kbits/s", stderr_text)
        if match:
            return float(match.group(1))

        # Fallback: extract video data size
        size_match = re.search(r"video:\s*([0-9.]+)\s*(KiB|kB|MB|B)", stderr_text)
        if size_match:
            val = float(size_match.group(1))
            unit = size_match.group(2)
            if unit == "KiB":
                kb = val * 1.024
            elif unit == "MB":
                kb = val * 1024 * 1.024
            elif unit == "B":
                kb = val / 1024
            else:
                kb = val
            bitrate_kbps = (kb * 8) / sample_duration_sec
            return bitrate_kbps
    except Exception:
        pass
    return None


async def analyze_video_complexity(
    input_files: List[str],
    disc_type: DiscType = DiscType.DVD5,
    tv_standard: TVStandard = TVStandard.AUTO,
    aspect_ratio: AspectRatio = AspectRatio.RATIO_16_9,
) -> ComplexityAnalysisResult:
    """Run multi-point fast snippet sampling across media files to estimate real-world VBR output size."""
    if not input_files:
        raise ValueError("No input files provided for complexity analysis.")

    is_dvd = disc_type in (DiscType.DVD5, DiscType.DVD9)
    media_infos = []
    for f in input_files:
        if os.path.exists(f):
            info = await probe_media_file(f)
            media_infos.append(info)

    if not media_infos:
        raise ValueError("Could not probe any of the provided input files.")

    total_duration_sec = sum(m.duration_sec for m in media_infos)
    if total_duration_sec <= 0:
        total_duration_sec = 3600.0

    # Collect audio bitrates based on target AC3 transcode (1 track per title: 384k 5.1ch on DVD, 448k 5.1ch on BD, 192k stereo)
    total_audio_kbps = 0
    for m in media_infos:
        first_audio = m.audio_streams[0] if m.audio_streams else None
        channels = first_audio.channels if first_audio else (6 if not is_dvd else 2)
        if channels >= 6:
            track_kbps = 384 if is_dvd else 448
        else:
            track_kbps = 192
        total_audio_kbps += track_kbps

    avg_audio_kbps = max(192, total_audio_kbps // len(media_infos))

    # Sample each file at multiple points
    all_sample_bitrates = []
    sample_fractions = [0.15, 0.35, 0.50, 0.70, 0.85]

    for m in media_infos:
        dur = m.duration_sec
        if dur <= 5:
            seek_points = [0.5]
        else:
            seek_points = [max(1.0, dur * frac) for frac in sample_fractions]

        for sp in seek_points:
            rate = await sample_snippet_bitrate(
                input_file=m.path,
                seek_sec=sp,
                sample_duration_sec=2.0,
                is_dvd=is_dvd,
                tv_standard=tv_standard,
                aspect_ratio=aspect_ratio,
                is_hdr=m.is_hdr,
            )
            if rate is not None and rate > 100:
                all_sample_bitrates.append(rate)

    if all_sample_bitrates:
        avg_video_bitrate = int(sum(all_sample_bitrates) / len(all_sample_bitrates))
    else:
        avg_video_bitrate = 3800 if is_dvd else 22000

    max_ceiling = 8000 if is_dvd else 35000
    min_floor = 1500 if is_dvd else 5000
    empirical_video_bitrate = max(min_floor, min(max_ceiling, avg_video_bitrate))

    # Calculate projected ISO size
    mux_overhead_kbps = int((empirical_video_bitrate + avg_audio_kbps) * 0.04)
    total_stream_kbps = empirical_video_bitrate + avg_audio_kbps + mux_overhead_kbps
    projected_bytes = (total_stream_kbps * 1000 * total_duration_sec) / 8
    projected_mb = round(projected_bytes / (1000 * 1000), 1)
    projected_gb = round(projected_mb / 1000.0, 2)

    # Complexity classification
    if is_dvd:
        if empirical_video_bitrate <= 4000:
            complexity_level = "Low (Clean Digital / High Compression Efficiency)"
        elif empirical_video_bitrate <= 6200:
            complexity_level = "Medium (Standard Film / Balanced Detail)"
        else:
            complexity_level = "High (Heavy 35mm Grain / Fast Motion)"
    else:
        if empirical_video_bitrate <= 18000:
            complexity_level = "Low (Clean Digital 1080p)"
        elif empirical_video_bitrate <= 28000:
            complexity_level = "Medium (Standard HD Film)"
        else:
            complexity_level = "High (Ultra-Detailed / Heavy Grain)"

    mins = round(total_duration_sec / 60.0, 1)
    if is_dvd:
        if projected_mb <= 4300.0:
            recommended_disc_type = DiscType.DVD5
            recommendation_text = (
                f"Fast sample analysis shows a {complexity_level.split(' ')[0].lower()} complexity factor. "
                f"Projected final size is ~{projected_gb:.1f} GB ({projected_mb:,.0f} MB) at 100% visual quality. "
                "Single-Layer (DVD-5) is 100% optimal with zero quality compromise."
            )
        else:
            recommended_disc_type = DiscType.DVD9
            recommendation_text = (
                f"Fast sample analysis projects ~{projected_gb:.1f} GB ({projected_mb:,.0f} MB) output. "
                "Dual-Layer (DVD-9) is recommended to prevent compression down to 4.3 GB."
            )
    else:
        if projected_mb <= 23000.0:
            recommended_disc_type = DiscType.BD25
            recommendation_text = (
                f"Fast sample analysis projects ~{projected_gb:.1f} GB output at Blu-ray master quality. "
                "Single-Layer (BD-25) is 100% optimal."
            )
        else:
            recommended_disc_type = DiscType.BD50
            recommendation_text = (
                f"Fast sample analysis projects ~{projected_gb:.1f} GB output. "
                "Dual-Layer (BD-50) is recommended."
            )

    return ComplexityAnalysisResult(
        empirical_video_bitrate_kbps=empirical_video_bitrate,
        projected_iso_size_mb=projected_mb,
        projected_iso_size_gb=projected_gb,
        recommended_disc_type=recommended_disc_type,
        recommendation_text=recommendation_text,
        complexity_level=complexity_level,
        sample_count=len(all_sample_bitrates),
    )

