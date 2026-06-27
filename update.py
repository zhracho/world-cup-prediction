#!/usr/bin/env python3
"""
1. Scrapes live World Cup 2026 standings from Wikipedia
2. Calls Anthropic API to generate analysis for every qualified team
3. Bakes everything into index.html
Run by GitHub Actions every 3 hours.

Requires env var: ANTHROPIC_API_KEY
"""
import json, re, urllib.request, html as html_lib
from datetime import datetime, timezone

GROUPS = list("ABCDEFGHIJKL")

NAME_MAP = {
    "Czech Republic": "Czechia", "South Korea": "Korea Republic",
    "Iran": "IR Iran", "Turkey": "Türkiye", "Côte d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR", "United States": "USA",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
}

# ── SCRAPE WIKIPEDIA ─────────────────────────────────────────────────────────
def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def clean_cell(c):
    c = re.sub(r'<[^>]+>', '', c)
    c = html_lib.unescape(c)
    c = re.sub(r'\[.*?\]', '', c)
    c = re.sub(r'\(.*?\)', '', c)
    return c.replace('\xa0', ' ').strip()

def parse_group(page_html, letter):
    tables = re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>', page_html, re.DOTALL|re.IGNORECASE)
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL|re.IGNORECASE)
        teams = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL|re.IGNORECASE)
            if len(cells) < 10: continue
            vals = [clean_cell(c) for c in cells]
            try:
                name = NAME_MAP.get(vals[1].strip(), vals[1].strip())
                w,d,l = int(vals[3]),int(vals[4]),int(vals[5])
                gf,ga,pts = int(vals[6]),int(vals[7]),int(vals[9])
                teams.append({"name":name,"pts":pts,"w":w,"d":d,"l":l,"gf":gf,"ga":ga,"gd":gf-ga,"played":w+d+l})
            except (ValueError, IndexError):
                continue
        if len(teams) == 4:
            teams.sort(key=lambda x: (-x["pts"],-x["gd"],-x["gf"]))
            return {"group": letter, "teams": teams}
    return None

def fetch_groups():
    groups = []
    for g in GROUPS:
        try:
            page = fetch_page(f"https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{g}")
            grp = parse_group(page, g)
            if grp:
                groups.append(grp)
                t = grp["teams"]
                print(f"  Group {g}: {t[0]['name']}({t[0]['pts']}) {t[1]['name']}({t[1]['pts']}) {t[2]['name']}({t[2]['pts']}) {t[3]['name']}({t[3]['pts']})")
        except Exception as e:
            print(f"  Group {g}: failed — {e}")
    return groups

# ── ELO ENGINE ───────────────────────────────────────────────────────────────
BASE_ELO = {
    "Argentina":1622.6,"France":1769.1,"Spain":1565.6,"Brazil":1577.4,
    "England":1549.6,"Germany":1706.6,"Netherlands":1649.5,"Portugal":1524.0,
    "Colombia":1496.0,"Mexico":1400.0,"Morocco":1494.4,"Norway":1470.0,
    "Uruguay":1510.0,"Belgium":1503.2,"Switzerland":1476.0,"USA":1475.0,
    "Japan":1474.0,"Australia":1450.0,"Ivory Coast":1485.0,"Egypt":1471.0,
    "Ecuador":1504.5,"Sweden":1487.0,"Canada":1450.0,"Croatia":1510.0,
    "Czechia":1465.0,"Czech Republic":1465.0,"Türkiye":1517.4,"Turkey":1517.4,
    "South Africa":1420.0,"Algeria":1501.4,"Ghana":1495.9,"Korea Republic":1368.0,
    "Bosnia and Herzegovina":1430.0,"Austria":1450.0,"IR Iran":1500.9,"Iran":1500.9,
    "Scotland":1499.8,"Paraguay":1450.0,"Senegal":1480.0,"Tunisia":1430.0,
    "New Zealand":1380.0,"Saudi Arabia":1420.0,"Cape Verde":1390.0,"Iraq":1390.0,
    "Jordan":1380.0,"Congo DR":1390.0,"Uzbekistan":1360.0,"Qatar":1370.0,
    "Curaçao":1350.0,"Haiti":1340.0,"Panama":1380.0,
}
ALIASES = {"Türkiye":"Turkey","IR Iran":"Iran","Czechia":"Czech Republic",
           "Bosnia and Herzegovina":"Bosnia and Herzegovina","Korea Republic":"Korea Republic",
           "Congo DR":"Cameroon","Ivory Coast":"Côte d'Ivoire"}

