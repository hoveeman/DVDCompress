"""Dynamic bitrate budget calculation engine for DVD and Blu-ray authoring."""

from typing import List, Optional
from dvdcompress.models import DiscType, BitrateBudget

# Target usable budgets in MegaBytes (MB = 1000 * 1000 bytes / decimal MB as standard in optical media)
DISC_CAPACITIES_MB = {
    DiscType.DVD5: 4300.0,
    DiscType.DVD9: 7850.0,
    DiscType.BD25: 23000.0,
    DiscType.BD50: 46000.0,
    DiscType.BD66: 61500.0,
    DiscType.BD100: 92000.0,
    DiscType.BD128: 118000.0,
}

# Bitrate constraints in kbps
DVD_MIN_VIDEO_BITRATE = 2000
DVD_MAX_VIDEO_BITRATE = 8000
DVD_MAX_TOTAL_BITRATE = 9800

BD_MIN_VIDEO_BITRATE = 5000
BD_MAX_VIDEO_BITRATE = 35000
BD_MAX_TOTAL_BITRATE = 40000


def calculate_bitrate_budget(
    total_duration_sec: float,
    disc_type: DiscType,
    audio_tracks_kbps: Optional[List[int]] = None,
    video_count: int = 1,
) -> BitrateBudget:
    """
    Calculate the optimal video bitrate and total budget to fit media onto the specified disc.

    Args:
        total_duration_sec: Total duration across all video files in seconds.
        disc_type: Target disc format (DVD-5, DVD-9, BD-25, BD-50).
        audio_tracks_kbps: List of audio stream bitrates in kbps (defaults to [192]).
        video_count: Number of video titles/episodes in the project.

    Returns:
        BitrateBudget detailing allocated bitrates, disc usage, and warnings if oversized.
    """
    if audio_tracks_kbps is None or len(audio_tracks_kbps) == 0:
        audio_tracks_kbps = [192]

    if total_duration_sec <= 0:
        total_duration_sec = 1.0

    target_mb = DISC_CAPACITIES_MB[disc_type]
    target_bits = target_mb * 1000 * 1000 * 8

    # Reserve 4% for container multiplexing and filesystem overhead
    mux_factor = 0.96
    usable_bits = target_bits * mux_factor

    # Audio bits
    total_audio_kbps = sum(audio_tracks_kbps)
    audio_bits = total_audio_kbps * 1000 * total_duration_sec

    # Available video bits
    available_video_bits = usable_bits - audio_bits
    raw_video_bitrate_kbps = int((available_video_bits / total_duration_sec) / 1000)

    warnings = []
    fits = True

    is_dvd = disc_type in (DiscType.DVD5, DiscType.DVD9)
    min_v = DVD_MIN_VIDEO_BITRATE if is_dvd else BD_MIN_VIDEO_BITRATE
    max_v = DVD_MAX_VIDEO_BITRATE if is_dvd else BD_MAX_VIDEO_BITRATE
    max_total = DVD_MAX_TOTAL_BITRATE if is_dvd else BD_MAX_TOTAL_BITRATE

    if raw_video_bitrate_kbps < min_v:
        video_bitrate = min_v
        fits = False
        warnings.append(
            f"Content duration ({total_duration_sec/60:.1f} min) exceeds recommended capacity for {disc_type.value.upper()}. Quality may be degraded."
        )
    elif raw_video_bitrate_kbps > max_v:
        video_bitrate = max_v
    else:
        video_bitrate = raw_video_bitrate_kbps

    # Check total bitrate
    if video_bitrate + total_audio_kbps > max_total:
        video_bitrate = max_total - total_audio_kbps

    mux_overhead_kbps = int((video_bitrate + total_audio_kbps) * 0.04)
    total_kbps = video_bitrate + total_audio_kbps + mux_overhead_kbps

    # Estimate used MB
    total_project_bits = total_kbps * 1000 * total_duration_sec
    used_mb = (total_project_bits / 8) / (1000 * 1000)
    capacity_percent = min(100.0, (used_mb / target_mb) * 100.0)

    # Determine optimal media recommendation (Single vs Dual Layer)
    recommended_disc_type = None
    recommendation_reason = None
    mins = round(total_duration_sec / 60.0, 1)

    if is_dvd:
        if total_duration_sec <= 7200:  # <= 120 minutes (2 hours)
            recommended_disc_type = DiscType.DVD5
            if disc_type == DiscType.DVD9:
                recommendation_reason = (
                    f"Single-Layer (DVD-5) is recommended for {mins:.0f} min runtime. "
                    "It fits on a standard 4.7 GB disc at maximum visual quality (8.0 Mbps). "
                    "Dual-Layer (DVD-9) is not needed."
                )
            else:
                recommendation_reason = (
                    f"Single-Layer (DVD-5) is optimal for {mins:.0f} min runtime. "
                    "Encodes at maximum allowable 8,000 kbps DVD quality."
                )
        else:  # > 120 minutes
            recommended_disc_type = DiscType.DVD9
            if disc_type == DiscType.DVD5:
                recommendation_reason = (
                    f"Dual-Layer (DVD-9) is recommended for {mins:.0f} min runtime. "
                    f"DVD-5 requires compressing video down to {video_bitrate} kbps. "
                    "Switching to an 8.5 GB DVD-9 preserves full visual quality."
                )
            else:
                recommendation_reason = (
                    f"Dual-Layer (DVD-9) is optimal for {mins:.0f} min runtime. "
                    "Provides 8.5 GB capacity for high bitrate across long footage."
                )
    else:
        if total_duration_sec <= 8100:  # <= 135 minutes (2.25 hours)
            recommended_disc_type = DiscType.BD25
            if disc_type in (DiscType.BD50, DiscType.BD66, DiscType.BD100, DiscType.BD128):
                recommendation_reason = (
                    f"Single-Layer (BD-25) is recommended for {mins:.0f} min runtime. "
                    "Fits on a 25 GB disc at maximum 35 Mbps Blu-ray master quality. "
                    "50 GB+ is not needed."
                )
            else:
                recommendation_reason = (
                    f"Single-Layer (BD-25) is optimal for {mins:.0f} min runtime. "
                    "Encodes at maximum 35 Mbps Blu-ray master quality."
                )
        elif total_duration_sec <= 16200:  # <= 270 minutes (4.5 hours)
            recommended_disc_type = DiscType.BD50
            if disc_type == DiscType.BD25:
                recommendation_reason = (
                    f"Dual-Layer (BD-50) is recommended for {mins:.0f} min runtime. "
                    "Provides 50 GB capacity to avoid compressing video below master quality."
                )
            else:
                recommendation_reason = (
                    f"Dual-Layer (BD-50) is optimal for {mins:.0f} min runtime. "
                    "Provides 50 GB capacity for high bitrate across all titles."
                )
        else:
            recommended_disc_type = DiscType.BD66 if disc_type == DiscType.BD66 else DiscType.BD100
            recommendation_reason = (
                f"Triple/Quad Layer BDXL is recommended for {mins:.0f} min extended runtime."
            )

    return BitrateBudget(
        disc_type=disc_type,
        target_capacity_mb=round(target_mb, 1),
        used_capacity_mb=round(used_mb, 1),
        capacity_percent=round(capacity_percent, 1),
        video_bitrate_kbps=video_bitrate,
        audio_bitrate_kbps=total_audio_kbps,
        mux_overhead_kbps=mux_overhead_kbps,
        total_bitrate_kbps=total_kbps,
        fits_disc=fits,
        warnings=warnings,
        recommended_disc_type=recommended_disc_type,
        recommendation_reason=recommendation_reason,
    )
