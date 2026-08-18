"""ISO mastering command builders for DVD-Video and Blu-ray."""

import shutil
from typing import List


def build_xorriso_dvd_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "DVD_DISC",
) -> List[str]:
    """Build xorriso command for mastering DVD ISOs (xorriso does not support -dvd-video or -udf)."""
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "xorriso",
        "-as",
        "mkisofs",
        "-V",
        clean_label,
        "-o",
        output_iso_path,
        author_dir,
    ]


def build_genisoimage_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "DVD_DISC",
) -> List[str]:
    """Build genisoimage command for mastering DVD-Video UDF bridge ISOs."""
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    binary = "genisoimage" if (shutil.which("genisoimage") or not shutil.which("mkisofs")) else "mkisofs"
    return [
        binary,
        "-dvd-video",
        "-udf",
        "-V",
        clean_label,
        "-o",
        output_iso_path,
        author_dir,
    ]


def build_dvd_iso_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "DVD_DISC",
) -> List[str]:
    """Build command for mastering DVD-Video ISOs using genisoimage/mkisofs."""
    return build_genisoimage_command(author_dir, output_iso_path, volume_label)


def build_dvd_fallback_iso_command(
    author_dir: str,
    output_iso_path: str,
    volume_label: str = "DVD_DISC",
) -> List[str]:
    """Build UDF fallback command for mastering DVD ISOs when -dvd-video hits padding bugs."""
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    binary = "genisoimage" if (shutil.which("genisoimage") or not shutil.which("mkisofs")) else "mkisofs"
    return [
        binary,
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
    """Build xorriso command for mastering Blu-ray ISOs."""
    clean_label = "".join([c if c.isalnum() else "_" for c in volume_label.upper()])[:32]
    return [
        "xorriso",
        "-as",
        "mkisofs",
        "-iso-level",
        "3",
        "-V",
        clean_label,
        "-o",
        output_iso_path,
        author_dir,
    ]
