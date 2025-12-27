import sys
import os
from notion_client import Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

def load_databases_from_env():
    databases = {}

    raw = os.getenv("DATABASES", "")
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]

    for name in names:
        prefix = f"DB_{name.upper()}"

        label = os.getenv(f"{prefix}_LABEL")
        db_id = os.getenv(f"{prefix}_ID")
        props_raw = os.getenv(f"{prefix}_PROPS", "")
        allow_time = os.getenv(f"{prefix}_ALLOW_TIME", "true").lower() == "true"


        if not label or not db_id:
            print(f"Skipping database '{name}' (missing LABEL or ID)")
            continue
            
        properties = [p.strip() for p in props_raw.split(",") if p.strip()]

        databases[name] = {
            "label": label,
            "id": db_id,
            "properties": properties,
            "allow_time": allow_time,
        }
    
    return databases

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
    print("Invalid choice, using default.")
    return DEFAULT_TZ

def format_date_input(user_input: str, allow_time =True, tz=None):
    """Convert user date input into Notion date format (with optional time)."""
    import re
    import calendar

    if not user_input.strip():
        return None

    def parse_recurrence(parts):
        if not parts:
            return None, None, parts

        # Case 1: repeat
        last = parts[-1].lower()
        if last in ("repeat", "r"):
            return "repeat", 1, parts[:-1]

        # Case 2: count-based (3d / 2w)
        m = re.match(r"^(\d+)([dw])$", last)
        if m:
            count = int(m.group(1))
            unit = m.group(2)
            delta = timedelta(days=1) if unit == "d" else timedelta(weeks=1)
            return "count", (count, delta), parts[:-1]

        # Case 3: until-date (d <date...> / w <date...>)
        if len(parts) >= 2 and parts[-2].lower() in ("d", "w"):
            unit = parts[-2].lower()
            end_date_tokens = parts[-1:]

            # allow multi-token natural dates: keep shifting left
            i = len(parts) - 1
            while i - 1 >= 0 and parts[i - 1].lower() not in ("d", "w"):
                end_date_tokens.insert(0, parts[i - 1])
                i -= 1

            delta = timedelta(days=1) if unit == "d" else timedelta(weeks=1)
            return "until", (delta, end_date_tokens), parts[:i - 1]

        return None, None, parts

    def parse_end_date(tokens):
        if not tokens:
            return None

        # Reuse the same function recursively, but disable recurrence
        result = format_date_input(" ".join(tokens), allow_time=False, tz=tz)
        start = result["date"]["start"]

        # Convert to datetime for comparison
        if "T" in start:
            return datetime.fromisoformat(start)
        else:
            return datetime.fromisoformat(start + "T00:00:00")

    # Original split (kept)
    parts = user_input.strip().split()
    recurrence_mode, recurrence_info, parts = parse_recurrence(parts)

    date_part = parts[0]
    time_part = " ".join(parts[1:]) if len(parts) > 1 else None
    if tz is None:
        tz = ZoneInfo(pick_timezone())

    now = datetime.now()
    dt = None  # will be set by weekday/shortcut OR by numeric parsing below

    # ── Weekday & shortcut parsing (non-destructive to original flows) ──
    tokens = [p.lower() for p in parts]
    weekdays_map = {day.lower(): i for i, day in enumerate(calendar.day_name)}
    aliases = {
        "mon": "monday",
        "tue": "tuesday", "tues": "tuesday",
        "wed": "wednesday", "weds": "wednesday",
        "thu": "thursday", "thur": "thursday", "thurs": "thursday",
        "fri": "friday",
        "sat": "saturday",
        "sun": "sunday",
    }

    def norm_weekday(tok: str):
        return aliases.get(tok.lower(), tok.lower())

    consumed = 0  # how many tokens belong to the date phrase we parse here

    if tokens:
        # Shortcuts: today / tomorrow
        if tokens[0] in ("today",):
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("tomorrow",):
            dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("yesterday",):
            dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

        # "this/next <weekday>"
        elif tokens[0] in ("this", "next") and len(tokens) >= 2:
            wd_full = norm_weekday(tokens[1])
            if wd_full in weekdays_map:
                target = weekdays_map[wd_full]
                today = now.weekday()  # Monday=0, Sunday=6

                if tokens[0] == "this":
                    # Start of this week (Monday)
                    start_of_week = now - timedelta(days=today)
                    candidate = start_of_week + timedelta(days=target)
                    # If that day already passed, roll forward to next week
                    if candidate.date() < now.date():
                        candidate += timedelta(weeks=1)
                    dt = candidate

                else:  # "next"
                    # Start of *next* calendar week (Monday)
                    start_of_next_week = now - timedelta(days=today) + timedelta(weeks=1)
                    dt = start_of_next_week + timedelta(days=target)

                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                consumed = 2

        # Just a weekday ("tuesday"/"tue")
        elif norm_weekday(tokens[0]) in weekdays_map:
            wd_full = norm_weekday(tokens[0])
            target = weekdays_map[wd_full]
            today = now.weekday()
            days_ahead = (target - today) % 7  # next occurrence, including today
            dt = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

    # If we matched a weekday/shortcut, recompute time_part from remaining tokens
    if dt is not None:
        remainder = " ".join(parts[consumed:]).strip()
        time_part = remainder if remainder else None

    if dt is None and date_part.isdigit():
        year_explicit = False

        if len(date_part) == 3: #817
            month = int(date_part[0])
            day = int(date_part[1:])
            year = now.year
        
        elif len(date_part) == 4: # 0817
            month = int(date_part[:2])
            day = int(date_part[2:])
            year = now.year

        elif len(date_part) == 6: # 011726
            month = int(date_part[:2])
            day = int(date_part[2:4])
            yy = int(date_part[4:])
            year = 2000 + yy if yy <= 69 else 1900 + yy
            year_explicit = True
        
        elif len(date_part) == 8: #01172026
            month = int(date_part[:2])
            day = int(date_part[2:4])
            year = int(date_part[4:])
            year_explicit = True
        
        else:
            month = day = year = None
        
        if month and day and year:
            dt = datetime(year, month, day)

            # Roll forward if implied-year date is in the past
            if not year_explicit and dt.date() < now.date():
                dt = dt.replace(year = now.year + 1)

    if dt is None:
        for fmt in ("%Y-%m-%d", "%m-%d"):
            try:
                dt = datetime.strptime(date_part, fmt)
                if fmt == "%m-%d":
                    dt = dt.replace(year=now.year)
                    if dt.date() < now.date():
                        dt = dt.replace(year = now.year + 1)
                break
            except ValueError:
                continue

    if dt is None:
        raise ValueError("Invalid date. Examples: '2025-08-17', '08-17', '817', '0817', '011726', or '01172026'; also 'today', 'tuesday', 'this fri', 'next wed'.")


    def build_recurrences(dt):
        if not recurrence_mode:
            return [dt]

        if recurrence_mode == "repeat":
            return [dt, dt + timedelta(weeks=1)]

        if recurrence_mode == "count":
            count, delta = recurrence_info
            return [dt + i * delta for i in range(count)]

        if recurrence_mode == "until":
            delta, end_tokens = recurrence_info
            end_dt = parse_end_date(end_tokens)

            if not end_dt:
                return [dt]

            MAX_RECURRENCES = 200
            dates = []
            cur = dt
            while cur.date() <= end_dt.date():
                if len(dates) >= MAX_RECURRENCES:
                    raise ValueError(
                        f"Recurrence exceeds {MAX_RECURRENCES} entries."
                    )
                dates.append(cur)
                cur += delta
            return dates

        return [dt]


    had_explicit_time = False

    # --- Parse time ---
    if time_part:
        # 1) Try typical formats first: 24h with colon, then 12h with colon+AM/PM
        for time_fmt in ("%H:%M", "%I:%M %p"):
            try:
                t = datetime.strptime(time_part, time_fmt)
                dt = dt.replace(hour=t.hour, minute=t.minute, tzinfo=tz)
                had_explicit_time = True

                dates = build_recurrences(dt)
                return {
                    "date": {"start": dates[0].isoformat()},
                    "_recurrences": dates[1:]
                }
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
            had_explicit_time = True
            dates = build_recurrences(dt)
            return {
                "date": {"start": dates[0].isoformat()},
                "_recurrences": dates[1:]
            }

        # If nothing matched:
        raise ValueError(
            "Invalid time. Examples: '14:30', '2:30 PM', '232', '1259', or '232 PM'."
        )

    # --- No time given -> optionally offer quick access times, else date-only ---
    if allow_time and QUICK_ACCESS_TIMES:
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
        dates = build_recurrences(dt)
        return {
            "date": {"start": dates[0].date().isoformat()},
            "_recurrences": [d.date().isoformat() for d in dates[1:]]
        }
    
    # Date only (no quick access times configured)
    dates = build_recurrences(dt)
    return {
        "date": {"start": dates[0].date().isoformat()},
        "_recurrences": [d.date().isoformat() for d in dates[1:]]
    }

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

