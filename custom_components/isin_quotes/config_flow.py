"""Generate config flow for isin_quotes integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api_client import IngApiClient, IngApiError
from .const import (
    CONF_CURRENCY_NAME,
    CONF_CURRENCY_SIGN,
    CONF_EXCHANGE_CODE,
    CONF_EXCHANGE_NAME,
    CONF_ISIN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ISIN_LENGTH,
)

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class IsinQuotesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for isin_quotes."""

    VERSION = 1

    def __init__(self) -> None:
        self._isin: str | None = None
        self._items: list[dict[str, Any]] = []  # from exchanges endpoint

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            isin = user_input.get(CONF_ISIN, "").strip().upper()
            if not isin or len(isin) != ISIN_LENGTH:
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

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle exchange/currency selection."""
        errors: dict[str, str] = {}

        # Collect and enrich
        currencies: dict[str, str] = {}
        default_exchange_code: str | None = None
        enriched: list[dict[str, Any]] = []
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
        def _rank(e: dict[str, Any]) -> int:
            if e["is_default"]:
                return 0
            if e["is_realtime"]:
                return 1
            return 2

        enriched.sort(key=lambda e: (_rank(e), e["sort_order"], e["code"]))

        # Build dropdown options with BADGES ONLY in the label
        exchange_options: list[dict[str, str]] = []
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
            {
                "value": sign,
                "label": f"{sign} - {name}" if name and name != sign else sign,
            }
            for sign, name in currencies.items()
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXCHANGE_CODE,
                    default=default_exchange_code
                    or (exchange_options[0]["value"] if exchange_options else ""),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=exchange_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_CURRENCY_SIGN,
                    default=(
                        currency_options[0]["value"] if currency_options else "EUR"
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=currency_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=15, max=3600, step=5, mode=NumberSelectorMode.BOX
                    )
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

            return self.async_create_entry(
                title=f"{self._isin} ({ex_code})", data=data, options=options
            )

        return self.async_show_form(step_id="select", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Handle Time Interval Options flow."""
        return IsinQuotesOptionsFlow(config_entry)


class IsinQuotesOptionsFlow(config_entries.OptionsFlow):
    """Time Interval Options flow for isin_quotes."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow time interval step."""
        errors: dict[str, str] = {}
        current = self.entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=15, max=3600, step=5, mode=NumberSelectorMode.BOX
                    )
                )
            }
        )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
