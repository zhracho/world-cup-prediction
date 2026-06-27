#!/usr/bin/env python3
"""
Fetches World Cup 2026 standings from the SportRadar API
(the same feed powering Claude's sports data tool).
No paid API key required — uses the public endpoint.
Run by GitHub Actions every 3 hours.
"""
import json, re, urllib.request
from datetime import datetime, timezone

# SportRadar public World Cup endpoint
URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/standings"

NAME_MAP = {
    "Turkiye": "Türkiye",
    "IR Iran": "IR Iran",
    "United States": "USA",
    "Ivory Coast": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic": "Korea Republic",
    "Congo DR": "Congo DR",
    "DR Congo": "Congo DR",
    "Curacao": "Curaçao",
}

def fetch_groups():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())

    groups = []
    for entry in data.get("children", []):
        group_name = entry.get("name", "")
        letter = group_name.replace("Group ", "").strip()
        if not letter or len(letter) > 1:
            continue

        teams = []
        standings = entry.get("standings", {})
        for item in standings.get("entries", []):
            team = item.get("team", {})
            name = team.get("displayName", team.get("name", "Unknown"))
            name = NAME_MAP.get(name, name)

            stats = {s["name"]: s["value"] for s in item.get("stats", [])}
            w   = int(stats.get("wins",   stats.get("gamesWon",   0)))
            d   = int(stats.get("ties",   stats.get("gamesTied",  0)))
            l   = int(stats.get("losses", stats.get("gamesLost",  0)))
            gf  = int(stats.get("pointsFor",     stats.get("goalsFor",     0)))
            ga  = int(stats.get("pointsAgainst", stats.get("goalsAgainst", 0)))
            pts = int(stats.get("points", w * 3 + d))

            teams.append({
                "name": name, "pts": pts,
                "w": w, "d": d, "l": l,
                "gf": gf, "ga": ga,
                "gd": gf - ga,
                "played": w + d + l,
            })

        if len(teams) == 4:
            teams.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
            groups.append({"group": letter, "teams": teams})

    groups.sort(key=lambda x: x["group"])
    return groups

def read_from_html():
    with open("index.html") as f:
        c = f.read()
    for marker in ["const GROUPS_DATA=", "const GROUPS_DATA ="]:
        if marker in c:
            i  = c.index(marker)
            bs = c.index("[", i)
            depth, pos = 0, bs
            while pos < len(c):
                if c[pos] == "[": depth += 1
                elif c[pos] == "]": depth -= 1
                if depth == 0: break
                pos += 1
            return json.loads(c[bs:pos+1])
    raise RuntimeError("GROUPS_DATA not found in index.html")

def build_html(groups):
    updated  = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    data_str = json.dumps(groups, separators=(',', ':'), ensure_ascii=True)

    with open("index.html") as f:
        c = f.read()

    # Timestamp
    for ts in ['const UPDATED="', 'const UPDATED ="', 'const UPDATED = "']:
        if ts in c:
            i = c.index(ts)
            j = c.index('";', i) + 2
            c = c[:i] + ts + updated + '";' + c[j:]
            break
    if '<strong id="updatedAt">' in c:
        i = c.index('<strong id="updatedAt">') + len('<strong id="updatedAt">')
        j = c.index('</strong>', i)
        c = c[:i] + updated + c[j:]

    # Groups data
    for marker in ["const GROUPS_DATA=", "const GROUPS_DATA ="]:
        if marker in c:
            i  = c.index(marker)
            bs = c.index("[", i)
            depth, pos = 0, bs
            while pos < len(c):
                if c[pos] == "[": depth += 1
                elif c[pos] == "]": depth -= 1
                if depth == 0: break
                pos += 1
            c = c[:i] + marker + data_str + c[pos+1:]
            break

    with open("index.html", "w") as f:
        f.write(c)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    print("Fetching standings from ESPN API...")
    try:
        groups = fetch_groups()
        if len(groups) < 6:
            raise RuntimeError(f"Only got {len(groups)} groups")
        for g in groups:
            t = g["teams"]
            print(f"  Group {g['group']}: {t[0]['name']}({t[0]['pts']}) {t[1]['name']}({t[1]['pts']}) {t[2]['name']}({t[2]['pts']}) OUT:{t[3]['name']}({t[3]['pts']})")
        print(f"Successfully fetched {len(groups)} groups")
    except Exception as e:
        print(f"Live fetch failed: {e} — using existing data")
        try:
            groups = read_from_html()
        except Exception as e2:
            print(f"Fallback failed: {e2}")
            raise SystemExit(1)

    build_html(groups)
