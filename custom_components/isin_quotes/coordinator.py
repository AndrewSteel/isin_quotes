from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging

from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_ISIN,
    CONF_EXCHANGE_CODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    OPEN_UPDATE_INTERVAL,
    CLOSED_UPDATE_INTERVAL,
)
from .api_client import IngApiClient, IngApiError
from .market_hours import MARKET_HOURS, WEEKDAYS

_LOGGER = logging.getLogger(__name__)

class QuotesCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self.config = config
        self.session = async_get_clientsession(hass)
        self.client = IngApiClient(self.session)
        self._initial_closed_fetch_done = False

        interval = int(config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN} Coordinator",
            update_interval=timedelta(seconds=interval),
        )

    def set_update_interval(self, seconds: int) -> None:
        self.update_interval = timedelta(seconds=int(seconds))

    def _is_market_open(self, exchange_code: Optional[str]) -> Optional[bool]:
        """Return True/False if hours are known, or None if unknown exchange.

        None → no market-hours entry; coordinator should behave with user interval.
        """
        if not exchange_code:
            return None  # default header; do not constrain
        info = MARKET_HOURS.get(exchange_code)
        if not info:
            return None

        tz = ZoneInfo(info["tz"]) if info.get("tz") else dt_util.DEFAULT_TIME_ZONE
        now_local = datetime.now(tz)
        wd_key = WEEKDAYS[now_local.weekday()]
        open_str = str(info.get("open", {}).get(wd_key) or "").strip()
        close_str = str(info.get("close", {}).get(wd_key) or "").strip()
        if not open_str or not close_str:
            return False  # closed today

        o_h, o_m = map(int, open_str.split(":"))
        c_h, c_m = map(int, close_str.split(":"))
        open_dt = now_local.replace(hour=o_h, minute=o_m, second=0, microsecond=0)
        close_dt = now_local.replace(hour=c_h, minute=c_m, second=0, microsecond=0)

        # Handle overnight sessions (close <= open)
        if close_dt <= open_dt:
            return now_local >= open_dt or now_local <= close_dt

        return open_dt <= now_local <= close_dt

    async def _async_update_data(self) -> Dict[str, Any]:
        isin = self.config[CONF_ISIN]
        exchange_code: Optional[str] = self.config.get(CONF_EXCHANGE_CODE)

        market_state = self._is_market_open(exchange_code)

        # 1) No market-hours entry → keep user's interval and always fetch normally
        if market_state is None:
            try:
                data = await self.client.fetch_instrument_header(isin, exchange_code=exchange_code)
            except IngApiError as err_primary:
                raise UpdateFailed(err_primary) from err_primary

            if data and ("price" not in data or data.get("price") is None):
                try:
                    data = await self.client.fetch_instrument_header(isin, exchange_code=None)
                except IngApiError as err_fallback:
                    raise UpdateFailed(err_fallback) from err_fallback
            return data

        # 2) Market-hours known → adapt interval and optionally skip network when closed
        desired = OPEN_UPDATE_INTERVAL if market_state else CLOSED_UPDATE_INTERVAL
        if int(self.update_interval.total_seconds()) != int(desired):
            self.set_update_interval(desired)

        # If market closed: avoid hitting API – return last data if we have it
        if market_state is False:
            if self.data is not None:
                return self.data
            # First time with no data yet: do a single lightweight fetch (default or selected)
            try:
                data = await self.client.fetch_instrument_header(isin, exchange_code=exchange_code)
            except IngApiError as err_primary:
                raise UpdateFailed(err_primary) from err_primary
            # Do not loop more than necessary; keep data and return
            return data

        # 3) Market open → normal fetch, with fallback to default exchange if needed
        try:
            data = await self.client.fetch_instrument_header(isin, exchange_code=exchange_code)
        except IngApiError as err_primary:
            raise UpdateFailed(err_primary) from err_primary

        if data and ("price" not in data or data.get("price") is None):
            try:
                data = await self.client.fetch_instrument_header(isin, exchange_code=None)
            except IngApiError as err_fallback:
                raise UpdateFailed(err_fallback) from err_fallback

        return data