#!/usr/bin/env python3
"""Comparator for the cross-OS benchmark rows scripts/vm/bench/run-bench.sh writes.

Reads the TSV rows under build/bench/, prints one table per metric with the best
value marked and `not measured` in every empty cell, writes an SVG bar chart,
and refuses to rank a metric that has data for fewer than two operating systems.

Stdlib only: no PIL, no numpy, no matplotlib. Nothing here claims a winner for
a metric only one OS was measured on, and an OS that was never measured appears
as `not measured` in every column rather than as a zero.

Usage: compare.py [--svg PATH] [--repo ROOT] [TSV ...]
With no TSV arguments every build/bench/*.tsv of the repository is read.
"""
import argparse
import csv
import html
import statistics
import sys
from pathlib import Path

# The metric set and order guest-probe.sh emits, so a column no distro provides
# stays visible instead of being silently dropped.
METRICS = (
    'uptime_at_desktop_ready_s',
    'mem_used_mib',
    'process_count',
    'top10_rss_kib',
    'context_switches_per_s',
    'interrupts_per_s',
    'idle_cpu_percent',
    'diskstats_reads_completed',
    'diskstats_sectors_read',
    'diskstats_mib_read',
    'pkg_manager',
    'package_count',
    'pkg_manager_query_ms',
)

# pkg_manager names a program, so there is nothing to rank; every numeric metric
# here rewards a smaller number: less time, less memory, fewer processes, fewer
# wake-ups, fewer disk reads.
TEXT_METRICS = ('pkg_manager',)

NOT_MEASURED = 'not measured'
REFUSED = 'REFUSED'
# Chart colours come from the Spaced Linux Dark metatheme (docs/THEME-COLORS.md
# and overlays/usr/share/spaced-themes/themes.json); the chart is monochrome like
# the theme, and the best bar is the lighter one.
BACKGROUND = '#1a1a1a'
TRACK = '#2f2f2f'
BEST_BAR = '#f0f0f0'
OTHER_BAR = '#7a7a7a'
TEXT = '#f0f0f0'


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('tsv', nargs='*', type=Path)
    parser.add_argument('--svg', type=Path)
    parser.add_argument('--repo', type=Path)
    return parser.parse_args(argv)


def repo_root():
    return Path(__file__).resolve().parents[1]


def collect(argv):
    args = parse_args(argv)
    repo = args.repo or repo_root()
    paths = args.tsv or sorted((repo / 'build/bench').glob('*.tsv'))
    rows = []
    for path in paths:
        if not path.is_file():
            print(f'SKIP: {path} no such TSV file')
            continue
        with path.open(encoding='utf-8', newline='') as handle:
            for row in csv.DictReader(handle, delimiter='\t'):
                if row.get('os_label'):
                    rows.append(row)
    return rows, args.svg or repo / 'build/bench/compare.svg'


def gather(rows):
    """os label -> metric -> measured values, in the order the rows appear.

    A value that is not a number for a numeric metric is treated as not measured
    rather than compared; repeated runs of one OS keep every value so the table
    can show a median the way the release measurements do.
    """
    data = {}
    for row in rows:
        values = data.setdefault(row['os_label'], {})
        for metric in METRICS:
            raw = (row.get(metric) or '').strip()
            if not raw:
                continue
            if metric in TEXT_METRICS:
                values[metric] = raw
                continue
            try:
                number = float(raw)
            except ValueError:
                continue
            values.setdefault(metric, []).append(number)
    return data


def median(values):
    if len(values) > 1:
        return statistics.median(values)
    return values[0]


def format_value(value):
    if float(value).is_integer():
        return str(int(value))
    return f'{value:.2f}'


def medians_for(data, oses, metric):
    if metric in TEXT_METRICS:
        return {}
    medians = {}
    for os_label in oses:
        values = data[os_label].get(metric)
        if values:
            medians[os_label] = median(values)
    return medians


