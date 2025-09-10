from __future__ import annotations
from typing import Any, Dict, List, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import logging
_LOGGER = logging.getLogger(__name__)

from .const import (
    DOMAIN,
    CONF_ISIN,
    CONF_EXCHANGE_CODE,
    CONF_EXCHANGE_NAME,
    CONF_CURRENCY_SIGN,
    CONF_CURRENCY_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)
from .api_client import IngApiClient, IngApiError

class IsinQuotesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._isin: Optional[str] = None
        self._items: List[Dict[str, Any]] = []  # from exchanges endpoint

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            isin = user_input.get(CONF_ISIN, "").strip().upper()
            if not isin or len(isin) < 10:
                errors[CONF_ISIN] = "invalid_isin"
            else:
                session = aiohttp_client.async_get_clientsession(self.hass)
                client = IngApiClient(session)
                try:
                    data = await client.fetch_exchanges(isin)
                except IngApiError:
                    errors["base"] = "cannot_connect"
                else:
                    items = data.get("items") or []
                    if not items:
                        errors["base"] = "no_exchanges"
                    else:
                        self._isin = isin
                        self._items = items
                        return await self.async_step_select()

        schema = vol.Schema({vol.Required(CONF_ISIN): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        assert self._isin is not None
        errors: Dict[str, str] = {}

        # Collect and enrich
        currencies: Dict[str, str] = {}
        default_exchange_code: Optional[str] = None
        enriched: List[Dict[str, Any]] = []
        for it in self._items:
            code = str(it.get("exchangeCode") or "")
            name = str(it.get("exchangeName") or "")
            cs = str(it.get("currencySign") or it.get("currencyIsoCode") or "")
            cn = str(it.get("currencyName") or "")
            is_default = bool(it.get("isDefault") is True)
            is_realtime = bool(it.get("isRealtime") is True)
            sort_order = it.get("sortOrder")

            if cs:
                currencies[cs] = cn or cs
            if is_default:
                default_exchange_code = code

            enriched.append(
                {
                    "code": code,
                    "name": name,
                    "is_default": is_default,
                    "is_realtime": is_realtime,
                    "sort_order": sort_order if isinstance(sort_order, int) else 9999,
                }
            )

        # Sort: default first, then realtime, then others; then sortOrder; then code
        def _rank(e: Dict[str, Any]) -> int:
            if e["is_default"]:
                return 0
            if e["is_realtime"]:
                return 1
            return 2

        enriched.sort(key=lambda e: (_rank(e), e["sort_order"], e["code"]))

        # Build dropdown options with BADGES ONLY in the label
        exchange_options: List[Dict[str, str]] = []
        for e in enriched:
            badges = []
            if e["is_default"]:
                badges.append("⭐")
            if e["is_realtime"]:
                badges.append("⚡")
            base = f"{e['name']} ({e['code']})" if e["name"] else e["code"]
            label = base + (" " + " ".join(badges) if badges else "")
            exchange_options.append({"value": e["code"], "label": label})
            
        currency_options = [
            {"value": sign, "label": f"{sign} – {name}" if name and name != sign else sign}
            for sign, name in currencies.items()
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXCHANGE_CODE,
                    default=default_exchange_code or (exchange_options[0]["value"] if exchange_options else ""),
                ): SelectSelector(
                    SelectSelectorConfig(options=exchange_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(
                    CONF_CURRENCY_SIGN,
                    default=(currency_options[0]["value"] if currency_options else "EUR"),
                ): SelectSelector(
                    SelectSelectorConfig(options=currency_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): NumberSelector(
                    NumberSelectorConfig(min=15, max=3600, step=5, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        if user_input is not None:
            ex_code = user_input[CONF_EXCHANGE_CODE]
            curr_sign = user_input[CONF_CURRENCY_SIGN]
            interval = int(user_input[CONF_UPDATE_INTERVAL])

            # Resolve friendly names
            ex_name = None
            curr_name = None
            for it in self._items:
                if str(it.get("exchangeCode")) == ex_code:
                    ex_name = str(it.get("exchangeName"))
                if (it.get("currencySign") or it.get("currencyIsoCode")) == curr_sign:
                    curr_name = str(it.get("currencyName") or curr_sign)

            data = {
                CONF_ISIN: self._isin,
                CONF_EXCHANGE_CODE: ex_code,
                CONF_EXCHANGE_NAME: ex_name,
                CONF_CURRENCY_SIGN: curr_sign,
                CONF_CURRENCY_NAME: curr_name,
            }
            options = {CONF_UPDATE_INTERVAL: interval}

            await self.async_set_unique_id(f"{self._isin}__{ex_code}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(title=f"{self._isin} ({ex_code})", data=data, options=options)

        return self.async_show_form(step_id="select", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return IsinQuotesOptionsFlow(config_entry)

class IsinQuotesOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}
        current = self.entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(min=15, max=3600, step=5, mode=NumberSelectorMode.BOX)
                )
            }
        )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
