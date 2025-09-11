"""
Custom integration to integrate isin_quotes with Home Assistant.

For more details about this integration, please refer to
https://github.com/AndrewSteel/isin_quotes
"""
from __future__ import annotations
import logging
from urllib.parse import quote_plus
from typing import Optional

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, BASE_URL, LOGO_EP, CONF_ISIN, DE2EN_ASSET
from .coordinator import QuotesCoordinator
from .logo_cache import ensure_logo_png

_LOGGER = logging.getLogger(__name__)

SERVICE_RENDER_LOGO = "render_logo"
SCHEMA_RENDER_LOGO = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("isin"): cv.string,
        vol.Optional("asset_class"): cv.string,  # EN variant; if omitted we map from meta
        vol.Optional("size", default=128): vol.All(int, vol.Range(min=16, max=1024)),
    }
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up isin_quotes from a config entry."""
    # Merge data+options if you use options; otherwise use entry.data directly
    config = {**entry.data, **entry.options}

    coordinator = QuotesCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Fire-and-forget: prepare a local logo file once (non-blocking)
    hass.async_create_task(_prepare_logo_once(hass, coordinator, entry))

    # Forward the entry to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

async def _prepare_logo_once(hass: HomeAssistant, coordinator: QuotesCoordinator, entry: ConfigEntry) -> None:
    """Build the logo URL from ISIN + assetClass and cache it locally.
    Runs after the first successful refresh, so additionalMetaInformation is available.
    """
    try:
        data = coordinator.data or {}
        meta = data.get("additionalMetaInformation") or []
        asset_raw = str(meta[0]).strip() if meta else None
        if not asset_raw:
            return
        asset_en = DE2EN_ASSET.get(asset_raw, asset_raw)
        isin = entry.data.get(CONF_ISIN)
        if not (isin and asset_en):
            return

        url = BASE_URL + LOGO_EP.format(isin=quote_plus(isin), asset_class=quote_plus(asset_en))
        session = async_get_clientsession(hass)
        local_url = await ensure_logo_png(hass, session, url, isin)
        if local_url:
            _LOGGER.debug("Logo prepared for %s: %s", isin, local_url)
    except Exception as err:  # keep non-fatal
        _LOGGER.debug("Logo preparation failed: %s", err)

async def _handle_render_logo(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service handler for isin_quotes.render_logo.

    Accepts either entry_id or isin; optional asset_class (EN) and size.
    """
    entry_id: Optional[str] = call.data.get("entry_id")
    isin: Optional[str] = call.data.get("isin")
    asset_class_en: Optional[str] = call.data.get("asset_class")
    size: int = int(call.data.get("size", 128))

    # Resolve entry/coordinator
    entry: Optional[ConfigEntry] = None
    coord: Optional[QuotesCoordinator] = None

    if entry_id and entry_id in (hass.data.get(DOMAIN) or {}):
        entry = next((e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id == entry_id), None)
        store = hass.data[DOMAIN].get(entry_id)
        coord = store and store.get("coordinator")
    elif isin:
        # Find the first entry with this ISIN
        for e in hass.config_entries.async_entries(DOMAIN):
            if (e.data or {}).get(CONF_ISIN) == isin:
                entry = e
                store = hass.data.get(DOMAIN, {}).get(e.entry_id)
                coord = store and store.get("coordinator")
                break

    if not entry or not coord:
        _LOGGER.warning("render_logo: No matching entry found (entry_id=%s, isin=%s)", entry_id, isin)
        return

    # Derive ISIN if not provided
    isin = isin or entry.data.get(CONF_ISIN)

    # Derive asset class in EN if not provided
    if not asset_class_en:
        data = coord.data or {}
        meta = data.get("additionalMetaInformation") or []
        asset_raw = str(meta[0]).strip() if meta else None
        asset_class_en = DE2EN_ASSET.get(asset_raw, asset_raw) if asset_raw else None

    if not (isin and asset_class_en):
        _LOGGER.warning("render_logo: Missing ISIN or asset_class after resolution")
        return

    url = BASE_URL + LOGO_EP.format(isin=quote_plus(isin), asset_class=quote_plus(asset_class_en))
    session = async_get_clientsession(hass)
    local_url = await ensure_logo_png(hass, session, url, isin, size=size)
    if local_url:
        _LOGGER.info("render_logo: Prepared %s -> %s", isin, local_url)
    else:
        _LOGGER.warning("render_logo: Failed to prepare logo for %s", isin)