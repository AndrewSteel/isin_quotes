"""Cached logo fetcher and renderer (Lottie, SVG, PNG, JPEG)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError
from lottie.exporters import exporters
from lottie.importers import import_lottie
from PIL import Image

from .const import STORAGE_BASE

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HTTP_TIMEOUT_S = 20  # seconds


async def ensure_logo_png(
    hass: HomeAssistant,
    session: ClientSession,
    url: str,
    isin: str,
    size: int = 128,
) -> str | None:
    """
    Fetch logo once and store it under /config/www/isin_quotes/<isin>.{png,svg}.

    Supported responses:
        - Lottie JSON  -> render frame 0 to PNG and return /local/... .png
        - Raw SVG (<svg) -> store as .svg and return /local/... .svg

    Returns:
        Local /local/... path on success, else None.

    """
    base = Path(hass.config.path("www")) / "isin_quotes"
    base.mkdir(parents=True, exist_ok=True)

    png_path = base / f"{isin}.png"
    svg_path = base / f"{isin}.svg"

    # Cache-Hit
    if png_path.exists():
        return f"{STORAGE_BASE}/{isin}.png"
    if svg_path.exists():
        return f"{STORAGE_BASE}/{isin}.svg"

    # Download
    try:
        async with session.get(url, timeout=HTTP_TIMEOUT_S) as resp:
            data = await resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
    except (TimeoutError, ClientError) as err:
        _LOGGER.debug("Logo fetch failed for %s: %s", isin, err, exc_info=True)
        return None

    result: str | None = None  # ein gemeinsamer Rückgabepunkt

    # Fall A: JSON (Lottie oder JSON mit eingebettetem SVG-String)
    if "application/json" in ctype or data[:1] in (b"{", b"["):
        obj: dict[str, Any] | list[Any] | None
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            obj = None

        if isinstance(obj, dict) and isinstance(obj.get("svg"), str):
            svg_text = obj["svg"]
            # Nur schreiben, wenn es wirklich nach SVG aussieht
            if "<svg" in svg_text:
                svg_path.write_text(svg_text, encoding="utf-8")
                result = f"{STORAGE_BASE}/{isin}.svg"
        elif obj is not None:
            # Lottie JSON -> PNG (frame 0) im Threadpool rendern
            try:
                await hass.async_add_executor_job(
                    _render_lottie_png_sync, obj, png_path, size
                )
                result = f"{STORAGE_BASE}/{isin}.png"
            except (OSError, ValueError, KeyError, TypeError) as err:
                _LOGGER.debug(
                    "Lottie render failed for %s: %s", isin, err, exc_info=True
                )

    # Fall B: rohes SVG (kein JSON, aber Inhalt startet mit <svg)
    elif data.lstrip().startswith(b"<svg"):
        svg_path.write_bytes(data)
        result = f"{STORAGE_BASE}/{isin}.svg"

    # Alle anderen Inhalte ignorieren (keine PNG/JPEG-Unterstützung)
    return result


def _render_lottie_png_sync(obj: dict[str, Any], png_path: Path, size: int) -> str:
    """Render Lottie frame 0 to PNG using Pillow renderer."""
    animation = import_lottie.from_dict(dict(obj))
    renderer = exporters.pillow.PillowRenderer(
        animation, frame=0, width=size, height=size
    )
    frame_img = renderer.render_frame()

    if frame_img is None:
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(png_path, format="PNG")
        return f"{STORAGE_BASE}/{png_path.name}"

    frame_img = frame_img.convert("RGBA").resize((size, size))
    frame_img.save(png_path, format="PNG")
    return f"{STORAGE_BASE}/{png_path.name}"
