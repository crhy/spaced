#!/usr/bin/env python3
"""Convert the showdown benchmark CSVs into the JSON used by the website's Benchmarks section.

Inputs are the two evidence CSVs (system.csv, phoronix.csv); the output is
website/assets/bench/showdown-<measured>.json, regenerated from the CSVs so the
site data can always be rebuilt from the evidence. Never edits the CSVs.

Usage: export-site.py [--system CSV] [--phoronix CSV] [--out FILE]
"""
import argparse
import csv
import json
import os
import sys

EVIDENCE = "/media/rhy/data/bench-evidence/showdown-20261122"
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
MEASURED = "2026-11-22"
NUMERIC = ("boot_s", "settle_s", "ram_mib", "processes", "idle_cpu_pct", "ctxt_per_s", "idle_start_s")


def number(text):
    """int when the value is integral, float otherwise; anything else is an error."""
    value = float(text)
    return int(value) if value.is_integer() else value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--system", default=os.path.join(EVIDENCE, "system.csv"))
    ap.add_argument("--phoronix", default=os.path.join(EVIDENCE, "phoronix.csv"))
    ap.add_argument("--out", default=os.path.join(REPO, "website", "assets", "bench", f"showdown-{MEASURED}.json"))
    args = ap.parse_args()

    with open(args.system, newline="") as f:
        distros = []
        for row in csv.DictReader(f):
            out = dict(row)
            for key in NUMERIC:
                out[key] = number(row[key])
            distros.append(out)

    with open(args.phoronix, newline="") as f:
        phoronix = []
        for row in csv.DictReader(f):
            out = dict(row)
            out["value"] = number(row["value"])
            phoronix.append(out)

    if len(distros) < 1 or len(phoronix) < 1:
        sys.exit("no rows read; refusing to write an empty benchmark JSON")

    data = {"measured": MEASURED, "distros": distros, "phoronix": phoronix}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"wrote {args.out} ({len(distros)} distros, {len(phoronix)} phoronix results)")


if __name__ == "__main__":
    main()