def prompt_for_property(prop_name, prop_info, allow_time):
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
        print("Enter a date (examples: '2025-08-17 11:59 PM', '08-17', '0817 1159 PM')")
        print("Shortcuts: 'today', 'tomorrow', 'this tue', 'next fri'")
        while True:
            user_input = input("Date: ").strip()
            if not user_input:
                return None
            try:
                return format_date_input(user_input, allow_time=allow_time)
            except ValueError as e:
                print(f"{e}. Try again.")

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

    elif prop_type == "number":
        while True:
            user_input = input("Enter a number: ").strip()
            if not user_input:
                return None
            try:
                return {"number": float(user_input)}
            except ValueError:
                print("Invalid number.")
    else:
        print(f"Skipping unsupported type: {prop_type}")
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
        elif "number" in v:
            print(f"{k}: {v['number']}")
        else:
            print(f"{k}: [set]")

def interactive_add_task(DATABASE_ID, PROPERTIES, db_label, allow_time):
    db = notion.databases.retrieve(DATABASE_ID)
    properties = db["properties"]

    print(f"\n=== Add a New Entry to {db_label} ===")
    notion_props = {}

    for prop_name in PROPERTIES:
        if prop_name not in properties:
            print(f"Property '{prop_name}' not found in schema, skipping.")
            continue
        value = prompt_for_property(prop_name, properties[prop_name], allow_time)
        if value:
            notion_props[prop_name] = value

    # extract recurrences (if any)
    recurrences = []
    for v in notion_props.values():
        if isinstance(v, dict) and "_recurrences" in v:
            recurrences = v.pop("_recurrences")
            break
    
    total = 1 + len(recurrences)
    print(f"\nThis will create {total} task(s).")
    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return
    
    pages = []

    # create first page
    first_page = notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties=notion_props
    )
    pages.append(first_page)

    # duplicate for recurrences
    for dt in recurrences:
        dup_props = {}

        for k, v in notion_props.items():
            if "date" in v:
                dup_props[k] = {
                    "date": {
                        "start": dt.isoformat() if isinstance(dt, datetime) else dt
                    }
                }
            else:
                dup_props[k] = v

        pages.append(
            notion.pages.create(
                parent={"database_id": DATABASE_ID},
                properties=dup_props
            )
        )

    # summary (once)
    summarize_task(notion_props)

    print(f"\n✅ Added {len(pages)} task(s) to {db_label}:")
    for p in pages:
        print(p["url"])


