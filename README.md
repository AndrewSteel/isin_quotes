# Isin Quotes – Home Assistant Custom Component

## Overview

This custom component allows you to integrate security price data into Home Assistant by specifying the ISIN (International Securities Identification Number). Multiple exchanges and currencies are supported. In addition to the current price, the integration provides percentage and absolute changes as well as the timestamp of the last price update. An internal market-hours model dynamically adjusts polling frequency according to trading hours.

## Installation (manual)

Since the integration is not yet available via HACS, it must be installed manually:

1. Copy the directory `isin_quotes` into your Home Assistant `custom_components` folder.

   ```bash
   config/custom_components/isin_quotes/
   ```

2. Restart Home Assistant.

3. Go to **Settings → Devices & Services → Integrations → Add Integration** and select **Isin Quotes**.

## Configuration / Adding a new ISIN

Through the **Config Flow** (UI wizard), new sensors can be created:

1. Add the **Isin Quotes** integration.
2. Enter the **ISIN** of the desired security.
3. Select the desired **exchange** and **currency** (dropdown, with badges for default and realtime exchanges).
4. Specify the **update interval** (in seconds) if no market hours are defined for the chosen exchange.

After completion, the integration will create multiple sensors per ISIN/exchange:

* Price (with currency)
* Change in %
* Change absolute (with currency or % for bonds)
* Timestamp of the last price change

## Example visualization with ApexCharts Card

You can visualize the 24h history of a sensor using the [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (installable via HACS). Example YAML:

```yaml
type: custom:apexcharts-card
graph_span: 24h
update_interval: 60s
header:
  show: true
  title: 'IE00B5SSQT16 – last 24h'
series:
  - entity: sensor.ie00b5ssqt16_tgt_price
    name: Price
    type: line
    group_by:
      duration: 5m
      func: last
apex_config:
  yaxis:
    decimalsInFloat: 2
  tooltip:
    x:
      format: 'dd.MM HH:mm'
```

## Notes

* Market hours for selected exchanges are defined in `market_hours.py` and can be added or modified as needed.
* If no market hours are defined for an exchange, the user-provided polling interval is used continuously.
* When markets are closed, no new data is fetched from the API; the last known values are returned instead.

---

This project is community-driven and unaffiliated with ING—use responsibly and be mindful of API limits.
