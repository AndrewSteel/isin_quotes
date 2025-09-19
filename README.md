# Isin Quotes – Home Assistant Custom Component

## Overview

This custom component allows you to integrate security price data into Home Assistant by specifying the ISIN (International Securities Identification Number). Multiple exchanges and currencies are supported. In addition to the current price, the integration provides percentage and absolute changes as well as the timestamp of the last price update. An internal market-hours model dynamically adjusts polling frequency according to trading hours.

---

This project is community-driven and unaffiliated with ING—use responsibly and be mindful of API limits.

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

## Market Hours

* Market hours for selected exchanges are defined in `market_hours.py` and can be added or modified as needed.
* If no market hours are defined for an exchange, the user-provided polling interval is used continuously.
* When markets are closed, no new data is fetched from the API; the last known values are returned instead.

## Services

The integration currently provides two services:

### `isin_quotes.render_logo`

This service fetches and caches the logo of a configured ISIN.

**What it does:**

* Retrieves the logo from the ING API.
* If the response is **Lottie JSON**, it renders **frame 0 to SVG**.
* If the response is **raw SVG**, it stores it directly.
* The file is written to: `/config/www/isin_quotes/`.
* The cached logo is available to Lovelace under: `/local/isin_quotes/<isin>.svg`.

**Variables:**

* `isin` (required): The ISIN of the security whose logo should be fetched.

---

### `isin_quotes.fetch_history`

This service retrieves historical chart data for a security.

**What it does:**

* Fetches historical price data from the ING API.
* Supports different **time ranges** (Intraday, OneWeek, OneMonth, OneYear, FiveYears, Maximum).
* Can be requested in **OHLC mode** (open, high, low, close) or simple price/time mode.
* Updates the internal helper sensor `sensor.isin_quotes_history` with the fetched data.

**Variables:**

* `isin` (required): ISIN of the security.
* `time_range` (optional, default: OneWeek): One of Intraday, OneWeek, OneMonth, OneYear, FiveYears, Maximum.
* `exchange_id` (required): ID of the exchange to fetch data from.
* `currency_id` (required): ID of the currency to use.
* `ohlc` (optional, default: false): Boolean, whether to return OHLC data.

## Todo

Functions for managing portfolios.

## Lovelace Examples

## Example: Visualization with ApexCharts Card

