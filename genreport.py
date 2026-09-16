#!/usr/bin/env python3
"""
Searendipity Recruitment Campaign Report Generator.
Processes exported NationStates telegram statistics, cross-references with
daily nation dumps, and generates interactive HTML dashboards and JSON data.
"""

import jinja2
import os
import json
import argparse
import sys

from src.report.datadump import generate_database
from src.report.parse import parse_template_folder
from src.report.filters import (
    renderDate, items, sortByHighest, sortStatsByHighest,
    sortTop, sortStatsTop, methodName, displayNumberWithCommas,
    normalizeNationName
)
from src.report.analytics import generate_analytics, canonName
from src.report.classes import Analytics, accumulate, Stats, Telegram

class SearendipityEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            if isinstance(o, list):
                return o
            if hasattr(o, "__dict__"):
                return o.__dict__
            return str(o)

def main():
    parser = argparse.ArgumentParser(
        prog="genreport",
        description="Searendipity recruitment report generator"
    )
    parser.add_argument("-n", "--nation-name", default="", help="Your main nation name (for User-Agent compliance)")
    parser.add_argument("-r", "--regenerate", action='store_true', help="Re-download and re-parse daily nation data dump")
    parser.add_argument("-a", "--activity-threshold", default=7, type=int, help="Days of inactivity threshold for faithful recruits (default: 7)")
    parser.add_argument("--region", required=True, help="Your target region to calculate retention for")
    parser.add_argument("-o", "--output", default="reports", help="Folder to save generated HTML and JSON report (default: 'reports')")
    parser.add_argument("-i", "--input", help="If provided, renders existing report.json directly to HTML without re-processing dumps")
    parser.add_argument("-t", "--tg-source", default="telegrams", help="Folder containing exported telegram JSON files (default: 'telegrams')")
    args = parser.parse_args()

    nation_name = args.nation_name.strip()
    if not nation_name:
        from dotenv import dotenv_values
        nation_name = dotenv_values(".env").get("DEFAULT_NATION", "")

    if not nation_name and not args.input:
        nation_name = input("Please enter your main nation name: ").strip()

    if not nation_name and not args.input:
        print("Error: Nation name is required to establish User-Agent per NationStates rules.")
        sys.exit(1)

    folder = args.output
    os.makedirs(folder, exist_ok=True)

    # Initialize Jinja2 templating environment
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir), autoescape=True)
    env.filters['renderdate'] = renderDate
    env.filters['items'] = items
    env.filters['sorttop'] = sortTop
    env.filters['sortstatstop'] = sortStatsTop
    env.filters['sortbyhighest'] = sortByHighest
    env.filters['sortstatsbyhighest'] = sortStatsByHighest
    env.filters['methodname'] = methodName
    env.filters['displaynum'] = displayNumberWithCommas

    telegrams: dict[str, Telegram] = {}
    overall_analytics = Analytics.empty()
    overall_methods: dict[str, Stats] = {}
    overall_nations: dict[str, Stats] = {}

    con = None
    cursor = None

    if args.input:
        print(f"[GenReport] Loading existing report from {args.input}...")
        with open(args.input, "r", encoding="utf-8") as f:
            input_json = json.load(f)

        overall_analytics = Analytics.fromJSON(input_json.get("analytics", {}))
        overall_methods = {k: Stats.fromJSON(v) for k, v in input_json.get("methods", {}).items()}
        overall_nations = {k: Stats.fromJSON(v) for k, v in input_json.get("nations", {}).items()}
        telegrams = {k: Telegram.fromJSON(v) for k, v in input_json.get("telegrams", {}).items()}

        env.filters['canonname'] = lambda nat: nat.replace("_", " ").title()

    else:
        print(f"[GenReport] Step 1: Initializing nation database...")
        con = generate_database(nation_name, regenerate=args.regenerate)
        cursor = con.cursor()
        env.filters['canonname'] = lambda nat: canonName(cursor, nat)

        print(f"[GenReport] Step 2: Parsing telegram template data from '{args.tg_source}'...")
        telegrams = parse_template_folder(args.tg_source)

        if not telegrams:
            print(f"Warning: No valid telegram data found in '{args.tg_source}'. Place JSON exports from the userscript there.")

        print(f"[GenReport] Step 3: Computing analytics across {len(telegrams)} category(ies)...")
        for category, telegram in telegrams.items():
            print(f"[GenReport]  -> Analyzing category: {category}")
            telegram.analytics = generate_analytics(cursor, telegram, args.region, args.activity_threshold)
            overall_analytics.add(telegram.analytics)

            overall_methods = accumulate(
                overall_methods,
                telegram.methods,
                Stats.empty(),
                lambda base, other: base.join(other)
            )
            overall_nations = accumulate(
                overall_nations,
                telegram.nations,
                Stats.empty(),
                lambda base, other: base.join(other)
            )

    print(f"[GenReport] Step 4: Generating JSON and HTML reports in '{folder}'...")

    # Save JSON report
    report_json_path = os.path.join(folder, "report.json")
    json_output = {
        "region": args.region,
        "analytics": overall_analytics,
        "methods": overall_methods,
        "nations": overall_nations,
        "telegrams": telegrams
    }
    with open(report_json_path, "w", encoding="utf-8") as out:
        json.dump(json_output, fp=out, indent=2, cls=SearendipityEncoder)
    print(f"[GenReport]  Saved JSON data: {report_json_path}")

    # Render category drill-down pages
    tgtemplate = env.get_template("telegram.html.jinja")
    for category, telegram in telegrams.items():
        rendered = tgtemplate.render(telegram=telegram, region=args.region)
        safe_cat = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in category)
        cat_file = os.path.join(folder, f"{safe_cat}.html")
        with open(cat_file, "w", encoding="utf-8") as out:
            out.write(rendered)

    # Render main index dashboard
    index_template = env.get_template("index.html.jinja")
    rendered_index = index_template.render(
        analytics=overall_analytics,
        methods=overall_methods,
        nations=overall_nations,
        telegrams=telegrams,
        region=args.region
    )
    index_file = os.path.join(folder, "index.html")
    with open(index_file, "w", encoding="utf-8") as out:
        out.write(rendered_index)

    print(f"[GenReport]  Saved Main Dashboard: {index_file}")
    print(f"==================================================")
    print(f"  Report generated successfully!")
    print(f"  Open in your browser: file://{os.path.abspath(index_file)}")
    print(f"==================================================")

    if con:
        con.close()

if __name__ == "__main__":
    main()
