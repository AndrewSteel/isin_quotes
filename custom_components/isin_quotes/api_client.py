"""InApiClient for fetching data from ING's public API."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import (
    BASE_URL,
    CHART_DATA_EP,
    CHART_META_EP,
    EXCHANGES_EP,
    INSTRUMENT_HEADER_EP,
)


@dataclass(slots=True)
class IngApiError(Exception):
    """Error raised for ING API errors."""

    status: int | None = None
    url: str | None = None
    body_preview: str | None = None
    note: str | None = None  # z.B. "Network error" o.ä.

    MAX_PREVIEW = 200

    def __str__(self) -> str:
        """Generate a human-readable error message."""
        parts: list[str] = []
        if self.note:
            parts.append(self.note)
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.url:
            parts.append(f"for {self.url}")
        msg = " ".join(parts) if parts else "ING API error"
        if self.body_preview:
            preview = self.body_preview[: self.MAX_PREVIEW]
            msg += f": {preview}"
        return msg


class IngApiClient:
    """API client for ING's public API."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, path: str) -> dict[str, Any]:
        url = BASE_URL + path
        try:
            async with self._session.get(url, timeout=20) as resp:
                if resp.status != HTTPStatus.OK:
                    text = await resp.text()
                    raise IngApiError(
                        status=resp.status, url=str(resp.url), body_preview=text
                    )
                return await resp.json(content_type=None)
        except (TimeoutError, ClientError) as exc:
            raise IngApiError(url=url, note="Network error") from exc

    async def fetch_exchanges(self, isin: str) -> dict[str, Any]:
        """Fetch exchanges for the given ISIN."""
        path = EXCHANGES_EP.format(isin=isin)
        return await self._get_json(path)

    async def fetch_instrument_header(
        self, isin: str, exchange_code: str | None = None
    ) -> dict[str, Any]:
        """Fetch instrument header for the given ISIN and optional exchange code."""
        path = INSTRUMENT_HEADER_EP.format(isin=isin)
        if exchange_code:
            path += f"?exchangeCode={exchange_code}"
        return await self._get_json(path)

    async def fetch_time_ranges(self, isin: str) -> dict[str, Any]:
        """Fetch available chart time ranges for the given ISIN."""
        path = CHART_META_EP.format(isin=isin)
        return await self._get_json(path)  # type: ignore[return-value]

    async def fetch_chart_data(
        self,
        isin: str,
        time_range: str,
        exchange_id: int,
        currency_id: int,
        ohlc: bool = False,  # noqa: FBT001,FBT002
    ) -> dict[str, Any] | list[Any]:
        """Fetch chart data for the given ISIN and parameters."""
        ohlc_part = "&ohlc=true" if ohlc else "&ohlc=false"
        path = CHART_DATA_EP.format(
            isin=isin,
            time_range=time_range,
            exchange_id=int(exchange_id),
            currency_id=int(currency_id),
            ohlc_part=ohlc_part,
        )
        return await self._get_json(path)
