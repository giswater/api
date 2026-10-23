"""
Copyright © 2026 by BGEO. All rights reserved.
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover - dependency is installed with the app
    pillow_heif = None

logger = logging.getLogger(__name__)

mimetypes.add_type("image/heic", ".heic")
mimetypes.add_type("image/heif", ".heif")

COMPRESS_BYTES = 1_048_576
MAX_EDGE = 2560
THUMB_EDGE = 400
_HEIC = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}
_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 36867


def resolve_content_type(name: str, content_type: str | None) -> str:
    raw = (content_type or "").split(";", 1)[0].strip().lower()
    if raw and raw != "application/octet-stream":
        return raw
    guessed, _ = mimetypes.guess_type(name)
    return (guessed or raw or "application/octet-stream").lower()


def process_upload(path: Path, content_type: str) -> dict:
    """Compress images, pull EXIF, and write thumb.jpg when we know how.

    Returns path, content_type, size, thumbnail_path, coordinates, metadata.
    A processing failure keeps the original file and leaves thumbnail_path null.
    """
    content_type = resolve_content_type(path.name, content_type)
    result = _fresh(path, content_type)
    if _is_image(content_type):
        try:
            _process_image(path, content_type, result)
        except Exception:
            logger.exception("cmms image processing failed for %s", path.name)
            result.update(_fresh(path, content_type))
    elif content_type == "application/pdf":
        try:
            result["thumbnail_path"] = _pdf_thumbnail(path)
        except Exception:
            logger.exception("cmms pdf thumbnail failed for %s", path.name)
            (path.parent / "thumb.jpg").unlink(missing_ok=True)
    return result


def _fresh(path: Path, content_type: str) -> dict:
    size = path.stat().st_size if path.exists() else 0
    return {
        "path": path,
        "content_type": content_type,
        "size": size,
        "thumbnail_path": None,
        "coordinates": None,
        "metadata": {},
    }


def _is_image(content_type: str) -> bool:
    return content_type.startswith("image/") or content_type in _HEIC


def _is_heic(content_type: str) -> bool:
    return content_type in _HEIC


def _process_image(path: Path, content_type: str, result: dict) -> None:
    source = ImageOps.exif_transpose(Image.open(path))
    thumb_source = source
    try:
        source.load()
        coordinates, meta = _read_exif(source)
        result["coordinates"] = coordinates
        result["metadata"].update(meta)
        stored, thumb_source, content_type = _compress(path, source, content_type, result["metadata"])
        result["path"] = stored
        result["content_type"] = content_type
        result["size"] = stored.stat().st_size
        try:
            result["thumbnail_path"] = _thumbnail(thumb_source, stored.parent)
        except Exception:
            logger.exception("cmms thumbnail failed for %s", stored.name)
            result["thumbnail_path"] = None
    finally:
        source.close()
        if thumb_source is not source:
            thumb_source.close()


def _read_exif(img: Image.Image) -> tuple[dict | None, dict]:
    exif = img.getexif()
    meta: dict = {}
    if not exif:
        return None, meta
    make = _text(exif.get(271))
    model = _text(exif.get(272))
    if make:
        meta["make"] = make
    if model:
        meta["model"] = model
    taken = _text(exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL))
    if taken:
        meta["takenAt"] = taken
    return _gps(exif.get_ifd(_GPS_IFD)), meta


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    text = str(value).strip("\x00").strip()
    return text or None


def _number(value) -> float:
    return float(value)


def _dms_to_deg(value) -> float:
    degrees, minutes, seconds = value
    return _number(degrees) + _number(minutes) / 60 + _number(seconds) / 3600


def _ref(value, default: str) -> str:
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    return str(value or default)


def _gps(gps: dict) -> dict | None:
    if not gps or 2 not in gps or 4 not in gps:
        return None
    lat = _dms_to_deg(gps[2])
    lon = _dms_to_deg(gps[4])
    if _ref(gps.get(1), "N").upper().startswith("S"):
        lat = -lat
    if _ref(gps.get(3), "E").upper().startswith("W"):
        lon = -lon
    out = {"lat": lat, "lon": lon}
    if 6 not in gps:
        return out
    alt = _number(gps[6])
    ref = gps.get(5, 0)
    if isinstance(ref, bytes):
        ref = ref[0] if ref else 0
    if int(ref) == 1:
        alt = -alt
    out["alt"] = alt
    return out


def _has_alpha(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA", "PA"):
        return True
    return img.mode == "P" and "transparency" in img.info


def _compress(path: Path, img: Image.Image, content_type: str, meta: dict) -> tuple[Path, Image.Image, str]:
    original_size = path.stat().st_size
    if original_size <= COMPRESS_BYTES and not _is_heic(content_type):
        return path, img, content_type
    webp = _has_alpha(img)
    dest = path.with_suffix(".webp" if webp else ".jpg")
    work = img.copy()
    work.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    meta["originalName"] = path.name
    meta["originalSize"] = original_size
    meta["originalContentType"] = content_type
    tmp = dest.with_name(f".{dest.name}.writing")
    try:
        if webp:
            work.save(tmp, "WEBP", quality=85)
            stored_type = "image/webp"
        else:
            work = work.convert("RGB")
            work.save(tmp, "JPEG", quality=85, optimize=True)
            stored_type = "image/jpeg"
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if dest.resolve() != path.resolve():
        path.unlink(missing_ok=True)
    return dest, work, stored_type


def _thumbnail(img: Image.Image, directory: Path) -> Path:
    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.Resampling.LANCZOS)
    if thumb.mode != "RGB":
        thumb = thumb.convert("RGB")
    dest = directory / "thumb.jpg"
    thumb.save(dest, "JPEG", quality=80)
    return dest


def _pdf_thumbnail(path: Path) -> Path:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[0]
        width, height = page.get_size()
        scale = THUMB_EDGE / max(width, height, 1)
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("RGB")
    finally:
        pdf.close()
    dest = path.parent / "thumb.jpg"
    image.save(dest, "JPEG", quality=80)
    return dest
