import sys
import os
from notion_client import Client
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import styling

import itertools
import threading
import time

import signal

def spinner(message="Working"):
    stop = False

    def run():
        for c in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if stop:
                break
            sys.stdout.write(f"\r{styling.dim(message)} {c}")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def end():
        nonlocal stop
        stop = True
        thread.join()

    return end

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
            print(styling.warn(f"Skipping database '{name}' (missing LABEL or ID)"))
            continue
            
        properties = [p.strip() for p in props_raw.split(",") if p.strip()]

        databases[name] = {
            "label": label,
            "id": db_id,
            "properties": properties,
            "allow_time": allow_time,
        }
    
    return databases

def resolve_data_source(database_id):
    db = notion.databases.retrieve(database_id)
    data_sources = db.get("data_sources", [])
    if not data_sources:
        raise ValueError(f"Database {database_id} has no data sources.")
    data_source_id = data_sources[0]["id"]

    ds = notion.request(
        method="GET",
        path=f"/data_sources/{data_source_id}"
    )
    return data_source_id, ds["properties"]

def pick_timezone():
    if not TIMEZONE_CHOICES:
        return DEFAULT_TZ
    print(f"\n{styling.h('Choose a timezone')}")
    for i, tz in enumerate(TIMEZONE_CHOICES, 1):
        print(f"[{i}] {tz}")
    choice = input(f"Enter number (or leave blank for default={DEFAULT_TZ}): ").strip()
    if not choice:
        return DEFAULT_TZ
    if choice.isdigit() and 1 <= int(choice) <= len(TIMEZONE_CHOICES):
        return TIMEZONE_CHOICES[int(choice)-1]
    print(styling.warn("Invalid choice, using default."))
    return DEFAULT_TZ

