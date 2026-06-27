#!/usr/bin/env python3
"""
Fetches live World Cup 2026 standings from worldcup26.ir
and injects them into index.html. Run by GitHub Actions every 3 hours.
"""
import json, re, urllib.request
from datetime import datetime, timezone

BASE_URL = "https://worldcup26.ir"

def get_json(path):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def fetch_groups():
    try:
        # Step 1 — build id->name map from /get/teams
        teams_data = get_json("/get/teams")
        teams_list = teams_data if isinstance(teams_data, list) else teams_data.get("teams", teams_data.get("data", []))
        id_to_name = {}
        for t in teams_list:
            tid = str(t.get("id", t.get("team_id", "")))
            name = (t.get("name_en") or t.get("name") or "").strip()
            if tid and name:
                id_to_name[tid] = name
        print(f"Loaded {len(id_to_name)} teams from /get/teams")

        # Step 2 — get group standings
        groups_data = get_json("/get/groups")
        groups_list = groups_data if isinstance(groups_data, list) else groups_data.get("groups", groups_data.get("data", []))

        groups = []
        for grp in groups_list:
            letter = str(grp.get("group", "?")).strip().upper()
            teams = []
            for t in grp.get("teams", []):
                tid = str(t.get("team_id", t.get("id", "")))
                name = id_to_name.get(tid) or (t.get("name_en") or t.get("name") or "Unknown").strip()
                w   = int(t.get("w",  t.get("wins",   0)))
                d   = int(t.get("d",  t.get("draws",  0)))
                l   = int(t.get("l",  t.get("losses", 0)))
                gf  = int(t.get("gf", t.get("goals_for",    0)))
                ga  = int(t.get("ga", t.get("goals_against", 0)))
                pts = int(t.get("pts", t.get("points", w*3+d)))
                teams.append({"name":name,"pts":pts,"w":w,"d":d,"l":l,
                              "gf":gf,"ga":ga,"gd":gf-ga,"played":w+d+l})
            teams.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
            groups.append({"group": letter, "teams": teams})

        groups.sort(key=lambda x: x["group"])
        print(f"Built {len(groups)} groups with live data")
        return groups

    except Exception as e:
        print(f"Live fetch failed: {e} — falling back to existing index.html data")
        return read_from_html()

def read_from_html():
    with open("index.html", "r") as f:
        html = f.read()
    m = re.search(r"const GROUPS_DATA = (\[.*?\]);", html, re.DOTALL)
    if m:
        print("Loaded fallback data from index.html")
        return json.loads(m.group(1))
    raise RuntimeError("Could not parse existing index.html data")

def build_html(groups):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    with open("index.html", "r") as f:
        html = f.read()

    # Use plain string split/join instead of re.sub to avoid unicode escape issues
    # Replace timestamp
    start_ts = 'const UPDATED = "'
    end_ts   = '";'
    i = html.index(start_ts)
    j = html.index(end_ts, i) + len(end_ts)
    html = html[:i] + f'{start_ts}{updated}"{end_ts[1:]}' + html[j:]

    # Replace groups data — find the block between the marker comments
    data_str = json.dumps(groups, separators=(',', ':'), ensure_ascii=True)
    start_marker = "const GROUPS_DATA = "
    end_marker   = ";"
    i = html.index(start_marker)
    # find the closing ; after the opening [
    bracket_start = html.index("[", i)
    depth = 0
    pos = bracket_start
    while pos < len(html):
        if html[pos] == "[": depth += 1
        elif html[pos] == "]": depth -= 1
        if depth == 0:
            break
        pos += 1
    j = pos + 1  # character after closing ]
    html = html[:i] + start_marker + data_str + html[j:]

    with open("index.html", "w") as f:
        f.write(html)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    groups = fetch_groups()
    build_html(groups)
