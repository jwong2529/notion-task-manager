# Notion Manager

A Python CLI tool to quickly add entries to Notion databases, with flexible input for dates, timezones, and recurring “quick access” times.  

I'm using this script to manage assignments, deadlines, and task durations in my Notion databases through the CLI instead of the Notion UI (because it's overstimulating 😕).

---

## What It Does

- **Interactive prompts** for all properties defined in your Notion database.  
- **Flexible date input**: supports `YYYY-MM-DD`, `MM-DD`, `MMDD`, natural weekday expressions, shortcuts, and optional time.  
- **Quick-access times**: choose from pre-defined common times if no time is provided.  
- **Timezone support**: choose a timezone or use the default.  
- **Supports date, select, multi-select, status, people, and relation properties**. 
- **Basic support for recurring tasks**: `{date} Nw` repeats for N weeks, `{date} Nd` repeats for N consecutive days, `{date} w {date}` repeats weekly until the specified date.
- **Summarizes the task** before submitting to Notion.
- **Add multiple entries** for efficient management.
- **Switch databases** easily.

---

## Setup

### 1. Clone the repository

```bash
git clone <repo_url>
cd <repo_directory>
```

### 2. Install dependencies
Create a virtual environment and activate it.
```bash
python -m venv .venv 
```
```bash
source .venv/bin/activate
```
Then install these.
```bash
pip install notion-client python-dotenv
```

### 3. Set up Notion integration
1. Go to [Notion Integrations](https://www.notion.so/my-integrations).
2. Click + New Integration.
   - Give it a name.
   - Select the workspace where your database lives.
   - Under Capabilities, enable:
     - Read content.
     - Insert content.
     - Update content.
3. Click Submit.
4. Copy the Internal Integration Token (this is your NOTION_SECRET).
5. Go to the Access tab and enable access to the page that has your database.
6. Go to your database on the web and copy the link. Extract the Database ID:
   - `https://www.notion.so/myworkspace/<DATABASE_ID>?v=...`.

### 4. Configure .env
Modify the `.sample_env` file with your desired information. Remember to rename the file to `.env` afterward.
- `NOTION_SECRET`: Your Notion integration token.
- `DEFAULT_TIMEZONE`: The timezone used when the user skips the timezone prompts.
- `TIMEZONE_CHOICES`: List of available timezones to choose from.
- `QUICK_ACCESS_TIMES`: Pre-defined times to quickly assign deadlines, e.g. 11:59 PM for most HW assignments.
- `DATABASES`: Comma-separated list of database keys. Each key must have corresponding `DB_<KEY>_LABEL`, `DB_<KEY>_ID`, `DB_<KEY>_PROPS`, and `DB_<KEY>_ALLOW_TIME`.
   - `DB_<KEY>_LABEL`: Name of the database.
   - `DB_<KEY>_ID`: ID of the database.
   - `DB_<KEY>_PROPS`: List of property names in the database you want to be prompted for.
   - `DB_<KEY>_ALLOW_TIME`: Determines whether the tool will prompt for quick-access times.

Make sure the variable names in your `.env` file match the `os.getenv(...)` calls in the code exactly.

### 5. Run the script
```bash
python main.py
```
