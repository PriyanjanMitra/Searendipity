import re
import typing
import sans

# Format a NationStates nation or region name to be compatible with the API / URL.
def format_nation_or_region(name: str) -> str:
    if not name:
        return ""
    return name.strip().lower().replace(" ", "_")

def check_if_nation_exists(nation: str) -> bool:
    """Check whether a nation currently exists on NationStates."""
    formatted = format_nation_or_region(nation)
    if not formatted:
        return False
    query = sans.Nation(formatted, "name")

    try:
        response = sans.get(query)
        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            return False
        else:
            return False
    except Exception as e:
        print(f"Warning: Failed to check nation {nation}: {e}")
        return False

def parse_template_id(template_str: str) -> typing.Optional[int]:
    """Parse template ID string formatted as %TEMPLATE-12345% or raw numbers 12345."""
    if not template_str:
        return None
    template_str = template_str.strip()
    match = re.search(r"%?TEMPLATE-([0-9]+)%?", template_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if template_str.isdigit():
        return int(template_str)
    return None
