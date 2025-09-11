from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_ISIN,
    CONF_EXCHANGE_CODE,
    CONF_EXCHANGE_NAME,
    CONF_CURRENCY_SIGN,
    CONF_CURRENCY_NAME,
    ATTR_NAME,
    ATTR_ISIN,
    ATTR_CURRENCY_SIGN,
    ATTR_PRICE_CHANGE_DATE,
    ATTR_EXCHANGE_NAME,
    ATTR_EXCHANGE_CODE,
    ATTR_ADDITIONAL_META,
    ATTR_SELECTED_CURRENCY,
    ATTR_SELECTED_EXCHANGE,
    ATTR_SOURCE,
)
from .coordinator import QuotesCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        IsinQuotePriceSensor(entry, coordinator),
        IsinQuoteChangePercentSensor(entry, coordinator),
        IsinQuoteChangeAbsoluteSensor(entry, coordinator),
        IsinQuoteTimestampSensor(entry, coordinator),
    ]
    async_add_entities(entities)


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

    def _api_currency(self) -> Optional[str]:
        return (self.coordinator.data or {}).get("currencySign") or self._currency_sign

    def _is_bond(self) -> bool:
        """Detect bonds via additionalMetaInformation[0] == 'Anleihe' or currencySign == '%'."""
        d = self.coordinator.data or {}
        if (d.get("currencySign") or "").strip() == "%":
            return True
        meta = d.get("additionalMetaInformation") or []
        first = str(meta[0]).strip().lower() if meta else ""
        return first == "anleihe"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
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
                "sign": self._currency_sign,
                "name": self._currency_name,
            },
            ATTR_SELECTED_EXCHANGE: {
                "code": self._exchange_code,
                "name": self._exchange_name,
            },
            ATTR_SOURCE: "ING components-ng/instrumentheader",
        }

    def _asset_class(self) -> Optional[str]:
        """Map the first additionalMetaInformation value from DE to EN for logo endpoint."""
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


class IsinQuotePriceSensor(_BaseIsinEntity):
    """Main price sensor (state = price)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = f"{self._isin}__{self._exchange_code or 'default'}__price"
        self._attr_name = f"{self._isin} ({self._exchange_code or 'default'}) price"

    @property
    def device_class(self) -> Optional[str]:
        # monetary for currencies, None for bonds (percentage price)
        unit = self._api_currency()
        return SensorDeviceClass.MONETARY if unit and unit != "%" else None

    @property
    def native_value(self) -> float | None:
        d = self.coordinator.data or {}
        v = d.get("price")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return "%" if self._is_bond() else self._api_currency()


class IsinQuoteChangePercentSensor(_BaseIsinEntity):
    """Change percent sensor."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = f"{self._isin}__{self._exchange_code or 'default'}__change_pct"
        self._attr_name = f"{self._isin} ({self._exchange_code or 'default'}) change %"

    @property
    def native_value(self) -> float | None:
        d = self.coordinator.data or {}
        v = d.get("changePercent")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None


class IsinQuoteChangeAbsoluteSensor(_BaseIsinEntity):
    """Change absolute sensor.

    - For currencies → monetary measurement (same unit as price)
    - For bonds (Anleihe) → percentage points ('%')
    """

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = f"{self._isin}__{self._exchange_code or 'default'}__change_abs"
        self._attr_name = f"{self._isin} ({self._exchange_code or 'default'}) change abs"

    @property
    def device_class(self) -> Optional[str]:
        unit = self._api_currency()
        return SensorDeviceClass.MONETARY if unit and unit != "%" else None

    @property
    def native_value(self) -> float | None:
        d = self.coordinator.data or {}
        v = d.get("changeAbsolute")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        return "%" if self._is_bond() else self._api_currency()


class IsinQuoteTimestampSensor(_BaseIsinEntity):
    """Price timestamp sensor using device_class=timestamp."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = None

    def __init__(self, entry: ConfigEntry, coordinator: QuotesCoordinator) -> None:
        super().__init__(entry, coordinator)
        self._attr_unique_id = f"{self._isin}__{self._exchange_code or 'default'}__ts"
        self._attr_name = f"{self._isin} ({self._exchange_code or 'default'}) timestamp"

    @property
    def native_value(self) -> datetime | None:
        ts = (self.coordinator.data or {}).get("priceChangeDate")
        if not ts:
            return None

        # Already a datetime?
        if isinstance(ts, datetime):
            return ts if ts.tzinfo is not None else ts.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

        # Epoch seconds/milliseconds
        if isinstance(ts, (int, float)):
            secs = ts / 1000.0 if ts > 10**11 else float(ts)
            return dt_util.utc_from_timestamp(secs)

        # String → parse
        dt = dt_util.parse_datetime(str(ts))
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(ts))
            except Exception:
                return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt