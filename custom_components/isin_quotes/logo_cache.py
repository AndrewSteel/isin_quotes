from __future__ import annotations

import json
from aiohttp import ClientSession
from pathlib import Path
from PIL import Image
from typing import Optional

from lottie.importers import import_lottie
from lottie.exporters import exporters
from homeassistant.core import HomeAssistant
from homeassistant.util import asyncio as ha_async

async def ensure_logo_png(
    hass: HomeAssistant,
    session: ClientSession,
    url: str,
    isin: str,
    size: int = 128,
) -> Optional[str]:
    """Fetch logo once, store as /config/www/isin_quotes/<isin>.png and return /local/... url.

    Supports Lottie JSON (renders frame 0 to PNG) and JSON with 'svg' (stores .svg as-is).
    Returns a local /local/... path or None on failure.
    """
    base = Path(hass.config.path("www")) / "isin_quotes"
    base.mkdir(parents=True, exist_ok=True)

    png_path = base / f"{isin}.png"
    if png_path.exists():
        return f"/local/isin_quotes/{isin}.png"

    # Download
    async with session.get(url, timeout=20) as resp:
        data = await resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()

    # JSON: Lottie or JSON with 'svg'
    if "application/json" in ctype or data[:1] in (b"{", b"["):
        try:
            obj = json.loads(data.decode("utf-8"))
        except Exception:
            return None

        # Fallback case: JSON with inline SVG
        if isinstance(obj, dict) and isinstance(obj.get("svg"), str):
            svg_path = base / f"{isin}.svg"
            svg_path.write_text(obj["svg"], encoding="utf-8")
            return f"/local/isin_quotes/{isin}.svg"

        # Lottie JSON → PNG (frame 0)
        try:
            return await ha_async.run_callback_threadsafe(
                hass.loop, _render_lottie_png_sync, obj, png_path, size
            ).result()
        except Exception:
            return None

    # Raw SVG
    if "image/svg" in ctype or data.strip().startswith(b"<svg"):
        svg_path = base / f"{isin}.svg"
        svg_path.write_bytes(data)
        return f"/local/isin_quotes/{isin}.svg"

    # PNG/JPEG direct
    if "image/png" in ctype or data[:8] == b"PNG":
        png_path.write_bytes(data)
        return f"/local/isin_quotes/{isin}.png"
    if "image/jpeg" in ctype or data[:2] == b"ÿØ":
        jpg_path = base / f"{isin}.jpg"
        jpg_path.write_bytes(data)
        return f"/local/isin_quotes/{isin}.jpg"

    return None


def _render_lottie_png_sync(obj, png_path: Path, size: int) -> str:
    """Synchronous part: render Lottie frame 0 to PNG using Pillow renderer."""

    animation = import_lottie.from_dict(obj)
    renderer = exporters.pillow.PillowRenderer(animation, frame=0, width=size, height=size)
    frame_img = renderer.render_frame()

    if frame_img is None:
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(png_path, format="PNG")
        return f"/local/isin_quotes/{png_path.name}"

    frame_img = frame_img.convert("RGBA").resize((size, size))
    frame_img.save(png_path, format="PNG")
    return f"/local/isin_quotes/{png_path.name}"
