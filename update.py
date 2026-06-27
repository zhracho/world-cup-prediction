#!/usr/bin/env python3
"""
Scrapes live World Cup 2026 group standings from Wikipedia.
No API key required. Run by GitHub Actions every 3 hours.

Wikipedia has a dedicated page per group, each updated within minutes
of a match finishing. We parse the standings table from each page.
"""
import json, re, urllib.request, html
from datetime import datetime, timezone

GROUPS = list("ABCDEFGHIJKL")

# Wikipedia group page URL template
def wiki_url(g):
    return f"https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{g}"

# Known team name normalisations (Wikipedia uses full official names)
NAME_MAP = {
    "Czech Republic": "Czechia",
    "South Korea": "Korea Republic",
    "Iran": "IR Iran",
    "Turkey": "Türkiye",
    "Ivory Coast": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "United States": "USA",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
}

def fetch_page(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; WorldCupBot/1.0)"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def parse_group(page_html, group_letter):
    """
    Extract standings table from Wikipedia group page.
    The standings table has class 'wikitable' and contains
    Pos, Team, Pld, W, D, L, GF, GA, GD, Pts columns.
    """
    # Find all wikitables
    tables = re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>',
                        page_html, re.DOTALL | re.IGNORECASE)

    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL | re.IGNORECASE)
        teams = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 9:
                continue
            def clean(c):
                c = re.sub(r'<[^>]+>', '', c)   # strip HTML tags
                c = html.unescape(c).strip()
                c = re.sub(r'\[.*?\]', '', c)    # strip footnotes like [a]
                c = c.replace('\xa0', ' ').strip()
                return c
            vals = [clean(c) for c in cells]
            # Expect: Pos, Team, Pld, W, D, L, GF, GA, GD, Pts
            try:
                pos  = int(vals[0])
                name = vals[1].strip()
                pld  = int(vals[2])
                w    = int(vals[3])
                d    = int(vals[4])
                l    = int(vals[5])
                gf   = int(vals[6])
                ga   = int(vals[7])
                # vals[8] is GD (may have + prefix), vals[9] is Pts
                pts  = int(vals[9])
                name = NAME_MAP.get(name, name)
                teams.append({
                    "name": name, "pts": pts, "w": w, "d": d, "l": l,
                    "gf": gf, "ga": ga, "gd": gf - ga, "played": pld
                })
            except (ValueError, IndexError):
                continue
        if len(teams) == 4:
            teams.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
            return {"group": group_letter, "teams": teams}
    return None

def fetch_all_groups():
    groups = []
    for g in GROUPS:
        try:
            url  = wiki_url(g)
            page = fetch_page(url)
            grp  = parse_group(page, g)
            if grp:
                groups.append(grp)
                t = grp["teams"]
                print(f"  Group {g}: {t[0]['name']}({t[0]['pts']}) "
                      f"{t[1]['name']}({t[1]['pts']}) "
                      f"{t[2]['name']}({t[2]['pts']}) "
                      f"{t[3]['name']}({t[3]['pts']})")
            else:
                print(f"  Group {g}: could not parse standings table")
        except Exception as e:
            print(f"  Group {g}: fetch failed — {e}")
    return groups

def read_from_html():
    """Fallback: keep whatever is currently in index.html"""
    with open("index.html", "r") as f:
        content = f.read()
    i = content.find("const GROUPS_DATA = ")
    if i == -1:
        raise RuntimeError("GROUPS_DATA marker not found in index.html")
    bracket_start = content.index("[", i)
    depth, pos = 0, bracket_start
    while pos < len(content):
        if   content[pos] == "[": depth += 1
        elif content[pos] == "]": depth -= 1
        if depth == 0: break
        pos += 1
    return json.loads(content[bracket_start:pos + 1])

def build_html(groups):
    updated  = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    data_str = json.dumps(groups, separators=(',', ':'), ensure_ascii=True)

    with open("index.html", "r") as f:
        content = f.read()

    # Replace timestamp
    ts = 'const UPDATED = "'
    i  = content.index(ts)
    j  = content.index('";', i) + 2
    content = content[:i] + f'{ts}{updated}";' + content[j:]

    # Replace groups data (bracket-depth walk avoids regex/unicode issues)
    marker = "const GROUPS_DATA = "
    i = content.index(marker)
    bs = content.index("[", i)
    depth, pos = 0, bs
    while pos < len(content):
        if   content[pos] == "[": depth += 1
        elif content[pos] == "]": depth -= 1
        if depth == 0: break
        pos += 1
    content = content[:i] + marker + data_str + content[pos + 1:]

    with open("index.html", "w") as f:
        f.write(content)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    print("Fetching group standings from Wikipedia...")
    groups = fetch_all_groups()

    if len(groups) < 6:
        print(f"Only got {len(groups)} groups — falling back to existing data")
        try:
            groups = read_from_html()
            print("Fallback succeeded")
        except Exception as e:
            print(f"Fallback failed: {e}")
            raise SystemExit(1)
    else:
        print(f"Successfully fetched {len(groups)} groups")

    build_html(groups)
