import sqlite3
import time
from .classes import Telegram, Analytics, Nation, Recruit
from .filters import normalizeNationName

DAY_SECONDS = 86400

def format_database_data(data: tuple) -> Nation:
    return Nation(
        canon_name=data[0],
        api_name=data[1],
        region=data[2],
        wa=bool(data[3]),
        lastlogin=data[4]
    )

def query_nation(cursor: sqlite3.Cursor, name: str) -> Nation | None:
    api_name = normalizeNationName(name)
    cursor.execute("SELECT canon_name, api_name, region, wa, lastlogin FROM nations WHERE api_name = ?", (api_name,))
    row = cursor.fetchone()
    if row is None:
        return None
    return format_database_data(row)

def canonName(cursor: sqlite3.Cursor, nation: str) -> str:
    n = query_nation(cursor, nation)
    return n.canon_name if n else nation

def time_since_last_active(nation: Nation) -> float:
    return max(0.0, time.time() - nation.lastlogin)

def generate_analytics(cur: sqlite3.Cursor, telegram: Telegram, region: str, inactivity_threshold: int = 7) -> Analytics:
    analytics = Analytics.empty()
    analytics.stats = telegram.stats
    analytics.timeRange = telegram.timeRange
    target_region = normalizeNationName(region)
    max_inactivity_secs = DAY_SECONDS * inactivity_threshold

    print(f"[Analytics] Analyzing {len(telegram.recruits)} recruits for category '{telegram.category}'...")
    for name, recruit_data in telegram.recruits.items():
        if recruit_data.cte:
            continue

        nation_data = query_nation(cur, name)
        if nation_data:
            if nation_data.region == target_region:
                if time_since_last_active(nation_data) <= max_inactivity_secs:
                    analytics.faithful.append(recruit_data)
                    if nation_data.wa:
                        analytics.wa_faithful.append(recruit_data)
            else:
                dest = nation_data.region or "Unknown"
                analytics.traitor_destinations[dest] = analytics.traitor_destinations.get(dest, 0) + 1

    print(f"[Analytics] Analyzing {len(telegram.recipients)} non-recruited recipients for category '{telegram.category}'...")
    recruited_names = set(telegram.recruits.keys())

    for recipient in telegram.recipients:
        if recipient in recruited_names:
            continue

        nation_data = query_nation(cur, recipient)
        if nation_data and nation_data.region and nation_data.region != target_region:
            dest = nation_data.region
            analytics.uninterested_destinations[dest] = analytics.uninterested_destinations.get(dest, 0) + 1

    return analytics
