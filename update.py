#!/usr/bin/env python3
"""
Scrapes live World Cup 2026 group standings from Wikipedia.
No API key required. Run by GitHub Actions every 3 hours.
"""
import json, re, urllib.request, html as html_lib
from datetime import datetime, timezone

GROUPS = list("ABCDEFGHIJKL")

NAME_MAP = {
    "Czech Republic": "Czechia",
    "South Korea": "Korea Republic",
    "Iran": "IR Iran",
    "Turkey": "Türkiye",
    "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "United States": "USA",
}

def fetch_page(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; WorldCupBot/1.0)"
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def clean_cell(c):
    c = re.sub(r'<[^>]+>', '', c)        # strip all HTML tags
    c = html_lib.unescape(c)             # decode &amp; etc
    c = re.sub(r'\[.*?\]', '', c)        # strip footnotes [a], [b]
    c = re.sub(r'\(.*?\)', '', c)        # strip annotations (H, A), (E)
    c = c.replace('\xa0', ' ').strip()
    return c

def parse_group(page_html, group_letter):
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>',
        page_html, re.DOTALL | re.IGNORECASE
    )
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL | re.IGNORECASE)
        teams = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            if len(cells) < 10:
                continue
            vals = [clean_cell(c) for c in cells]
            try:
                pos  = int(vals[0])
                name = vals[1].strip()
                pld  = int(vals[2])
                w    = int(vals[3])
                d    = int(vals[4])
                l    = int(vals[5])
                gf   = int(vals[6])
                ga   = int(vals[7])
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
            url  = f"https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{g}"
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

def inject_into_html(groups):
    updated  = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    data_str = json.dumps(groups, separators=(',', ':'), ensure_ascii=True)

    with open("index.html", "r") as f:
        content = f.read()

    # --- Replace UPDATED timestamp ---
    # Try both spacing variants of the JS const
    for ts_marker in ['const UPDATED="', 'const UPDATED ="', 'const UPDATED = "']:
        if ts_marker in content:
            i = content.index(ts_marker)
            j = content.index('";', i) + 2
            content = content[:i] + ts_marker + updated + '";' + content[j:]
            break
    # Also update the visible HTML span if present
    span_marker = '<strong id="updatedAt">'
    if span_marker in content:
        i = content.index(span_marker) + len(span_marker)
        j = content.index('</strong>', i)
        content = content[:i] + updated + content[j:]

    # --- Replace GROUPS_DATA ---
    # Search loosely (handles "const GROUPS_DATA=" and "const GROUPS_DATA = ")
    gd_match = None
    for variant in ["const GROUPS_DATA=", "const GROUPS_DATA ="]:
        if variant in content:
            gd_match = variant
            break
    if not gd_match:
        raise RuntimeError("const GROUPS_DATA marker not found in index.html")
    i  = content.index(gd_match)
    bs = content.index("[", i)
    depth, pos = 0, bs
    while pos < len(content):
        if   content[pos] == "[": depth += 1
        elif content[pos] == "]": depth -= 1
        if depth == 0: break
        pos += 1
    # Preserve original spacing style
    content = content[:i] + gd_match + data_str + content[pos + 1:]

    with open("index.html", "w") as f:
        f.write(content)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    print("Fetching group standings from Wikipedia...")
    groups = fetch_all_groups()

    if len(groups) < 6:
        print(f"Only got {len(groups)} groups — aborting to avoid overwriting good data")
        raise SystemExit(1)

    print(f"Successfully fetched {len(groups)} groups")
    inject_into_html(groups)
