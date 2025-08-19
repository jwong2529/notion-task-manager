# Notion Task Manager

A Python CLI tool to quickly add tasks to a Notion database, with flexible input for dates, timezones, and recurring “quick access” times.  

I'm using this script to manage assignments and deadlines in my Notion database through the CLI instead of the Notion UI (because it's overstimulating 😕).

---

## What It Does

- **Interactive prompts** for all task properties defined in your Notion database  
- **Flexible date input**: supports `YYYY-MM-DD`, `MM-DD`, and optional time.  
- **Quick-access times**: choose from pre-defined common times if no time is provided.  
- **Timezone support**: choose a timezone or use the default.  
- **Supports select, multi-select, status, people, and relation properties**.  
- **Summarizes the task** before submitting to Notion.  

---

## Setup

### 1. Clone the repository

```bash
git clone <repo_url>
cd <repo_directory>
```

### 2. Install dependencies
```bash
pip install notion-client python-dotenv
```

### 3. Set up Notion integration
1. Go to [Notion Integrations](https://www.notion.so/my-integrations).
2. Click + New Integration.
   3. Give it a name.
   4. Select the workspace where your database lives.
   5. Under Capabilities, enable:
      6. Read content.
      7. Insert content.
      8. Update content.
9. Click Submit.
10. Copy the Internal Integration Token (this is your NOTION_SECRET).
11. Go to the Access tab and enable access to the page that has your database.
12. Go to your database on the web and copy the link. Extract the Database ID:
    13. `https://www.notion.so/myworkspace/<DATABASE_ID>?v=...`.

### 4. Configure .env
Modify the `.sample_env` file with your desired information. Remember to rename the file to `.env` afterward.
- NOTION_SECRET: Your Notion integration token.
- DATABASE_ID: ID of the database where tasks will be added.
- PROPERTIES: List of property names in the database you want to be prompted for.
- DEFAULT_TIMEZONE: The timezone used when the user skips the timezone prompts.
- TIMEZONE_CHOICES: List of available timezones to choose from.
- QUICK_ACCESS_TIMES: Pre-defined times to quickly assign deadlines, e.g. 11:59 PM for most assignments.

### 5. Run the script
```bash
python main.py
```
