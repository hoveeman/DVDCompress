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

    # Determine optimal media recommendation (Single vs Dual Layer) with exact bitrates
    recommended_disc_type = None
    recommendation_reason = None
    mins = round(total_duration_sec / 60.0, 1)

    if is_dvd:
        dvd5_target_bits = 4300.0 * 1000 * 1000 * 8 * 0.96
        dvd5_v_kbps = min(
            DVD_MAX_VIDEO_BITRATE,
            int(((dvd5_target_bits - audio_bits) / total_duration_sec) / 1000),
        )
        dvd5_v_kbps = max(DVD_MIN_VIDEO_BITRATE, dvd5_v_kbps)

        dvd9_target_bits = 7850.0 * 1000 * 1000 * 8 * 0.96
        dvd9_v_kbps = min(
            DVD_MAX_VIDEO_BITRATE,
            int(((dvd9_target_bits - audio_bits) / total_duration_sec) / 1000),
        )
        dvd9_v_kbps = max(DVD_MIN_VIDEO_BITRATE, dvd9_v_kbps)

        if dvd5_v_kbps >= DVD_MAX_VIDEO_BITRATE:
            recommended_disc_type = DiscType.DVD5
            if disc_type == DiscType.DVD9:
                recommendation_reason = (
                    f"Single-Layer (DVD-5) is recommended for {mins:.0f} min: "
                    "fits on a 4.7 GB disc at the maximum 8,000 kbps DVD quality ceiling. "
                    "An 8.5 GB Dual-Layer disc is not needed."
                )
            else:
                recommendation_reason = (
                    f"Single-Layer (DVD-5) is optimal for {mins:.0f} min: "
                    "encodes at the maximum allowable 8,000 kbps DVD quality."
                )
        elif dvd9_v_kbps > dvd5_v_kbps:
            if disc_type == DiscType.DVD5:
                recommended_disc_type = DiscType.DVD9
                recommendation_reason = (
                    f"DVD-5 encodes this {mins:.0f} min title at {dvd5_v_kbps:,} kbps ({capacity_percent:.0f}% disc usage). "
                    f"Switch to Dual-Layer (DVD-9) to increase quality to {dvd9_v_kbps:,} kbps."
                )
            else:
                recommended_disc_type = DiscType.DVD9
                recommendation_reason = (
                    f"Dual-Layer (DVD-9) is optimal for {mins:.0f} min: "
                    f"provides {dvd9_v_kbps:,} kbps visual quality (DVD-5 is limited to {dvd5_v_kbps:,} kbps)."
                )
        else:
            recommended_disc_type = DiscType.DVD9
            if disc_type == DiscType.DVD5:
                recommendation_reason = (
                    f"Dual-Layer (DVD-9) is recommended for {mins:.0f} min: "
                    f"DVD-5 requires heavy compression ({dvd5_v_kbps:,} kbps). "
                    f"DVD-9 preserves {dvd9_v_kbps:,} kbps quality."
                )
            else:
                recommendation_reason = (
                    f"Dual-Layer (DVD-9) is optimal for {mins:.0f} min: "
                    f"allocates {dvd9_v_kbps:,} kbps across extended content."
                )
    else:
        bd25_target_bits = 23000.0 * 1000 * 1000 * 8 * 0.96
        bd25_v_kbps = min(
            BD_MAX_VIDEO_BITRATE,
            int(((bd25_target_bits - audio_bits) / total_duration_sec) / 1000),
        )
        bd25_v_kbps = max(BD_MIN_VIDEO_BITRATE, bd25_v_kbps)

        bd50_target_bits = 46000.0 * 1000 * 1000 * 8 * 0.96
        bd50_v_kbps = min(
            BD_MAX_VIDEO_BITRATE,
            int(((bd50_target_bits - audio_bits) / total_duration_sec) / 1000),
        )
        bd50_v_kbps = max(BD_MIN_VIDEO_BITRATE, bd50_v_kbps)

        if bd25_v_kbps >= BD_MAX_VIDEO_BITRATE:
            recommended_disc_type = DiscType.BD25
            if disc_type in (DiscType.BD50, DiscType.BD66, DiscType.BD100, DiscType.BD128):
                recommendation_reason = (
                    f"Single-Layer (BD-25) is recommended for {mins:.0f} min: "
                    "fits on a 25 GB disc at the maximum 35 Mbps master quality ceiling. "
                    "50 GB+ is not needed."
                )
            else:
                recommendation_reason = (
                    f"Single-Layer (BD-25) is optimal for {mins:.0f} min: "
                    "encodes at the maximum 35 Mbps Blu-ray master quality."
                )
        elif bd50_v_kbps > bd25_v_kbps:
            if disc_type == DiscType.BD25:
                recommended_disc_type = DiscType.BD50
                recommendation_reason = (
                    f"BD-25 encodes this {mins:.0f} min title at {bd25_v_kbps:,} kbps. "
                    f"Switch to Dual-Layer (BD-50) to increase quality to {bd50_v_kbps:,} kbps."
                )
            else:
                recommended_disc_type = DiscType.BD50
                recommendation_reason = (
                    f"Dual-Layer (BD-50) is optimal for {mins:.0f} min: "
                    f"provides {bd50_v_kbps:,} kbps visual quality (BD-25 is limited to {bd25_v_kbps:,} kbps)."
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