def get_elo(name, groups):
    base = BASE_ELO.get(name) or BASE_ELO.get(ALIASES.get(name,"")) or 1470
    for g in groups:
        for t in g["teams"]:
            if t["name"] == name:
                bonus = max(-80, min(80, (t["w"]*3+t["d"])*5 + (t["gf"]-t["ga"])*3))
                return round(base + bonus, 1)
    return base

def win_prob(a, b, groups):
    ea, eb = get_elo(a, groups), get_elo(b, groups)
    return 1 / (1 + 10**((eb-ea)/400))

# ── GET QUALIFIED TEAMS ───────────────────────────────────────────────────────
def get_qualified(groups):
    """Returns list of team names that have qualified for R32"""
    qualified = []
    thirds = []
    for g in groups:
        s = sorted(g["teams"], key=lambda x: (-x["pts"],-x["gd"],-x["gf"]))
        if len(s) >= 2:
            if s[0]["played"] >= 3: qualified.append(s[0]["name"])
            if s[1]["played"] >= 3: qualified.append(s[1]["name"])
        if len(s) >= 3:
            thirds.append({**s[2], "group": g["group"]})

    thirds.sort(key=lambda x: (-x["pts"],-x["gd"],-x["gf"]))
    for t in thirds[:8]:
        qualified.append(t["name"])
    return list(set(qualified))

# ── MONTE CARLO ───────────────────────────────────────────────────────────────
def monte_carlo(groups, n=5000):
    """Run n tournament simulations, return win% for each team"""
    import random
    qualified = get_qualified(groups)
    if len(qualified) < 4:
        return {}

    wins = {t: 0 for t in qualified}

    for _ in range(n):
        remaining = list(qualified)
        random.shuffle(remaining)
        while len(remaining) > 1:
            next_round = []
            for i in range(0, len(remaining), 2):
                if i+1 >= len(remaining):
                    next_round.append(remaining[i])
                    continue
                a, b = remaining[i], remaining[i+1]
                p = win_prob(a, b, groups)
                winner = a if random.random() < p else b
                next_round.append(winner)
            remaining = next_round

        if remaining:
            wins[remaining[0]] = wins.get(remaining[0], 0) + 1

    return {t: round(wins[t]/n*100, 1) for t in wins}

def generate_all_analyses(groups, win_pcts):
    """Generate stat-based analysis for each team — no API needed"""
    analyses = {}
    for g in groups:
        for t in g["teams"]:
            name = t["name"]
            pct = win_pcts.get(name, 0)
            elo = get_elo(name, groups)
            gd = t["gf"] - t["ga"]
            form = "strong" if t["w"] >= 2 else ("inconsistent" if t["d"] >= 2 else "poor")
            analyses[name] = (
                f"Group stage form: {t['w']}W {t['d']}D {t['l']}L, "
                f"{t['gf']} goals scored, {t['ga']} conceded (GD {'+' if gd>=0 else ''}{gd}). "
                f"ELO rating {elo} — {form} form heading into the knockout rounds. "
                f"Win probability across 5,000 simulations: {pct}%."
            )
    return analyses

