# Hub Visit Dashboard

Live: https://shiva0095.github.io/Hub_Visit_Dash/

Driver walk-in / allocation funnel dashboard for Hyderabad operations (Overall, Hyderabad, Damaigudda, Nagole Dost hubs).

## How it loads data
`index.html` tries a live Google Sheets Apps Script connection first (Live Data button, saved in `localStorage`). If none is connected, or the live fetch fails, it falls back to the bundled `data_v2.json` in this repo.

## Refreshing `data_v2.json`
Source data is a CSV export (employee_id, category, walkin_week, allocation_week, final_location, channel, etc. -- one row per lead/walk-in/funnel event, filtered to `final_city == "Hyderabad"`).

```
python3 scripts/build_data_v2.py path/to/export.csv data_v2.json
```

Key logic notes (see comments in the script for full detail):
- **Location** is taken from `final_location`, not `walkin_location` -- the latter is blank on ~10% of real walk-ins, which previously caused per-hub totals to undercount vs. Overall.
- **Fresh vs. Spill**: an employee is "fresh" in a period if their first-ever walk-in (any category) falls in that period, otherwise "spill" (repeat visit).
- **Funnel fields** (doc/SD/training/contract/allocation) are counted as unique employees whose respective timestamp falls inside the period, using the full funnel row pool (`by_month`/`by_week`/`by_day`), not just that period's walk-ins.
- **Lead Type / Channel Source / Source filters** need the full breakdown keys (`by_month_leadtype`, `by_week_leadtype`, `by_month_chcat`, `by_week_chcat`, `by_month_ch`, `by_week_ch`, `channel_by_month`, `ch_to_chcat`) -- make sure any future rebuild keeps emitting all of them, not just the `by_month`/`by_week`/`by_day` totals, or those filters will silently show no data.

After regenerating, commit and push `data_v2.json` (and GitHub Pages will pick it up automatically).
