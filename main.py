#!/usr/bin/env python3
"""CSV charging statistics. Configure column mappings in providers.yaml."""
import argparse
import csv
import yaml
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

@dataclass
class Session:
    date: str
    provider: str
    energy_kwh: str
    cost_eur: str
    location: str
    session_id: str
    source_file: str

def number(value):
    s = re.sub(r'[^\d,.-]', '', str(value or '').strip())
    if not s:
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError(f'Invalid number: {value!r}')

def date_iso(value, formats):
    value = str(value).strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).isoformat(timespec='seconds')
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat(timespec='seconds')
    except ValueError as exc:
        raise ValueError(f'Unknown date: {value!r}') from exc

class CSVProvider:
    name = ''
    def __init__(self, config):
        self.config = config

    def parse(self, path):
        cfg = self.config
        with path.open('r', encoding=cfg.get('encoding', 'utf-8-sig'), newline='') as file:
            reader = csv.DictReader(file, delimiter=cfg.get('delimiter', ';'))
            fields = cfg['columns']
            required = [fields[k] for k in ('date', 'energy_kwh')]
            missing = [x for x in required if x not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f'Missing columns: {missing}')
            for line, row in enumerate(reader, 2):
                def get(key):
                    return (row.get(fields.get(key, ''), '') or '').strip()
                if not any(row.values()):
                    continue
                try:
                    provider_name = get('name') or self.name
                    energy = number(get('energy_kwh'))
                    if energy is None or energy < 0:
                        raise ValueError('Energy missing or negative')
                    cost = number(get('cost_eur'))
                    if cost is None and cfg.get('price_per_kwh') is not None:
                        cost = energy * Decimal(str(cfg['price_per_kwh']))
                    yield Session(date_iso(get('date'), cfg['date_formats']), provider_name,
                                  str(energy), '' if cost is None else str(cost.quantize(Decimal('.01'))),
                                  get('location'), get('session_id'), str(path))
                except ValueError as exc:
                    raise ValueError(f'{path}:{line}: {exc}') from exc

class AudiCharging(CSVProvider): name = 'AudiCharging'
class EWEGo(CSVProvider): name = 'EWEGo'
class Vattenfall(CSVProvider): name = 'Vattenfall'
class Octopus(CSVProvider): name = 'Octopus'
class Wallbox(CSVProvider): name = 'Wallbox'

PROVIDERS = {c.name: c for c in (AudiCharging, EWEGo, Vattenfall, Octopus, Wallbox)}
FIELDS = list(Session.__dataclass_fields__)

def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