if __name__ == "__main__":

    # Load env variables
    load_dotenv()
    NOTION_TOKEN = os.getenv("NOTION_SECRET")

    DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")
    TIMEZONE_CHOICES = [t.strip() for t in os.getenv("TIMEZONE_CHOICES", "").split(",") if t.strip()]
    QUICK_ACCESS_TIMES = [t.strip() for t in os.getenv("QUICK_ACCESS_TIMES", "").split(",") if t.strip()]   

    # Init client
    notion = Client(auth=NOTION_TOKEN)  

    DATABASES = load_databases_from_env()
    if not DATABASES:
        print("No databases configured. Check your .env file.")
        sys.exit(1)

    DATABASE_ID = None
    PROPERTIES = None
    db_label = None

    while True:
        keys = list(DATABASES.keys())

        print("\nWhich database do you want to add to?")
        for i, key in enumerate(keys, 1):
            print(f"[{i}] {DATABASES[key]['label']}")

        choice = input("Enter number: ").strip()

        if not choice.isdigit() or not (1 <= int(choice) <= len(keys)):
            print("Invalid choice.")
            continue

        selected = DATABASES[keys[int(choice) - 1]]
        DATABASE_ID = selected["id"]
        PROPERTIES = selected["properties"]
        db_label = selected["label"]
        ALLOW_TIME = selected["allow_time"]

        interactive_add_task(DATABASE_ID, PROPERTIES, db_label, selected["allow_time"])

        again = input(
            "\nAdd another entry? (y = same DB / s = switch DB / n = quit): "
        ).strip().lower()

        if again in ("y", "yes"):
            continue
        elif again in ("s", "switch"):
            # Reset DB so next loop will ask again
            DATABASE_ID = None
            PROPERTIES = None
            db_label = None
        else:
            print("Done adding entries.")
            break