You can visualize the 24h history of a sensor using the [ApexCharts Card](https://github.com/RomRider/apexcharts-card) (installable via HACS).

![apexcharts-card][https://github.com/AndrewSteel/isin_quotes/images/apexcharts-card]

Example YAML:

```yaml
type: custom:apexcharts-card
graph_span: 24h
update_interval: 60s
header:
  show: true
  title: 'IE00B5SSQT16 – last 24h'
series:
  - entity: sensor.ie00b5ssqt16_tgt_price   # <- adjust to your entity id
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

## Example: visualization with Plotly Graph Card

The [Plotly Graph Card](https://github.com/dbuezas/lovelace-plotly-graph-card) can also be installed via HACS and used to render interactive charts.

![Plotly Graph Card][https://github.com/AndrewSteel/isin_quotes/images/plotly-graph.png]

Example YAML for a 24h price line:

```yaml
type: custom:plotly-graph
title: 'IE00B5SSQT16 – last 24h (Plotly)'
hours_to_show: 24
refresh_interval: 60
entities:
  - entity: sensor.ie00b5ssqt16_tgt_price   # <- adjust to your entity id
    name: Price
layout:
  xaxis:
    type: date
  yaxis:
    tickformat: .2f
    title: Price
traces:
  - entity: sensor.ie00b5ssqt16_tgt_price
    name: Price
    mode: lines
```

### Example: Current Data and Historical Insights

For a richer dashboard experience, you can combine **current price data** with the ability to dive deeper into **historical charts**.

* The **Home view** shows a compact overview of all configured ISINs and their current prices.

![config-template-card][https://github.com/AndrewSteel/isin_quotes/images/config-template-card.png]

* The **Insight view** focuses on a selected ISIN and allows you to analyze its historical performance using the `isin_quotes.fetch_history` service:
  
price only ...

![historical-insight-price][https://github.com/AndrewSteel/isin_quotes/images/historical-insight-price.png]

... or OHLC - open, high, low, close.

![historical-insight-ohlc][https://github.com/AndrewSteel/isin_quotes/images/historical-insight-ohlc.png]

* Navigation between views can be automated using the included scripts and helpers.
* The **helpers** (`input_number.view_currency_id`, `input_number.view_exchange_id`, `input_text.view_isin`, `input_text.view_name`, `input_boolean.view_ohlc`, `input_select.view_time_range`) manage the context for fetching and displaying the data.

Insert this into the (`configuration.yaml`) or create appropriate helpers:

```yaml
input_number:
  view_currency_id:
    name: Currency (ID)
    min: 0
    max: 9999
    step: 1
    mode: box
  view_exchange_id:
    name: exchange (ID)
    min: 0
    max: 9999
    step: 1
    mode: box

input_text:
  view_isin:
    name: ISIN
    pattern: '^[A-Z0-9]{12}$'
  view_name:
    name: Name
    max: 100

input_boolean:
  view_ohlc:
    name: Show Open, High, Low, Close

input_select:
  view_time_range:
    name: Choose time range
    options:
      - Intraday
      - OneWeek
      - OneMonth
      - OneYear
      - FiveYears
      - Maximum
    initial: OneMonth
```

* The **scripts** (`script.isin_quotes_fetch_current_view`,

```yaml
alias: isin_quotes_fetch_current_view
mode: restart
sequence:
  - variables:
      name: "{{ states('input_text.view_name') }}"
      isin: "{{ states('input_text.view_isin') | lower }}"
      ex: "{{ states('input_number.view_exchange_id') | int(2779) }}"
      cur: "{{ states('input_number.view_currency_id') | int(814) }}"
      tr: "{{ states('input_select.view_time_range') | default('OneWeek') }}"
      ohlc: "{{ is_state('input_boolean.view_ohlc','on') }}"
  - data:
      isin: "{{ isin }}"
      time_range: "{{ tr }}"
      exchange_id: "{{ ex }}"
      currency_id: "{{ cur }}"
      ohlc: "{{ ohlc }}"
    action: isin_quotes.fetch_history
description: ""
```

* `script.isin_quotes_set_view_and_go`)

```yaml
alias: isin_quotes_set_view_and_go
mode: single
fields:
  entity_id:
    description: source with attributes (ISIN sensor)
  path:
    description: view path
  time_range:
    description: (optional) Intraday/OneWeek/OneMonth/OneYear/FiveYears/Maximum
  ohlc:
    description: (optional) true/false – OHLC mode
sequence:
  - variables:
      a: "{{ state_attr(entity_id, 'friendly_name') | default('', true) }}"
      isin: "{{ state_attr(entity_id, 'isin') | default('', true) | lower }}"
      ex: "{{ (state_attr(entity_id, 'selectedExchange') or {}).get('id', 2779) }}"
      cur: "{{ (state_attr(entity_id, 'selectedCurrency') or {}).get('id', 814) }}"
      name: "{{ state_attr(entity_id, 'name') | default('', true) }}"
      tr: OneWeek
      ohlc: false
  - target:
      entity_id: input_text.view_name
    data:
      value: "{{ name }}"
    action: input_text.set_value
  - target:
      entity_id: input_text.view_isin
    data:
      value: "{{ isin }}"
    action: input_text.set_value
  - target:
      entity_id: input_number.view_exchange_id
    data:
      value: "{{ ex }}"
    action: input_number.set_value
  - target:
      entity_id: input_number.view_currency_id
    data:
      value: "{{ cur }}"
    action: input_number.set_value
  - target:
      entity_id: input_select.view_time_range
    data:
      option: "{{ tr }}"
    action: input_select.select_option
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ ohlc }}"
        sequence:
          - target:
              entity_id: input_boolean.view_ohlc
            action: input_boolean.turn_on
    default:
      - target:
          entity_id: input_boolean.view_ohlc
        action: input_boolean.turn_off
  - data:
      isin: "{{ isin }}"
      time_range: "{{ tr }}"
      exchange_id: "{{ ex }}"
      currency_id: "{{ cur }}"
      ohlc: "{{ ohlc }}"
    action: isin_quotes.fetch_history
  - data:
      path: "{{ path }}"
    action: browser_mod.navigate
description: ""
```

* handle fetching historical data and navigating to the correct view.
* The **automations** (`isin_quotes_autofetch_source_paramas`)

```yaml
alias: isin_quotes_autofetch_source_params
description: ""
triggers:
  - entity_id:
      - input_text.view_isin
      - input_number.view_exchange_id
      - input_number.view_currency_id
    trigger: state
actions:
  - action: script.isin_quotes_fetch_current_view
mode: restart
```

(`isin_quotes_autofetch_time_range`)

```yaml
alias: isin_quotes_autofetch_time_range
description: ""
triggers:
  - entity_id: input_select.view_time_range
    trigger: state
actions:
  - action: script.isin_quotes_fetch_current_view
mode: restart
```

and (`ison_quotes_autofetch_ohlc`)

```yaml
alias: isin_quotes_autofetch_ohlc
description: ""
triggers:
  - entity_id: input_boolean.view_ohlc
    trigger: state
actions:
  - action: script.isin_quotes_fetch_current_view
mode: restart
```

ensure that whenever the user changes parameters (ISIN, time range, OHLC mode), the historical data is automatically refreshed.

This [setup][https://github.com/AndrewSteel/isin_quotes/examples/finance-view.yaml] enables seamless switching between securities and time ranges, ensuring that both high-level overviews and detailed insights are always up to date.