def format_date_input(user_input: str, allow_time=True, tz=None):
    import re
    import calendar

    if not user_input.strip():
        return None

    def parse_recurrence(parts):
        if not parts:
            return None, None, parts

        last = parts[-1].lower()
        if last in ("repeat", "r"):
            return "repeat", 1, parts[:-1]

        m = re.match(r"^(\d+)([dw])$", last)
        if m:
            count = int(m.group(1))
            unit = m.group(2)
            delta = timedelta(days=1) if unit == "d" else timedelta(weeks=1)
            return "count", (count, delta), parts[:-1]

        dow_pattern = r"^([mtwrfsu]+)(\d+)w$"
        m = re.match(dow_pattern, last)
        if m:
            dow_str = m.group(1)
            weeks = int(m.group(2))
            return "dow", (dow_str, weeks), parts[:-1]

        for idx in range(len(parts) - 1, -1, -1):
            if re.match(r"^[mtwrfsu]+$", parts[idx].lower()):
                dow_str = parts[idx].lower()
                end_date_tokens = parts[idx + 1:]
                parts = parts[:idx]
                return "dow_until", (dow_str, end_date_tokens), parts

        for idx in range(len(parts) - 1, -1, -1):
            if parts[idx].lower() in ("d", "w"):
                unit = parts[idx].lower()
                end_date_tokens = parts[idx + 1:]
                parts = parts[:idx]
                return "until", (timedelta(days=1) if unit == "d" else timedelta(weeks=1), end_date_tokens), parts

        return None, None, parts

    def parse_end_date(tokens):
        if not tokens:
            return None

        result = format_date_input(" ".join(tokens), allow_time=False, tz=tz)
        start = result["date"]["start"]

        if "T" in start:
            return datetime.fromisoformat(start)
        else:
            return datetime.fromisoformat(start + "T00:00:00")

    parts = user_input.strip().split()
    recurrence_mode, recurrence_info, parts = parse_recurrence(parts)

    if not parts:
        parts = ["today"]
    
    date_part = parts[0]
    time_part = " ".join(parts[1:]) if len(parts) > 1 else None

    now = datetime.now()
    dt = None

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

    consumed = 0

    if tokens:
        if tokens[0] in ("today",):
            dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("tomorrow",):
            dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1
        elif tokens[0] in ("yesterday",):
            dt = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

        elif tokens[0] in ("this", "next") and len(tokens) >= 2:
            wd_full = norm_weekday(tokens[1])
            if wd_full in weekdays_map:
                target = weekdays_map[wd_full]
                today = now.weekday()

                if tokens[0] == "this":
                    start_of_week = now - timedelta(days=today)
                    candidate = start_of_week + timedelta(days=target)
                    if candidate.date() < now.date():
                        candidate += timedelta(weeks=1)
                    dt = candidate

                else:
                    start_of_next_week = now - timedelta(days=today) + timedelta(weeks=1)
                    dt = start_of_next_week + timedelta(days=target)

                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                consumed = 2

        elif norm_weekday(tokens[0]) in weekdays_map:
            wd_full = norm_weekday(tokens[0])
            target = weekdays_map[wd_full]
            today = now.weekday()
            days_ahead = (target - today) % 7
            dt = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
            consumed = 1

    if dt is not None:
        remainder = " ".join(parts[consumed:]).strip()
        time_part = remainder if remainder else None

    if dt is None and date_part.isdigit():
        year_explicit = False

        if len(date_part) == 3:
            month = int(date_part[0])
            day = int(date_part[1:])
            year = now.year
        
        elif len(date_part) == 4:
            month = int(date_part[:2])
            day = int(date_part[2:])
            year = now.year

        elif len(date_part) == 6:
            month = int(date_part[:2])
            day = int(date_part[2:4])
            yy = int(date_part[4:])
            year = 2000 + yy if yy <= 69 else 1900 + yy
            year_explicit = True
        
        elif len(date_part) == 8:
            month = int(date_part[:2])
            day = int(date_part[2:4])
            year = int(date_part[4:])
            year_explicit = True
        
        else:
            month = day = year = None
        
        if month and day and year:
            dt = datetime(year, month, day)

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

        if recurrence_mode == "dow":
            dow_str, weeks = recurrence_info
            dow_map = {"m": 0, "t": 1, "w": 2, "r": 3, "f": 4, "s": 5, "u": 6}
            
            target_days = []
            for c in dow_str:
                if c in dow_map:
                    target_days.append(dow_map[c])
            
            if not target_days:
                return [dt]
            
            target_days = sorted(set(target_days))
            
            dates = []
            current_date = dt.date()
            
            for week_offset in range(weeks):
                for target_day in target_days:
                    days_ahead = (target_day - dt.weekday()) % 7
                    if week_offset == 0 and days_ahead == 0:
                        days_ahead = 0
                    candidate_date = current_date + timedelta(days=days_ahead + (week_offset * 7))
                    
                    if candidate_date >= current_date:
                        candidate = datetime.combine(candidate_date, datetime.min.time())
                        candidate = candidate.replace(hour=dt.hour, minute=dt.minute, second=dt.second, microsecond=dt.microsecond, tzinfo=dt.tzinfo)
                        dates.append(candidate)
            
            return dates

        if recurrence_mode == "dow_until":
            dow_str, end_tokens = recurrence_info
            dow_map = {"m": 0, "t": 1, "w": 2, "r": 3, "f": 4, "s": 5, "u": 6}
            
            target_days = []
            for c in dow_str:
                if c in dow_map:
                    target_days.append(dow_map[c])
            
            if not target_days:
                return [dt]
            
            target_days = sorted(set(target_days))
            
            end_dt = parse_end_date(end_tokens)
            if not end_dt:
                return [dt]
            
            MAX_RECURRENCES = 200
            dates = []
            current_date = dt.date()
            week_offset = 0
            
            while True:
                for target_day in target_days:
                    days_ahead = (target_day - dt.weekday()) % 7
                    if week_offset == 0 and days_ahead == 0:
                        days_ahead = 0
                    candidate_date = current_date + timedelta(days=days_ahead + (week_offset * 7))
                    
                    if candidate_date > end_dt.date():
                        return dates
                    
                    if candidate_date >= current_date:
                        if len(dates) >= MAX_RECURRENCES:
                            raise ValueError(f"Recurrence exceeds {MAX_RECURRENCES} entries.")
                        candidate = datetime.combine(candidate_date, datetime.min.time())
                        candidate = candidate.replace(hour=dt.hour, minute=dt.minute, second=dt.second, microsecond=dt.microsecond, tzinfo=dt.tzinfo)
                        dates.append(candidate)
                
                week_offset += 1
                if week_offset > 100:
                    return dates
            
            return dates

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

    if time_part:
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

        m = re.match(r"^\s*(\d{1,4})\s*(am|pm|AM|PM)?\s*$", time_part)
        if m:
            digits = m.group(1)
            ampm = (m.group(2) or "").lower()

            if len(digits) in (3, 4):
                hour = int(digits[:-2])
                minute = int(digits[-2:])
            elif len(digits) in (1, 2):
                hour = int(digits)
                minute = 0
            else:
                raise ValueError("Time too long. Use up to 4 digits, e.g. '232' or '1259'.")

            if not (0 <= minute <= 59):
                raise ValueError("Minute must be 00–59.")
            if ampm:
                if not (1 <= hour <= 12):
                    raise ValueError("Hour must be 1–12 when using AM/PM.")
                if ampm == "am":
                    hour = 0 if hour == 12 else hour
                else:
                    hour = 12 if hour == 12 else hour + 12
            else:
                if not (0 <= hour <= 23):
                    raise ValueError("Hour must be 00–23 for 24-hour times.")

            dt = dt.replace(hour=hour, minute=minute, tzinfo=tz)
            had_explicit_time = True
            dates = build_recurrences(dt)
            return {
                "date": {"start": dates[0].isoformat()},
                "_recurrences": dates[1:]
            }

        raise ValueError(
            "Invalid time. Examples: '14:30', '2:30 PM', '232', '1259', or '232 PM'."
        )

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
                    dates = build_recurrences(dt)
                    return {
                        "date": {"start": dates[0].isoformat()},
                        "_recurrences": dates[1:]
                    }
                except ValueError:
                    continue

        dates = build_recurrences(dt)
        return {
            "date": {"start": dates[0].date().isoformat()},
            "_recurrences": [d.date().isoformat() for d in dates[1:]]
        }
    
    dates = build_recurrences(dt)
    return {
        "date": {"start": dates[0].date().isoformat()},
        "_recurrences": [d.date().isoformat() for d in dates[1:]]
    }

