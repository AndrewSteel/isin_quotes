from __future__ import annotations
from typing import Any, Dict, Optional
import asyncio
from aiohttp import ClientSession, ClientError

from .const import BASE_URL, EXCHANGES_EP, INSTRUMENT_HEADER_EP

class IngApiError(Exception):
    pass

class IngApiClient:
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, path: str) -> Dict[str, Any]:
        url = BASE_URL + path
        try:
            async with self._session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise IngApiError(f"HTTP {resp.status} for {url}: {text[:200]}")
                return await resp.json(content_type=None)
        except (ClientError, asyncio.TimeoutError) as exc:
            raise IngApiError(f"Network error for {url}: {exc}") from exc

    async def fetch_exchanges(self, isin: str) -> Dict[str, Any]:
        path = EXCHANGES_EP.format(isin=isin)
        return await self._get_json(path)

    async def fetch_instrument_header(self, isin: str, exchange_code: Optional[str] = None) -> Dict[str, Any]:
        path = INSTRUMENT_HEADER_EP.format(isin=isin)
        if exchange_code:
            path += f"?exchangeCode={exchange_code}"
        return await self._get_json(path)
