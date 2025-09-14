"""
Custom integration to integrate isin_quotes with Home Assistant.

For more details about this integration, please refer to
https://github.com/AndrewSteel/isin_quotes
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import quote_plus

import voluptuous as vol
from aiohttp import ClientError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BASE_URL,
    CONF_ISIN,
    DE2EN_ASSET,
    DOMAIN,
    HISTORY_SUBDIR,
    LOGO_EP,
    STORAGE_BASE,
)
from .coordinator import QuotesCoordinator
from .logo_cache import ensure_logo_svg

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

SERVICE_RENDER_LOGO = "render_logo"
SERVICE_FETCH_HISTORY = "fetch_history"

SCHEMA_RENDER_LOGO = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("isin"): cv.string,
        vol.Optional(
            "asset_class"
        ): cv.string,  # EN variant; if omitted we map from meta
        vol.Optional("size", default=128): vol.All(int, vol.Range(min=16, max=1024)),
    }
)

SCHEMA_FETCH_HISTORY = vol.Schema(
    {
        vol.Required("isin"): cv.string,
        vol.Required("time_range"): vol.In(
            [
                "Intraday",
                "OneWeek",
                "OneMonth",
                "OneYear",
                "FiveYears",
                "Maximum",
            ]
        ),
        vol.Required("exchange_id"): vol.Coerce(int),
        vol.Required("currency_id"): vol.Coerce(int),
        vol.Optional("ohlc", default=False): cv.boolean,  # Intraday: wird ignoriert
    }
)


class HistorySpec(NamedTuple):
    """Specification of a historical data request."""

    isin: str
    time_range: str
    exchange_id: int  # ING exchangeId
    currency_id: int  # ING currencyId
    ohlc: bool  # True=OHLC, False=line chart


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up isin_quotes from a config entry."""
    # Merge data+options if you use options; otherwise use entry.data directly
    config = {**entry.data, **entry.options}

    coordinator = QuotesCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_RENDER_LOGO, _handle_render_logo, schema=SCHEMA_RENDER_LOGO
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FETCH_HISTORY,
        _handle_fetch_history,
        schema=SCHEMA_FETCH_HISTORY,
    )

    # Fire-and-forget: prepare a local logo file once (non-blocking)
    hass.async_create_task(_prepare_logo_once(hass, coordinator, entry))

    # Forward the entry to platforms
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def _on_stop(_: Any) -> None:
        """Cleanup and stop."""
        _LOGGER.debug("isin_quotes stopped")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the isin_quotes integration for a given config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _prepare_logo_once(
    hass: HomeAssistant, coordinator: QuotesCoordinator, entry: ConfigEntry
) -> None:
    """
    Build the logo URL from ISIN + assetClass and cache it locally.

    Runs after the first successful refresh, so additionalMetaInformation is available.
    """
    data = coordinator.data or {}
    meta = data.get("additionalMetaInformation") or []
    asset_raw = str(meta[0]).strip() if meta else None
    if not asset_raw:
        return
    asset_en = DE2EN_ASSET.get(asset_raw, asset_raw)
    isin = entry.data.get(CONF_ISIN)
    if not (isin and asset_en):
        return

    url = BASE_URL + LOGO_EP.format(
        isin=quote_plus(isin), asset_class=quote_plus(asset_en)
    )
    try:
        session = async_get_clientsession(hass)
        local_url = await ensure_logo_svg(hass, session, url, isin)
    except (TimeoutError, ClientError) as net_err:
        _LOGGER.debug("Logo preparation: network issue: %s", net_err, exc_info=True)
        return
    except OSError as fs_err:
        _LOGGER.debug(
            "Logo preparation: filesystem/cache issue: %s", fs_err, exc_info=True
        )
        return
    except ValueError as parse_err:
        # Falls ensure_logo_svg bei ungültigen Inhalten/Status ValueError wirft
        _LOGGER.debug(
            "Logo preparation: invalid response/image: %s", parse_err, exc_info=True
        )
        return
    if local_url:
        _LOGGER.debug("Logo prepared for %s: %s", isin, local_url)


