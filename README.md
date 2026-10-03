# Charging Statistics
I was annoyed that most CPOs do not provide export of my charging sessions ad my Go-E wallbox does. I wrote a script that can parse any CSV 
export format and bring all the informations together. Most public CPOs must be entered in CSV by hand but as I'm rarely charging public, this does not matter much. 

Made with help of AI. 

Requires Python 3.9+ and PyYAML

Place provider exports in `data/AudiCharging/`, `data/EWEGo/`, `data/Vattenfall/`, `data/Octopus/`, or `data/Wallbox/` as `.csv` files. Two example formats are already configured in `providers.yaml`: AudiCharging and Wallbox. The remaining providers are disabled until you add their actual mappings.

Run `python main.py` from the project root (or supply `--data`, `--output`, `--config`).

Outputs in `output/`:
- `charging_sessions.csv`: chronological, deduplicated sessions.
- `monthly_statistics.csv`: kWh, costs and session counts per provider and month, plus TOTAL.
- `duplicates.csv`: discarded duplicates with original source filename.
- `errors.csv`: unreadable files and conflicting IDs.

`providers.yaml` supports `delimiter`, `encoding`, `date_formats`, `columns` (required keys: `date` and `energy_kwh`; optional: `cost_eur`, `session_id`, `location`) and `price_per_kwh`. Comma decimals and euro signs are handled automatically. The Audi `pro kWh` column is informational; actual `Betrag` is authoritative. Wallbox costs are estimated using the configured electricity rate. Adjust the rate if it changes.

Duplicates are detected within each provider by session ID when present; otherwise by exact date/time, kWh and cost. Matching session IDs with conflicting values are reported in `errors.csv`. Entries without session IDs but different amounts/times are not automatically merged.

# Install
PyEnv or another virtual environment for python is required. Than, install dependencies. 
~~~
pip install -r requirements.txt
~~~

# Example output
~~~

Statistik nach Ladeanbieter
-------------------------------------------------------------------------------------
Anbieter               Energie (kWh)    Kosten (EUR)       EUR/kWh    Ladungen
-------------------------------------------------------------------------------------
AralPulse                       22.4           12.29        0.5487           2
AudiCharging                   555.0          238.19        0.4292          20
CityWatt                        76.3           26.74        0.3505           3
Octopus                       108.66           57.78        0.5318           5
Repower                         61.7           36.14        0.5857           2
Vattenfall                    40.248           16.64        0.4134           1
Wallbox                     3864.939          869.65        0.2250         112
-------------------------------------------------------------------------------------
TOTAL                       4729.247         1257.43        0.2659         145
-------------------------------------------------------------------------------------
~~~