# ── INJECT INTO HTML ──────────────────────────────────────────────────────────
def inject(groups, win_pcts, analyses):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")

    with open("index.html") as f:
        content = f.read()

    def replace_marker(c, marker, value):
        for variant in [marker+"=", marker+" =", marker + " = "]:
            if variant in c:
                i = c.index(variant)
                # Find end of value (next ; at depth 0)
                start = c.index(variant[len(marker):].lstrip().lstrip("=").lstrip(), i+len(marker))
                # Find matching close for arrays/objects, or closing ; for strings
                first_char = c[start:].lstrip()[0]
                if first_char in '[{':
                    actual_start = c.index(first_char, i)
                    depth, pos = 0, actual_start
                    open_c, close_c = first_char, ']' if first_char=='[' else '}'
                    while pos < len(c):
                        if c[pos]==open_c: depth+=1
                        elif c[pos]==close_c: depth-=1
                        if depth==0: break
                        pos+=1
                    c = c[:i] + variant + value + c[pos+1:]
                elif first_char == '"':
                    actual_start = c.index('"', i+len(variant))
                    end = c.index('";', actual_start+1)
                    c = c[:i] + variant + value + c[end+1:]
                return c
        return c

    # Replace timestamp in JS and HTML
    for ts in ['const UPDATED="', 'const UPDATED ="', 'const UPDATED = "']:
        if ts in content:
            i = content.index(ts)
            j = content.index('";', i) + 2
            content = content[:i] + ts + updated + '";' + content[j:]
            break
    if '<strong id="updatedAt">' in content:
        i = content.index('<strong id="updatedAt">') + len('<strong id="updatedAt">')
        j = content.index('</strong>', i)
        content = content[:i] + updated + content[j:]

    # Replace GROUPS_DATA
    data_str = json.dumps(groups, separators=(',',':'), ensure_ascii=True)
    for marker in ["const GROUPS_DATA=", "const GROUPS_DATA ="]:
        if marker in content:
            i = content.index(marker)
            bs = content.index("[", i)
            depth, pos = 0, bs
            while pos < len(content):
                if content[pos]=="[": depth+=1
                elif content[pos]=="]": depth-=1
                if depth==0: break
                pos+=1
            content = content[:i] + marker + data_str + content[pos+1:]
            break

    # Replace WIN_PCTS
    wp_str = json.dumps(win_pcts, ensure_ascii=True)
    for marker in ["const WIN_PCTS=", "const WIN_PCTS ="]:
        if marker in content:
            i = content.index(marker)
            bs = content.index("{", i)
            depth, pos = 0, bs
            while pos < len(content):
                if content[pos]=="{": depth+=1
                elif content[pos]=="}": depth-=1
                if depth==0: break
                pos+=1
            content = content[:i] + marker + wp_str + content[pos+1:]
            break

    # Replace ANALYSES
    an_str = json.dumps(analyses, ensure_ascii=False)
    for marker in ["const ANALYSES=", "const ANALYSES ="]:
        if marker in content:
            i = content.index(marker)
            bs = content.index("{", i)
            depth, pos = 0, bs
            while pos < len(content):
                if content[pos]=="{": depth+=1
                elif content[pos]=="}": depth-=1
                if depth==0: break
                pos+=1
            content = content[:i] + marker + an_str + content[pos+1:]
            break

    with open("index.html", "w") as f:
        f.write(content)
    print(f"index.html updated — {updated}")

if __name__ == "__main__":
    print("Fetching standings from Wikipedia...")
    groups = fetch_groups()

    if len(groups) < 6:
        print(f"Only got {len(groups)} groups — aborting")
        raise SystemExit(1)

    print(f"Fetched {len(groups)} groups. Running Monte Carlo...")
    win_pcts = monte_carlo(groups, n=5000)
    top5 = sorted(win_pcts.items(), key=lambda x: -x[1])[:5]
    print("Top 5:", ", ".join(f"{t}({p}%)" for t,p in top5))

    print("Generating stat-based analyses...")
    analyses = generate_all_analyses(groups, win_pcts)
    print(f"Generated {len(analyses)} analyses")

    inject(groups, win_pcts, analyses)
