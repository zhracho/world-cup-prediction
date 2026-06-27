#!/usr/bin/env python3
"""
Fetches live World Cup 2026 standings from worldcup26.ir
and injects them into index.html. Run by GitHub Actions every 3 hours.

worldcup26.ir /get/groups returns team_id values, not names.
We fetch /get/teams first to build an id->name map, then join.
"""
import json, re, urllib.request
from datetime import datetime, timezone

BASE_URL = "https://worldcup26.ir"

BASE_STR = {
    "Argentina":92,"France":91,"Spain":89,"Brazil":88,"England":86,"Germany":85,
    "Netherlands":84,"Portugal":83,"Colombia":82,"Mexico":81,"Morocco":80,"Norway":79,
    "Uruguay":78,"Belgium":77,"Switzerland":76,"USA":75,"United States":75,"Japan":74,
    "Australia":73,"Ivory Coast":72,"Côte d'Ivoire":72,"Egypt":71,"Ecuador":70,
    "Sweden":69,"Canada":68,"Croatia":67,"Czech Republic":65,"Czechia":65,
    "Türkiye":66,"Turkey":66,"South Africa":64,"Algeria":63,"Ghana":63,
    "Korea Republic":62,"South Korea":62,"Austria":62,
    "Bosnia and Herzegovina":61,"Bosnia & Herz.":61,"Iran":58,"IR Iran":58,
    "Scotland":60,"Paraguay":59,"Senegal":64,"Tunisia":55,"New Zealand":50,
    "Saudi Arabia":54,"Cape Verde":52,"Iraq":51,"Jordan":48,"Congo DR":49,
    "DR Congo":49,"Uzbekistan":46,"Qatar":44,"Curaçao":42,"Curacao":42,"Haiti":40,
}

def get_json(path):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def fetch_groups():
    try:
        # Step 1 — get all teams to build id->name map
        teams_data = get_json("/get/teams")
        id_to_name = {}
        id_to_group = {}
        teams_list = teams_data if isinstance(teams_data, list) else teams_data.get("teams", teams_data.get("data", []))
        for t in teams_list:
            tid = str(t.get("id", t.get("team_id", "")))
            name = (t.get("name_en") or t.get("name") or "").strip()
            group = str(t.get("groups", t.get("group", ""))).strip().upper()
            if tid and name:
                id_to_name[tid] = name
                id_to_group[tid] = group

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
                gf  = int(t.get("gf", t.get("goals_for",     0)))
                ga  = int(t.get("ga", t.get("goals_against",  0)))
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

    html = re.sub(
        r'const UPDATED = ".*?";',
        f'const UPDATED = "{updated}";',
        html
    )
    html = re.sub(
        r"const GROUPS_DATA = \[.*?\];",
        f"const GROUPS_DATA = {json.dumps(groups, separators=(',',':'))};",
        html,
        flags=re.DOTALL
    )
    with open("index.html", "w") as f:
        f.write(html)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    groups = fetch_groups()
    build_html(groups)
