#!/usr/bin/env python3
"""
Fetches live World Cup 2026 standings from api-football (api-sports.io)
and injects them into index.html. Run by GitHub Actions every 3 hours.

Requires env var: API_FOOTBALL_KEY
Set it in GitHub repo Settings -> Secrets -> Actions -> New repository secret
"""
import json, re, os, urllib.request
from datetime import datetime, timezone

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
STANDINGS_URL = "https://v3.football.api-sports.io/standings?league=1&season=2026"
TEAMS_URL     = "https://v3.football.api-sports.io/teams?league=1&season=2026"

def get_json(url):
    req = urllib.request.Request(url, headers={
        "x-apisports-key": API_KEY,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def fetch_groups():
    if not API_KEY:
        raise RuntimeError("API_FOOTBALL_KEY env var not set")

    data = get_json(STANDINGS_URL)

    # Check for errors
    errors = data.get("errors", {})
    if errors:
        raise RuntimeError(f"API error: {errors}")

    # The standings response nests groups inside league.standings
    # Each item in standings is a list of teams in one group
    raw = data.get("response", [])
    if not raw:
        raise RuntimeError("Empty response from standings endpoint")

    league_data = raw[0].get("league", {})
    raw_groups  = league_data.get("standings", [])

    if not raw_groups:
        raise RuntimeError("No standings data in response")

    groups = []
    for grp in raw_groups:
        if not grp:
            continue
        # Group name is in each team's "group" field e.g. "Group A"
        letter = grp[0].get("group", "Group ?").replace("Group ", "").strip()
        teams  = []
        for t in grp:
            team_info = t.get("team", {})
            all_stats = t.get("all", {})
            goals     = all_stats.get("goals", {})
            w   = int(all_stats.get("win",  0))
            d   = int(all_stats.get("draw", 0))
            l   = int(all_stats.get("lose", 0))
            gf  = int(goals.get("for",     0))
            ga  = int(goals.get("against", 0))
            pts = int(t.get("points", w * 3 + d))
            teams.append({
                "name":   team_info.get("name", "Unknown"),
                "pts":    pts,
                "w":      w,
                "d":      d,
                "l":      l,
                "gf":     gf,
                "ga":     ga,
                "gd":     gf - ga,
                "played": w + d + l,
            })
        teams.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
        groups.append({"group": letter, "teams": teams})

    groups.sort(key=lambda x: x["group"])
    print(f"Fetched {len(groups)} groups, {sum(len(g['teams']) for g in groups)} teams")
    return groups

def read_from_html():
    """Fallback: extract existing data from index.html"""
    with open("index.html", "r") as f:
        html = f.read()
    m = re.search(r"const GROUPS_DATA = (\[.*?\]);", html, re.DOTALL)
    if m:
        print("Using fallback data from existing index.html")
        return json.loads(m.group(1))
    raise RuntimeError("Could not parse fallback data from index.html")

def build_html(groups):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    with open("index.html", "r") as f:
        html = f.read()

    # Replace timestamp (plain string, no regex)
    ts_start = 'const UPDATED = "'
    ts_end   = '";'
    i = html.index(ts_start)
    j = html.index(ts_end, i) + len(ts_end)
    html = html[:i] + f'{ts_start}{updated}"{ts_end[1:]}' + html[j:]

    # Replace groups data (bracket-depth walk, avoids regex + unicode issues)
    data_str     = json.dumps(groups, separators=(',', ':'), ensure_ascii=True)
    start_marker = "const GROUPS_DATA = "
    i = html.index(start_marker)
    bracket_start = html.index("[", i)
    depth, pos = 0, bracket_start
    while pos < len(html):
        if   html[pos] == "[": depth += 1
        elif html[pos] == "]": depth -= 1
        if depth == 0: break
        pos += 1
    html = html[:i] + start_marker + data_str + html[pos + 1:]

    with open("index.html", "w") as f:
        f.write(html)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    try:
        groups = fetch_groups()
    except Exception as e:
        print(f"Live fetch failed: {e}")
        try:
            groups = read_from_html()
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            raise SystemExit(1)
    build_html(groups)
