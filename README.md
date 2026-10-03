# Charging Statistics

Requires Python 3.9+ and PyYAML (`pip install -r requirements.txt`).

Place provider exports in `data/AudiCharging/`, `data/EWEGo/`, `data/Vattenfall/`, `data/Octopus/`, or `data/Wallbox/` as `.csv` files. Two example formats are already configured in `providers.yaml`: AudiCharging and Wallbox. The remaining providers are disabled until you add their actual mappings.

Run `python main.py` from the project root (or supply `--data`, `--output`, `--config`).

Outputs in `output/`:
- `charging_sessions.csv`: chronological, deduplicated sessions.
- `monthly_statistics.csv`: kWh, costs and session counts per provider and month, plus TOTAL.
- `duplicates.csv`: discarded duplicates with original source filename.
- `errors.csv`: unreadable files and conflicting IDs.

`providers.yaml` supports `delimiter`, `encoding`, `date_formats`, `columns` (required keys: `date` and `energy_kwh`; optional: `cost_eur`, `session_id`, `location`) and `price_per_kwh`. Comma decimals and euro signs are handled automatically. The Audi `pro kWh` column is informational; actual `Betrag` is authoritative. Wallbox costs are estimated using the configured electricity rate. Adjust the rate if it changes.

Duplicates are detected within each provider by session ID when present; otherwise by exact date/time, kWh and cost. Matching session IDs with conflicting values are reported in `errors.csv`. Entries without session IDs but different amounts/times are not automatically merged.
