from .classes import Recruit, Telegram, TelegramTemplate, TimeRange, Stats
import json
import os

def import_raw_template_data(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as tgdata:
        return json.load(tgdata)

def import_template_data(path: str) -> TelegramTemplate:
    tgdata = import_raw_template_data(path)

    template = TelegramTemplate()
    template.tgid = tgdata.get("tgid", 0)
    template.type = tgdata.get("type", "template")
    template.nation = tgdata.get("nation", "")
    template.category = tgdata.get("category", "Uncategorized")
    template.timeRange = TimeRange(
        tgdata.get("createdAt", 9999999999999),
        tgdata.get("generatedAt", 0)
    )
    template.stats = Stats(
        delivered=tgdata.get("delivered", 0),
        readCount=tgdata.get("readCount", 0),
        recruitCount=tgdata.get("recruitCount", 0)
    )
    template.recipients = tgdata.get("recipients", [])
    template.recruits = {}
    for recruit in tgdata.get("recruits", []):
        name = recruit.get("name", "")
        if name:
            template.recruits[name] = Recruit(
                cte=recruit.get("cte", False),
                recruitedAt=recruit.get("timestamp", recruit.get("recruitedAt", 0)),
                name=name
            )

    return template

def create_empty_telegram(category_name: str) -> Telegram:
    return Telegram(category_name)

def parse_template_folder(path: str) -> dict[str, Telegram]:
    telegrams: dict[str, Telegram] = {}

    if not os.path.exists(path):
        print(f"[Parse] Telegram template directory '{path}' does not exist.")
        return telegrams

    for entry in os.scandir(path):
        if entry.is_file() and entry.name.endswith(".json"):
            try:
                template = import_template_data(entry.path)
            except Exception as e:
                print(f"[Parse] Error reading {entry.name}: {e}. Skipping.")
                continue

            category = template.category or "Uncategorized"
            if category not in telegrams:
                telegrams[category] = create_empty_telegram(category)

            tg = telegrams[category]
            tg.stats.add(template.stats)
            tg.recipients.extend(template.recipients)
            tg.recruits.update(template.recruits)

            tg.timeRange.try_add_start(template.timeRange.start)
            tg.timeRange.try_add_end(template.timeRange.end)

            # Accumulate breakdown by method type (API vs Manual/Stamp)
            method_type = template.type or "template"
            if method_type not in tg.methods:
                tg.methods[method_type] = Stats.empty()
            tg.methods[method_type].add(template.stats)

            # Accumulate breakdown by sender nation
            sender = template.nation or "Unknown"
            if sender not in tg.nations:
                tg.nations[sender] = Stats.empty()
            tg.nations[sender].add(template.stats)

            tg.templates.append(template)

    return telegrams
