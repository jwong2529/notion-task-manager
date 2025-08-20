import os
from notion_client import Client
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo

# Load env variables
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_SECRET")
DATABASE_ID = os.getenv("DATABASE_ID")
PROPERTIES = [p.strip() for p in os.getenv("PROPERTIES", "").split(",")]

DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")
TIMEZONE_CHOICES = [t.strip() for t in os.getenv("TIMEZONE_CHOICES", "").split(",") if t.strip()]
QUICK_ACCESS_TIMES = [t.strip() for t in os.getenv("QUICK_ACCESS_TIMES", "").split(",") if t.strip()]

# Init client
notion = Client(auth=NOTION_TOKEN)

def pick_timezone():
    """Pick timezone from list or fallback to default."""
    if not TIMEZONE_CHOICES:
        return DEFAULT_TZ
    print("\nChoose a timezone:")
    for i, tz in enumerate(TIMEZONE_CHOICES, 1):
        print(f"[{i}] {tz}")
    choice = input(f"Enter number (or leave blank for default={DEFAULT_TZ}): ").strip()
    if not choice:
        return DEFAULT_TZ
    if choice.isdigit() and 1 <= int(choice) <= len(TIMEZONE_CHOICES):
        return TIMEZONE_CHOICES[int(choice)-1]
    print("⚠️ Invalid choice, using default.")
    return DEFAULT_TZ

def format_date_input(user_input: str):
    """Convert user date input into Notion date format (with optional time).
       Supports:
       - Dates: YYYY-MM-DD, MM-DD, and shorthand MMDD like '817' or '0817'
       - Times: HH:MM (24h), H:MM AM/PM, digit-only '232' or '1259',
                and digit-only with AM/PM like '232 PM'
    """
    import re
    if not user_input.strip():
        return None

    # Split into date + optional time (everything after the first token is "time_part")
    parts = user_input.strip().split()
    date_part = parts[0]
    time_part = " ".join(parts[1:]) if len(parts) > 1 else None
    tz = ZoneInfo(pick_timezone())

    # --- Parse date (supports '817'/'0817' -> Aug 17 of current year) ---
    dt = None
    if date_part.isdigit() and len(date_part) in (3, 4):
        if len(date_part) == 3:   # e.g., 817 -> 8/17
            month = int(date_part[0])
            day = int(date_part[1:])
        else:                     # e.g., 0817 -> 08/17
            month = int(date_part[:2])
            day = int(date_part[2:])
        dt = datetime(datetime.now().year, month, day)

    if not dt:
        for fmt in ("%Y-%m-%d", "%m-%d"):
            try:
                dt = datetime.strptime(date_part, fmt)
                if fmt == "%m-%d":
                    dt = dt.replace(year=datetime.now().year)
                break
            except ValueError:
                continue

    if not dt:
        raise ValueError("Invalid date. Examples: '2025-08-17', '08-17', '817', or '0817'.")

    # --- Parse time (if provided) ---
    if time_part:
        # 1) Try typical formats first: 24h with colon, then 12h with colon+AM/PM
        for time_fmt in ("%H:%M", "%I:%M %p"):
            try:
                t = datetime.strptime(time_part, time_fmt)
                dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                return {"date": {"start": dt.isoformat()}}
            except ValueError:
                pass

        # 2) Try digit-only with optional AM/PM, e.g. "232", "1259", "232 PM"
        m = re.match(r"^\s*(\d{1,4})\s*(am|pm|AM|PM)?\s*$", time_part)
        if m:
            digits = m.group(1)
            ampm = (m.group(2) or "").lower()

            # Convert digits -> hour/minute
            if len(digits) in (3, 4):
                hour = int(digits[:-2])
                minute = int(digits[-2:])
            elif len(digits) in (1, 2):
                hour = int(digits)
                minute = 0
            else:
                raise ValueError("Time too long. Use up to 4 digits, e.g. '232' or '1259'.")

            # Validate ranges (pre-AM/PM conversion)
            if not (0 <= minute <= 59):
                raise ValueError("Minute must be 00–59.")
            if ampm:
                # 12-hour normalization
                if not (1 <= hour <= 12):
                    raise ValueError("Hour must be 1–12 when using AM/PM.")
                if ampm == "am":
                    hour = 0 if hour == 12 else hour
                else:  # pm
                    hour = 12 if hour == 12 else hour + 12
            else:
                # No AM/PM -> treat as 24h
                if not (0 <= hour <= 23):
                    raise ValueError("Hour must be 00–23 for 24-hour times.")

            dt = dt.replace(hour=hour, minute=minute, tzinfo=tz)
            return {"date": {"start": dt.isoformat()}}

        # If nothing matched:
        raise ValueError(
            "Invalid time. Examples: '14:30', '2:30 PM', '232', '1259', or '232 PM'."
        )

    # --- No time given -> optionally offer quick access times, else date-only ---
    if QUICK_ACCESS_TIMES:
        print("\nChoose a hardcoded time or leave blank for no time:")
        for i, t in enumerate(QUICK_ACCESS_TIMES, 1):
            print(f"[{i}] {t}")
        choice = input("Enter number or blank: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(QUICK_ACCESS_TIMES):
            t_str = QUICK_ACCESS_TIMES[int(choice) - 1]
            for time_fmt in ("%H:%M", "%I:%M %p"):
                try:
                    t = datetime.strptime(t_str, time_fmt)
                    dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                    return {"date": {"start": dt.isoformat()}}
                except ValueError:
                    continue
        # Blank => date-only
        return {"date": {"start": dt.date().isoformat()}}

    # Date only (no quick access times configured)
    return {"date": {"start": dt.date().isoformat()}}



def choose_from_options(options, multi=False):
    """Display numbered options and let user choose by number(s)."""
    for i, opt in enumerate(options, 1):
        print(f"[{i}] {opt}")
    choice = input("Choose: ").strip()
    if not choice:
        return [] if multi else None
    if multi:
        indices = [int(c.strip()) for c in choice.split(",") if c.strip().isdigit()]
        return [options[i-1] for i in indices if 1 <= i <= len(options)]
    else:
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx-1]
        return None