def write_svg(path, data, oses, ranked_metrics, refused_metrics):
    blocks = []
    y = 56
    for metric in ranked_metrics:
        medians = medians_for(data, oses, metric)
        best = min(medians, key=lambda name: medians[name])
        maximum = max(medians.values()) or 1.0
        blocks.append(f'  <text x="24" y="{y}" fill="{TEXT}" font-size="15"'
                      f' font-family="monospace">{html.escape(metric)} (lower is better)</text>')
        y += 20
        for os_label in oses:
            if os_label not in medians:
                continue
            value = medians[os_label]
            width = 480.0 * value / maximum
            fill = BEST_BAR if os_label == best else OTHER_BAR
            blocks.append(f'  <rect x="180" y="{y}" width="480" height="16" fill="{TRACK}"/>')
            blocks.append(f'  <rect x="180" y="{y}" width="{width:.1f}" height="16" fill="{fill}"/>')
            blocks.append(f'  <text x="24" y="{y + 13}" fill="{TEXT}" font-size="13"'
                          f' font-family="monospace">{html.escape(os_label)}</text>')
            blocks.append(f'  <text x="668" y="{y + 13}" fill="{TEXT}" font-size="13"'
                          f' font-family="monospace">{html.escape(format_value(value))}'
                          f'{"  best" if os_label == best else ""}</text>')
            y += 22
        y += 14
    if refused_metrics:
        blocks.append(f'  <text x="24" y="{y}" fill="{TEXT}" font-size="13"'
                      f' font-family="monospace">not ranked, fewer than two OSes measured:</text>')
        y += 18
        for index in range(0, len(refused_metrics), 3):
            line = ', '.join(refused_metrics[index:index + 3])
            blocks.append(f'  <text x="24" y="{y}" fill="{TEXT}" font-size="13"'
                          f' font-family="monospace">{html.escape(line)}</text>')
            y += 18
    height = y + 24
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="760" height="{height}"'
        f' viewBox="0 0 760 {height}">',
        '  <title>Cross-OS benchmark comparison</title>',
        f'  <rect width="760" height="{height}" fill="{BACKGROUND}"/>',
        f'  <text x="24" y="34" fill="{TEXT}" font-size="17"'
        f' font-family="monospace">Cross-OS benchmark comparison</text>',
    ]
    svg.extend(blocks)
    svg.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(svg) + '\n', encoding='utf-8')


def main(argv=None):
    rows, svg_path = collect(sys.argv[1:] if argv is None else argv)
    if not rows:
        print(f'{REFUSED}: no benchmark rows found; run scripts/vm/bench/run-bench.sh first')
        print('RESULT: oses=0 ranked=0 refused=0 svg=none')
        return 1

    data = gather(rows)
    oses = list(data)
    print(f'OSes compared: {", ".join(oses)}')

    ranked = []
    refused = []
    for metric in METRICS:
        medians = medians_for(data, oses, metric)
        print(f'metric: {metric}')
        if metric in TEXT_METRICS:
            print('note: text metric, nothing to rank')
        elif len(medians) < 2:
            print(f'{REFUSED}: {metric} has data for {len(medians)} OS'
                  f'{"es" if len(medians) != 1 else ""}; ranking needs at least two')
            refused.append(metric)
        else:
            ranked.append(metric)
        print('| OS | value | note |')
        print('|---|---|---|')
        if metric in TEXT_METRICS:
            for os_label in oses:
                value = data[os_label].get(metric)
                if value:
                    print(f'| {os_label} | {value} |  |')
                else:
                    print(f'| {os_label} | {NOT_MEASURED} |  |')
            continue
        best = min(medians, key=lambda name: medians[name]) if len(medians) >= 2 else None
        for os_label in oses:
            if os_label in medians:
                note = 'best' if os_label == best else ''
                print(f'| {os_label} | {format_value(medians[os_label])} | {note} |')
            else:
                print(f'| {os_label} | {NOT_MEASURED} |  |')

    write_svg(svg_path, data, oses, ranked, refused)
    print(f'RESULT: oses={len(oses)} ranked={len(ranked)} refused={len(refused)} svg={svg_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
