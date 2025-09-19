"""Generate sensors for ISIN quotes."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ADDITIONAL_META,
    ATTR_CURRENCY_SIGN,
    ATTR_EXCHANGE_CODE,
    ATTR_EXCHANGE_NAME,
    ATTR_ISIN,
    ATTR_NAME,
    ATTR_PRICE_CHANGE_DATE,
    ATTR_SELECTED_CURRENCY,
    ATTR_SELECTED_EXCHANGE,
    ATTR_SOURCE,
    CONF_CURRENCY_NAME,
    CONF_CURRENCY_SIGN,
    CONF_EXCHANGE_CODE,
    CONF_EXCHANGE_NAME,
    CONF_ISIN,
    DOMAIN,
)
from .coordinator import QuotesCoordinator

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up ISIN quote sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        IsinQuotePriceSensor(entry, coordinator),
        IsinQuoteChangePercentSensor(entry, coordinator),
        IsinQuoteChangeAbsoluteSensor(entry, coordinator),
        IsinQuoteTimestampSensor(entry, coordinator),
    ]
    async_add_entities(entities)

    reg = er.async_get(hass)
    target_unique = "isin_quotes__history"
    target_entity_id_prefix = "sensor.isin_quotes_history"

    # Iterate all entities in the registry
    for ent in list(reg.entities.values()):
        # Only consider sensor entities of this integration
        if ent.domain != "sensor" or ent.platform != DOMAIN:
            continue
        if not ent.entity_id.startswith(target_entity_id_prefix):
            continue
        # remove old taget_unique entities
        if ent.unique_id != target_unique:
            reg.async_remove(ent.entity_id)

    global_hist = hass.data[DOMAIN].get("global_history_entity")
    if global_hist is None:
        global_hist = GlobalIsinQuotesHistorySensor()
        async_add_entities([global_hist])
        hass.data[DOMAIN]["global_history_entity"] = global_hist

    hass.data[DOMAIN][entry.entry_id]["history_entity"] = global_hist


class _BaseIsinEntity(CoordinatorEntity[QuotesCoordinator], SensorEntity):
    """Shared base for ISIN sensors."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._isin = entry.data[CONF_ISIN]
        self._exchange_code = entry.data.get(CONF_EXCHANGE_CODE)
        self._exchange_name = entry.data.get(CONF_EXCHANGE_NAME)
        self._currency_sign = entry.data.get(CONF_CURRENCY_SIGN)
        self._currency_name = entry.data.get(CONF_CURRENCY_NAME)
        # exchanges kann in entry fehlen - versuche Coordinator, sonst leere Liste
        exchanges = entry.data.get("exchanges")
        if not exchanges:
            # coordinator.data kann beim ersten Start ebenfalls leer sein – daher "or []"
            exchanges = (getattr(coordinator, "data", None) or {}).get(
                "exchanges"
            ) or []

        # Hilfsfunktion für sichere Suche
        def find_first(
            items: Iterable[Mapping[str, Any]],
            match_key: str,
            match_value: Any,
            return_key: str,
        ) -> str | None:
            for it in items:
                if it.get(match_key) == match_value:
                    return it.get(return_key)
            return None

        # Nur suchen, wenn Schlüssel vorhanden - sonst bleibt None
        self._currency_id = (
            find_first(exchanges, "currencySymbol", self._currency_sign, "currencyId")
            if self._currency_sign
            else None
        )
        self._exchange_id = (
            find_first(exchanges, "exchangeCode", self._exchange_code, "exchangeId")
            if self._exchange_code
            else None
        )

        # Optional: Loggen, falls nicht gefunden – hilft beim Debuggen in HA
        if self._exchange_code and self._exchange_id is None:
            _LOGGER.debug(
                "No exchangeId found for exchangeCode=%s (isin=%s). Exchanges present: %s",
                self._exchange_code,
                self._isin,
                [e.get("exchangeCode") for e in exchanges],
            )
        if self._currency_sign and self._currency_id is None:
            _LOGGER.debug(
                "No currencyId found for currencySymbol=%s (isin=%s). Symbols present: %s",
                self._currency_sign,
                self._isin,
                [e.get("currencySymbol") for e in exchanges],
            )

    def _api_currency(self) -> str | None:
        return (self.coordinator.data or {}).get("currencySign") or self._currency_sign

    def _is_bond(self) -> bool:
        """Detect bonds via additionalMetaInformation[0]."""
        d = self.coordinator.data or {}
        if (d.get("currencySign") or "").strip() == "%":
            return True
        meta = d.get("additionalMetaInformation") or []
        first = str(meta[0]).strip().lower() if meta else ""
        return first == "anleihe"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            ATTR_NAME: d.get("name"),
            ATTR_ISIN: d.get("isin") or self._isin,
            ATTR_CURRENCY_SIGN: d.get("currencySign") or self._currency_sign,
            ATTR_PRICE_CHANGE_DATE: d.get("priceChangeDate"),
            ATTR_EXCHANGE_NAME: d.get("exchangeName"),
            ATTR_EXCHANGE_CODE: d.get("exchangeCode"),
            ATTR_ADDITIONAL_META: d.get("additionalMetaInformation"),
            ATTR_SELECTED_CURRENCY: {
                "id": self._currency_id,
                "sign": self._currency_sign,
                "name": self._currency_name,
            },
            ATTR_SELECTED_EXCHANGE: {
                "id": self._exchange_id,
                "code": self._exchange_code,
                "name": self._exchange_name,
            },
            ATTR_SOURCE: "ING components-ng/instrumentheader",
        }

    def _asset_class(self) -> str | None:
        """Map the first additionalMetaInformation from DE to EN for logo endpoint."""
        d = self.coordinator.data or {}
        meta = d.get("additionalMetaInformation") or []
        if not meta:
            return None
        raw = str(meta[0]).strip()
        de2en = {
            "Devisenkurs": "ExchangeRate",
            "ETF": "Fund",
            "Fonds": "Fund",
            "Rohstoff": "Commodity",
            "Aktie": "Share",
            "Anleihe": "Bond",
            "Zertifikate": "Derivative",
            "Hebelprodukt": "Derivative",
        }
        return de2en.get(raw, raw)

    @property
    def device_info(self) -> dict:
        """Information about the device."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": f"{self._isin} ({self._exchange_code or 'default'})",
            "manufacturer": "isin_quotes",
            "model": "ING instrument",
        }


class IsinQuotePriceSensor(_BaseIsinEntity):
    """Main price sensor (state = price)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = (
            f"{self._isin}__{self._exchange_code or 'default'}__price"
        )
        self._attr_name = "price"

    @property
    def device_class(self) -> str | None:
        """State class."""
        return None

    @property
    def native_value(self) -> float | None:
        """State value: the price."""
        d = self.coordinator.data or {}
        v = d.get("price")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Unit of measurement: currency sign or '%' for bonds."""
        return "%" if self._is_bond() else self._api_currency()


class IsinQuoteChangePercentSensor(_BaseIsinEntity):
    """Change percent sensor."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = (
            f"{self._isin}__{self._exchange_code or 'default'}__change_pct"
        )
        self._attr_name = "change %"

    @property
    def native_value(self) -> float | None:
        """State value: the change percent."""
        d = self.coordinator.data or {}
        v = d.get("changePercent")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None


