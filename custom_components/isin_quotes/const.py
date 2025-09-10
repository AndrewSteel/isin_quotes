"""Constants for isin_quotes."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "isin_quotes"
PLATFORMS = ["sensor"]

BASE_URL = "https://component-api.wertpapiere.ing.de/api/v1/"
EXCHANGES_EP = "components/exchanges/{isin}"
INSTRUMENT_HEADER_EP = "components-ng/instrumentheader/{isin}"

CONF_ISIN = "isin"
CONF_EXCHANGE_CODE = "exchange_code"
CONF_EXCHANGE_NAME = "exchange_name"
CONF_CURRENCY_SIGN = "currency_sign"
CONF_CURRENCY_NAME = "currency_name"
CONF_UPDATE_INTERVAL = "update_interval"

# User-chosen default polling (seconds) if no market-hour control applies
DEFAULT_UPDATE_INTERVAL = 60

# Coordinator dynamic intervals when market hours are defined for the selected exchange
OPEN_UPDATE_INTERVAL = 60       # poll fast when market open
CLOSED_UPDATE_INTERVAL = 15 * 60  # poll slow when market closed (and skip network fetch)

ATTR_NAME = "name"
ATTR_ISIN = "isin"
ATTR_PRICE = "price"
ATTR_CURRENCY_SIGN = "currencySign"
ATTR_PRICE_CHANGE_DATE = "priceChangeDate"
ATTR_EXCHANGE_NAME = "exchangeName"
ATTR_EXCHANGE_CODE = "exchangeCode"
ATTR_ADDITIONAL_META = "additionalMetaInformation"
ATTR_SELECTED_CURRENCY = "selectedCurrency"
ATTR_SELECTED_EXCHANGE = "selectedExchange"
ATTR_SOURCE = "source"
