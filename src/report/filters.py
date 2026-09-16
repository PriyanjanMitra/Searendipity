import datetime

def renderRate(total: int, count: int) -> str:
    if total <= 0:
        return "0.00%"
    rate = (count / total) * 100.0
    return f"{round(rate, 2):.2f}%"

def renderDate(timestamp: int) -> str:
    if not timestamp or timestamp <= 0 or timestamp >= 999999999999:
        return "N/A"
    try:
        local_date = datetime.date.fromtimestamp(timestamp)
        return local_date.strftime("%B %d, %Y")
    except (ValueError, OSError):
        return "N/A"

def items(view: dict):
    if not isinstance(view, dict):
        return []
    return view.items()

def normalizeNationName(name: str) -> str:
    if not name:
        return ""
    return name.lower().replace(" ", "_").strip()

def methodName(method: str) -> str:
    methods = {
        "api": "API Template",
        "template": "Manual/Stamp Template",
        "generic": "Individual Mass TG",
    }
    return methods.get(method, method.capitalize())

def sortByHighest(view: dict):
    if not isinstance(view, dict):
        return []
    return sorted(view.items(), key=lambda item: item[1], reverse=True)

def sortTop(view: dict, count: int = 5):
    return sortByHighest(view)[:count]

def sortStatsByHighest(view: dict):
    if not isinstance(view, dict):
        return []
    return sorted(view.items(), key=lambda item: item[1].delivered if hasattr(item[1], 'delivered') else item[1].get('delivered', 0), reverse=True)

def sortStatsTop(view: dict, count: int = 5):
    return sortStatsByHighest(view)[:count]

def displayNumberWithCommas(number: int) -> str:
    try:
        return f"{int(number):,}"
    except (ValueError, TypeError):
        return str(number)