def prompt_for_property(prop_name, prop_info):
    """Ask user for input depending on property type and return Notion-formatted value."""
    prop_type = prop_info["type"]

    # Title: inline input right after the colon
    if prop_type == "title":
        print()  # uniform one blank line before every property
        user_input = input(f"{prop_name} (title): ").strip()
        if not user_input:
            return None
        return {"title": [{"text": {"content": user_input}}]}

    # Non-title: keep the header line, then inputs on following lines
    print(f"\n{prop_name} ({prop_type}):")

    if prop_type in ("select", "multi_select", "status"):
        options = [opt["name"] for opt in prop_info[prop_type].get("options", [])]
        choice = choose_from_options(options, multi=(prop_type == "multi_select"))
        if not choice:
            return None
        if prop_type == "select":
            return {"select": {"name": choice}}
        elif prop_type == "multi_select":
            return {"multi_select": [{"name": v} for v in choice]}
        elif prop_type == "status":
            return {"status": {"name": choice}}

    elif prop_type == "date":
        user_input = input("e.g. 2025-08-17 11:59 PM or 08-17 11:59 PM or 0817 1159 PM: ").strip()
        if not user_input:
            return None
        return format_date_input(user_input)

    elif prop_type == "people":
        user_input = input("Enter Notion user ID: ").strip()
        if not user_input:
            return None
        return {"people": [{"id": user_input}]}

    elif prop_type == "relation":
        user_input = input("Enter related page ID: ").strip()
        if not user_input:
            return None
        return {"relation": [{"id": user_input}]}

    else:
        print(f"⚠️ Skipping unsupported type: {prop_type}")
        return None

def summarize_task(properties):
    """Pretty-print a summary of what was just added."""
    print("\n=== Task Summary ===")
    for k, v in properties.items():
        if "title" in v:
            print(f"{k}: {v['title'][0]['text']['content']}")
        elif "select" in v:
            print(f"{k}: {v['select']['name']}")
        elif "status" in v:
            print(f"{k}: {v['status']['name']}")
        elif "multi_select" in v:
            vals = [opt["name"] for opt in v["multi_select"]]
            print(f"{k}: {', '.join(vals)}")
        elif "date" in v:
            print(f"{k}: {v['date']['start']}")
        else:
            print(f"{k}: [set]")

def interactive_add_task():
    db = notion.databases.retrieve(DATABASE_ID)
    properties = db["properties"]

    print("\n=== Add a New Task ===")
    notion_props = {}
    for prop_name in PROPERTIES:
        if prop_name not in properties:
            print(f"⚠️ Property '{prop_name}' not found in schema, skipping.")
            continue
        value = prompt_for_property(prop_name, properties[prop_name])
        if value:
            notion_props[prop_name] = value

    page = notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties=notion_props
    )

    summarize_task(notion_props)
    print("\n✅ Task added:", page["url"])

if __name__ == "__main__":
    while True:
        interactive_add_task()
        again = input("\n➕ Do you want to add another task? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            print("👋 Done adding tasks.")
            break

