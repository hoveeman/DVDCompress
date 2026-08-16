"""Media prober and stream analyzer module using ffprobe."""

import json
import os
import asyncio
from typing import Dict, Any
from dvdcompress.models import MediaInfo, AudioStreamInfo, SubtitleStreamInfo

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