def run(data, output, configs):
    output.mkdir(parents=True, exist_ok=True)
    unique = {}
    duplicates = []
    errors = []
    for name, cfg in configs.items():
        cls = PROVIDERS.get(name)
        if cls is None:
            cls = type(f'{name}Provider', (CSVProvider,), {'name': name})
        if not cfg.get('columns'):
            continue
        parser = cls(cfg)
        for path in sorted((data / name).glob('*.csv')):
            try:
                for item in parser.parse(path):
                    # Exact timestamps are intentionally required: near-matches need manual review.
                    fallback = (item.provider, item.date, Decimal(item.energy_kwh), item.cost_eur)
                    key = (item.provider, item.session_id) if item.session_id else fallback
                    # Also catch same no-ID entry imported twice; ID and no-ID records
                    # require manual review rather than risking a false positive.
                    if key in unique:
                        previous = unique[key]
                        if item.session_id and (previous.date != item.date or previous.energy_kwh != item.energy_kwh or previous.cost_eur != item.cost_eur):
                            errors.append({'file': str(path), 'error': f'Conflicting session ID {item.session_id}: {previous.source_file}'})
                            continue
                        duplicates.append(asdict(item) | {'duplicate_of': unique[key].source_file})
                    else:
                        unique[key] = item
            except (ValueError, UnicodeError, csv.Error) as exc:
                errors.append({'file': str(path), 'error': str(exc)})
    sessions = sorted(unique.values(), key=lambda x: (x.date, x.provider))
    write_csv(output / 'charging_sessions.csv', FIELDS, map(asdict, sessions))
    write_csv(output / 'duplicates.csv', FIELDS + ['duplicate_of'], duplicates)
    summary = defaultdict(lambda: {'energy': Decimal(0), 'cost': Decimal(0), 'count': 0, 'missing_cost': 0})
    for s in sessions:
        for provider in (s.provider, 'TOTAL'):
            item = summary[(s.date[:7], provider)]
            item['energy'] += Decimal(s.energy_kwh)
            item['count'] += 1
            if s.cost_eur:
                item['cost'] += Decimal(s.cost_eur)
            else:
                item['missing_cost'] += 1
    rows = []
    for (month, provider), item in sorted(summary.items()):
        rows.append({'month': month, 'provider': provider, 'energy_kwh': str(item['energy']),
                     'cost_eur': str(item['cost'].quantize(Decimal('.01'))),
                     'sessions': item['count'], 'sessions_without_cost': item['missing_cost']})
    write_csv(output / 'monthly_statistics.csv',
              ['month', 'provider', 'energy_kwh', 'cost_eur', 'sessions', 'sessions_without_cost'], rows)
    # Provider-wide totals across all months. Average is energy-weighted, not
    # the arithmetic mean of individual session prices. Exclude unknown-cost
    # sessions from the price denominator so the average is not understated.
    provider_summary = defaultdict(lambda: {'energy': Decimal(0), 'priced_energy': Decimal(0),
                                            'cost': Decimal(0), 'count': 0, 'missing_cost': 0})
    for session in sessions:
        for provider in (session.provider, 'TOTAL'):
            item = provider_summary[provider]
            energy = Decimal(session.energy_kwh)
            item['energy'] += energy
            item['count'] += 1
            if session.cost_eur != '':
                item['cost'] += Decimal(session.cost_eur)
                item['priced_energy'] += energy
            else:
                item['missing_cost'] += 1
    provider_rows = []
    for provider, item in sorted(
        provider_summary.items(),
        key=lambda entry: (entry[0] == "TOTAL", entry[0].lower())
    ):
        avg = (item['cost'] / item['priced_energy']).quantize(Decimal('0.0001')) if item['priced_energy'] else None
        provider_rows.append({'provider': provider, 'energy_kwh': str(item['energy']),
                              'cost_eur': str(item['cost'].quantize(Decimal('0.01'))),
                              'average_eur_per_kwh': '' if avg is None else str(avg),
                              'energy_with_cost_kwh': str(item['priced_energy']),
                              'sessions': item['count'], 'sessions_without_cost': item['missing_cost']})
    write_csv(output / 'provider_statistics.csv',
              ['provider', 'energy_kwh', 'cost_eur', 'average_eur_per_kwh',
               'energy_with_cost_kwh', 'sessions', 'sessions_without_cost'], provider_rows)
    write_csv(output / 'errors.csv', ['file', 'error'], errors)
    print("\nStatistik nach Ladeanbieter")
    print("-" * 85)

    print(
        f"{'Anbieter':<20}"
        f"{'Energie (kWh)':>16}"
        f"{'Kosten (EUR)':>16}"
        f"{'EUR/kWh':>14}"
        f"{'Ladungen':>12}"
    )

    print("-" * 85)

    for row in provider_rows:
        if row["provider"] == "TOTAL":
            print("-" * 85)

        print(
            f"{row['provider']:<20}"
            f"{row['energy_kwh']:>16}"
            f"{row['cost_eur']:>16}"
            f"{row['average_eur_per_kwh']:>14}"
            f"{row['sessions']:>12}"
        )

    print("-" * 85)
    print(f'{len(sessions)} sessions, {len(duplicates)} duplicates, {len(errors)} files with errors')
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, default=Path('data'))
    ap.add_argument('--output', type=Path, default=Path('output'))
    ap.add_argument('--config', type=Path, default=Path('providers.yaml'))
    args = ap.parse_args()
    run(args.data, args.output, yaml.safe_load(args.config.read_text(encoding='utf-8')) or {})

if __name__ == '__main__':
    main()
