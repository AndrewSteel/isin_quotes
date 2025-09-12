"""
Cached logo fetcher and renderer (Lottie ➜ SVG, Raw SVG).

Only two response forms are supported and the output is **always SVG**:
- Lottie JSON  -> render frame 0 to **SVG** and return /local/... .svg
- Raw SVG (<svg) -> store as **.svg** and return /local/... .svg
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError

from .const import STORAGE_BASE

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HTTP_TIMEOUT_S = 20  # seconds


async def ensure_logo_svg(  # kept name for backward compatibility; returns .svg now
    hass: HomeAssistant,
    session: ClientSession,
    url: str,
    isin: str,
    size: int = 128,  # kept for signature compatibility; not used for SVG
) -> str | None:
    """
    Fetch logo once and store it under /config/www/isin_quotes/<isin>.svg.

    Supported responses (result is always .svg):
        - Lottie JSON  -> render frame 0 to SVG and return /local/... .svg
        - Raw SVG (<svg) -> store as .svg and return /local/... .svg

    Returns:
        Local /local/... path on success, else None.

    """
    base = Path(hass.config.path("www")) / "isin_quotes"
    base.mkdir(parents=True, exist_ok=True)

    svg_path = base / f"{isin}.svg"

    # Cache-Hit
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

    result: str | None = None  # single exit at the end

    # A) JSON: Lottie or JSON with embedded SVG string
    if "application/json" in ctype or data[:1] in (b"{", b"["):
        obj: dict[str, Any] | list[Any] | None
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            obj = None

        if isinstance(obj, dict) and isinstance(obj.get("svg"), str):
            svg_text = obj["svg"]
            # Write only if it really looks like SVG
            if "<svg" in svg_text:
                svg_path.write_text(svg_text, encoding="utf-8")
                result = f"{STORAGE_BASE}/{isin}.svg"
        elif obj is not None:
            # Lottie JSON -> SVG (frame 0) in threadpool (pure-Python exporter)
            try:
                await hass.async_add_executor_job(
                    _render_lottie_svg_sync, obj, svg_path, size
                )
                result = f"{STORAGE_BASE}/{isin}.svg"
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as err:
                _LOGGER.debug(
                    "Lottie SVG render failed for %s: %s", isin, err, exc_info=True
                )

    # B) Raw SVG (not JSON, but content starts with <svg)
    elif data.lstrip().startswith(b"<svg"):
        svg_path.write_bytes(data)
        result = f"{STORAGE_BASE}/{isin}.svg"

    # All other content types are ignored by design
    return result


def _render_lottie_svg_sync(
    obj: dict[str, Any] | list[Any],
    svg_path: Path,
    _size: int,
) -> str:
    """
    Render Lottie frame 0 to **SVG** using the pure-Python SVG exporter.

    Heavy imports are done lazily to avoid slowing down HA startup.
    """
    error_str = "svg_exporter_unavailable"
    # Lazy imports (speed up HA startup and avoid import cost on module load)
    from lottie import objects

    # Try to import SVG exporter lazily; fail gracefully if unavailable.
    try:
        from lottie.exporters.svg import export_svg  # type: ignore[import]
    except Exception as imp_err:
        raise RuntimeError(error_str) from imp_err

    # Build animation from parsed JSON object
    animation = objects.Animation.load(obj)

    # Export frame 0 as SVG to the target path
    export_svg(animation, str(svg_path), frame=0, animated=False)

    return f"{STORAGE_BASE}/{svg_path.name}"