async def _handle_render_logo(hass: HomeAssistant, call: ServiceCall) -> None:
    """
    Service handler for isin_quotes.render_logo.

    Accepts either entry_id or isin; optional asset_class (EN) and size.
    """
    entry_id: str | None = call.data.get("entry_id")
    isin: str | None = call.data.get("isin")
    asset_class_en: str | None = call.data.get("asset_class")
    size: int = int(call.data.get("size", 128))

    # Resolve entry/coordinator
    entry: ConfigEntry | None = None
    coord: QuotesCoordinator | None = None

    if entry_id and entry_id in (hass.data.get(DOMAIN) or {}):
        entry = next(
            (
                e
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id == entry_id
            ),
            None,
        )
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
        _LOGGER.warning(
            "render_logo: No matching entry found (entry_id=%s, isin=%s)",
            entry_id,
            isin,
        )
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

    url = BASE_URL + LOGO_EP.format(
        isin=quote_plus(isin), asset_class=quote_plus(asset_class_en)
    )
    session = async_get_clientsession(hass)
    local_url = await ensure_logo_svg(hass, session, url, isin, size=size)
    if local_url:
        _LOGGER.info("render_logo: Prepared %s -> %s", isin, local_url)
    else:
        _LOGGER.warning("render_logo: Failed to prepare logo for %s", isin)


def _ensure_history_dir(hass: HomeAssistant) -> Path:
    # STORAGE_BASE URL-Path ("/local/isin_quotes") is filesystem /config/www/isin_quotes
    www = Path(hass.config.path("www"))
    target = www / "isin_quotes" / HISTORY_SUBDIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _history_filename(spec: HistorySpec) -> str:
    flag = "ohlc" if spec.ohlc else "line"
    return (
        f"{spec.isin}__{spec.exchange_id}_{spec.currency_id}__"
        f"{spec.time_range}__{flag}__{spec.suffix}.json"
    )


def _today_suffix(time_range: str) -> str:
    if time_range == "Intraday":
        return "intraday"
    return dt_util.now().date().isoformat()


def _public_url(filename: str) -> str:
    return f"{STORAGE_BASE}/{HISTORY_SUBDIR}/{filename}"


async def _save_json(hass: HomeAssistant, path: Path, data: dict | list) -> None:
    txt = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    await hass.async_add_executor_job(path.write_text, txt, "utf-8")


async def _load_json_if_exists(hass: HomeAssistant, path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        txt: str = await hass.async_add_executor_job(path.read_text, "utf-8")
        return json.loads(txt)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Failed to read cached history %s: %s", path, exc)
        return None


async def _handle_fetch_history(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service: fetch historical data and local storage."""
    isin = str(call.data["isin"]).strip()
    time_range = str(call.data["time_range"]).strip()
    exchange_id = int(call.data["exchange_id"])
    currency_id = int(call.data["currency_id"])
    ohlc = bool(call.data.get("ohlc", False))

    # 1) check time range support
    session = async_get_clientsession(hass)
    client = QuotesCoordinator(hass, {}).client
    if client is None:
        from .api_client import IngApiClient

        client = IngApiClient(session)

    try:
        meta = await client.fetch_time_ranges(isin)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning(
            "fetch_history: failed to query timeRanges for %s: %s", isin, exc
        )
        meta = {}

    supported = set((meta or {}).get("timeRanges") or [])
    if supported and time_range not in supported:
        _LOGGER.warning(
            "fetch_history: time_range=%s not in supported %s for %s",
            time_range,
            sorted(supported),
            isin,
        )
        return

    # 2) set cache path
    folder = _ensure_history_dir(hass)
    suffix = _today_suffix(time_range)
    filename = _history_filename(
        isin, time_range, exchange_id, currency_id, ohlc, suffix
    )
    path = folder / filename

    use_cache = time_range != "Intraday" and path.exists()

    # 3) get data (cache or fetch)
    payload: dict | list
    if use_cache:
        cached = await _load_json_if_exists(hass, path)
        if cached is not None:
            payload = cached
        else:
            use_cache = False

    if not use_cache:
        try:
            payload = await client.fetch_chart_data(
                isin=isin,
                time_range=time_range,
                exchange_id=exchange_id,
                currency_id=currency_id,
                ohlc=(ohlc and time_range != "Intraday"),
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "fetch_history: failed to fetch %s/%s: %s", isin, time_range, exc
            )
            return
        try:
            await _save_json(hass, path, payload)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("fetch_history: failed to save cache %s: %s", path, exc)

    # 4) Public URL & Event
    public_url = _public_url(filename)
    hass.bus.async_fire(
        f"{DOMAIN}/history_fetched",
        {
            "isin": isin,
            "time_range": time_range,
            "exchange_id": exchange_id,
            "currency_id": currency_id,
            "ohlc": bool(ohlc and time_range != "Intraday"),
            "file_url": public_url,
        },
    )
    _LOGGER.info(
        "fetch_history: ready for %s %s (ohlc=%s) → %s",
        isin,
        time_range,
        bool(ohlc and time_range != "Intraday"),
        public_url,
    )