class IsinQuoteChangeAbsoluteSensor(_BaseIsinEntity):
    """
    Change absolute sensor.

    - For currencies → monetary measurement (same unit as price)
    - For bonds (Anleihe) → percentage points ('%')
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = (
            f"{self._isin}__{self._exchange_code or 'default'}__change_abs"
        )
        self._attr_name = "change abs"

    @property
    def device_class(self) -> str | None:
        """State class."""
        return None

    @property
    def native_value(self) -> float | None:
        """State value: the change absolute."""
        d = self.coordinator.data or {}
        v = d.get("changeAbsolute")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Unit of measurement: currency sign or '%' for bonds."""
        return "%" if self._is_bond() else self._api_currency()


class IsinQuoteTimestampSensor(_BaseIsinEntity):
    """Price timestamp sensor using device_class=timestamp."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = f"{self._isin}__{self._exchange_code or 'default'}__ts"
        self._attr_name = "timestamp"

    @property
    def native_value(self) -> datetime | None:
        """State value: the price timestamp as datetime or None."""
        ts = (self.coordinator.data or {}).get("priceChangeDate")
        if not ts:
            return None

        # Already a datetime?
        if isinstance(ts, datetime):
            return (
                ts
                if ts.tzinfo is not None
                else ts.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            )

        # Epoch seconds/milliseconds
        if isinstance(ts, (int, float)):
            secs = ts / 1000.0 if ts > 10**11 else float(ts)
            return dt_util.utc_from_timestamp(secs)

        # String → parse
        dt = dt_util.parse_datetime(str(ts))
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(ts))
            except ValueError:
                return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt


class GlobalIsinQuotesHistorySensor(SensorEntity):
    """Global history payload holder shared across all entries."""

    _attr_unique_id = "isin_quotes__history"
    _attr_name = "ISIN Quotes History"
    _attr_has_entity_name = True
    _attr_icon = "mdi:chart-line"
    _attr_native_value = 0

    def __init__(self) -> None:
        """Initialize the history sensor."""
        self._payload: dict | list | None = None

    @property
    def state_class(self) -> SensorStateClass | None:
        """State class."""
        return SensorStateClass.MEASUREMENT

    def set_payload(self, payload: dict | list | None) -> None:
        """Set the payload."""
        self._payload = payload
        length = 0
        if isinstance(payload, dict):
            instruments = payload.get("instruments")
            if isinstance(instruments, list) and instruments:
                inst0 = instruments[0]
                if isinstance(inst0, dict):
                    data = inst0.get("data")
                    if isinstance(data, list):
                        length = len(data)
        self._attr_native_value = length
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        return self._payload if isinstance(self._payload, dict) else None

    @property
    def device_info(self) -> dict | None:
        """Information about the device."""
        return None
