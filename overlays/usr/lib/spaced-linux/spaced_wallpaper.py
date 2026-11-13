"""Filesystem and sizing helpers for Spaced's Caja wallpaper action."""

import hashlib
import os
from pathlib import Path


def default_style(image_width, image_height, screen_width, screen_height):
    """Fill close aspect ratios; fit images that would otherwise crop heavily."""
    dimensions = (image_width, image_height, screen_width, screen_height)
    if any(not isinstance(value, int) or value <= 0 for value in dimensions):
        return "scaled"
    image_ratio = image_width / image_height
    screen_ratio = screen_width / screen_height
    return "zoom" if abs(image_ratio / screen_ratio - 1.0) <= 0.15 else "scaled"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_to_wallpapers(source, pictures_directory):
    """Copy source without overwriting a user's file; reuse identical content."""
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError("The selected wallpaper is not a regular file")

    destination_directory = Path(pictures_directory).expanduser() / "Wallpapers"
    destination_directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    try:
        if source.parent.samefile(destination_directory):
            return str(source)
    except OSError:
        pass

    candidate = destination_directory / source.name
    source_digest = None
    if candidate.exists():
        source_digest = _sha256(source)
        if candidate.is_file() and _sha256(candidate) == source_digest:
            return str(candidate)
        candidate = destination_directory / (
            f"{source.stem}-{source_digest[:12]}{source.suffix}"
        )
        if candidate.exists():
            if candidate.is_file() and _sha256(candidate) == source_digest:
                return str(candidate)
            raise FileExistsError(f"Refusing to overwrite {candidate}")

    # Exclusive creation prevents a concurrent action from replacing user data.
    with open(source, "rb") as input_file, open(candidate, "xb") as output_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            output_file.write(chunk)
    os.chmod(candidate, source.stat().st_mode & 0o777)
    return str(candidate)