def choose_from_options(options, multi=False):
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

def prompt_for_property(prop_name, prop_info, allow_time, tz):
    prop_type = prop_info["type"]

    if prop_type == "title":
        print()
        user_input = input(f"{prop_name} (title): ").strip()
        if not user_input:
            return None
        return {"title": [{"text": {"content": user_input}}]}

    print(f"\n{styling.h(f'{prop_name}')} {styling.dim(f'({prop_type})')}")

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
        print(styling.dim("Enter a date (examples: '2025-08-17 11:59 PM', '08-17', '0817 1159 PM')"))
        print(styling.dim("Shortcuts: 'today', 'tomorrow', 'this tue', 'next fri'"))
        print(styling.dim("Recurrence: 'mwf3w' (Mon/Wed/Fri for 3 weeks), 'tr2w' (Tue/Thu for 2 weeks)"))
        while True:
            user_input = input("Date: ").strip()
            if not user_input:
                return None
            try:
                return format_date_input(user_input, allow_time=allow_time, tz=tz)
            except ValueError as e:
                print(styling.err(f"{e}. Try again."))

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
                print(styling.err("Invalid number."))
    else:
        print(styling.warn(f"Skipping unsupported type: {prop_type}"))
        return None

def summarize_task(properties):
    print(f"\n{styling.h('Task Summary')}")
    for k, v in properties.items():
        if "title" in v:
            print(f"{styling.dim(k)}: {v['title'][0]['text']['content']}")
        elif "select" in v:
            print(f"{styling.dim(k)}: {v['select']['name']}")
        elif "status" in v:
            print(f"{styling.dim(k)}: {v['status']['name']}")
        elif "multi_select" in v:
            vals = [opt["name"] for opt in v["multi_select"]]
            print(f"{styling.dim(k)}: {', '.join(vals)}")
        elif "date" in v:
            print(f"{styling.dim(k)}: {v['date']['start']}")
        elif "number" in v:
            print(f"{styling.dim(k)}: {v['number']}")
        else:
            print(f"{styling.dim(k)}: [set]")

