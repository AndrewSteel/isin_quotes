"""
Custom integration to integrate isin_quotes with Home Assistant.

For more details about this integration, please refer to
https://github.com/AndrewSteel/isin_quotes
"""
from __future__ import annotations
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
from .coordinator import QuotesCoordinator

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Merge data + options for the coordinator
    merged: dict[str, Any] = {**entry.data, **{CONF_UPDATE_INTERVAL: entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)}}
    coordinator = QuotesCoordinator(hass, merged)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Handle live update of options (update interval)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True

async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: QuotesCoordinator = store["coordinator"]
    interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    coordinator.set_update_interval(interval)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
