"""ISO mastering command builders for DVD-Video and Blu-ray."""

from typing import List


def build_genisoimage_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "DVD_DISC",
) -> List[str]:
    """Build genisoimage command for mastering DVD-Video UDF bridge ISOs."""
    # Sanitized volume label (max 32 uppercase alphanumeric chars)
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "genisoimage",
        "-dvd-video",
        "-udf",
        "-V",
        clean_label,
        "-o",
        output_iso_path,
        author_dir,
    ]


def build_xorriso_bd_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "BD_DISC",
) -> List[str]:
    """Build xorriso command for mastering Blu-ray UDF 2.50 ISOs."""
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "xorriso",
        "-as",
        "mkisofs",
        "-iso-level",
        "3",
        "-udf",
        "-V",
        clean_label,
        "-o",
        output_iso_path,
        author_dir,
    ]