def interactive_add_task(data_source_id, schema, PROPERTIES, db_label, allow_time, tz):
    
    properties = schema

    print(f"\n{styling.h(f'Add a New Entry → {db_label}')}")
    notion_props = {}

    for prop_name in PROPERTIES:
        if prop_name not in properties:
            print(styling.warn(f"Property '{prop_name}' not found in schema, skipping."))
            continue
        value = prompt_for_property(prop_name, properties[prop_name], allow_time, tz)
        if value:
            notion_props[prop_name] = value

    recurrences = []
    for v in notion_props.values():
        if isinstance(v, dict) and "_recurrences" in v:
            recurrences = v.pop("_recurrences")
            break
    
    total = 1 + len(recurrences)
    print(f"""\n{styling.dim(f"This will create {total} {'entry' if total == 1 else 'entries'}.")}""")
    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print(styling.warn("Cancelled."))
        return
    
    pages = []

    stop_spinner = spinner(f"Creating {'entry' if total == 1 else 'entries'}...")

    try:
        first_page = notion.pages.create(
            parent={
                "type": "data_source_id",
                "data_source_id": data_source_id
            },
            properties=notion_props
        )
        pages.append(first_page)

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
                    parent={
                        "type": "data_source_id",
                        "data_source_id": data_source_id
                    },
                    properties=dup_props
                )
            )
    finally:
        stop_spinner()

    summarize_task(notion_props)

    print(f"\n{styling.ok(f'✓ Added {len(pages)} task(s) to {db_label}')}")
    for p in pages:
        print(p["url"])

def main():
    while True:
        try:
            tz = ZoneInfo(pick_timezone())
            break
        except KeyboardInterrupt:
            try:
                confirm = input("\nAre you sure you want to quit? (y/n): ").strip().lower()
            except KeyboardInterrupt:
                print(styling.ok("\nGoodbye!"))
                sys.exit(0)
                
            if confirm in ("y", "yes"):
                print(styling.ok("Goodbye!"))
                sys.exit(0)
            else:
                print(styling.ok("Resuming..."))

    DATABASES = load_databases_from_env()
    if not DATABASES:
        print(styling.err("No databases configured. Check your .env file."))
        sys.exit(1)

    DATABASE_ID = None
    PROPERTIES = None
    db_label = None

    while True:
        try:
            if DATABASE_ID is None:
                keys = list(DATABASES.keys())

                print(f"\n{styling.h('Choose a database')}")
                for i, key in enumerate(keys, 1):
                    print(f"[{i}] {DATABASES[key]['label']}")

                choice = input("Enter number: ").strip()

                if not choice.isdigit() or not (1 <= int(choice) <= len(keys)):
                    print(styling.err("Invalid choice."))
                    continue

                selected = DATABASES[keys[int(choice) - 1]]
                DATABASE_ID = selected["id"]
                PROPERTIES = selected["properties"]
                db_label = selected["label"]
                ALLOW_TIME = selected["allow_time"]
                data_source_id, schema = resolve_data_source(DATABASE_ID)

            interactive_add_task(data_source_id, schema, PROPERTIES, db_label, selected["allow_time"], tz)

            again = input(
                "\nAdd another entry? (y = same DB / s = switch DB / n = quit): "
            ).strip().lower()

            if again in ("y", "yes"):
                continue
            elif again in ("s", "switch"):
                DATABASE_ID = None
                PROPERTIES = None
                db_label = None
            else:
                print(styling.ok("Done adding entries."))
                break
        except KeyboardInterrupt:
            try:
                confirm = input("\nAre you sure you want to quit? (y/n): ").strip().lower()
            except KeyboardInterrupt:
                print(styling.ok("\nGoodbye!"))
                sys.exit(0)
            if confirm in ("y", "yes"):
                print(styling.ok("Goodbye!"))
                sys.exit(0)
            else:
                print(styling.ok("Resuming..."))

if __name__ == "__main__":
    load_dotenv()
    NOTION_TOKEN = os.getenv("NOTION_SECRET")

    DEFAULT_TZ = os.getenv("DEFAULT_TIMEZONE", "UTC")
    TIMEZONE_CHOICES = [t.strip() for t in os.getenv("TIMEZONE_CHOICES", "").split(",") if t.strip()]
    QUICK_ACCESS_TIMES = [t.strip() for t in os.getenv("QUICK_ACCESS_TIMES", "").split(",") if t.strip()]   

    notion = Client(auth=NOTION_TOKEN)  

    main()