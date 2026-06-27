#!/usr/bin/env python3
"""
World Cup 2026 Predictor - Auto-updater
Runs every 3 hours via GitHub Actions.

1. Scrapes live standings from Wikipedia (one page per group)
2. Runs 5,000 Monte Carlo simulations
3. Propagates bracket results as rounds progress
4. Builds index.html fresh from template.html
No API keys needed.
"""
import json, re, random, urllib.request, html as html_lib, os
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────────────────────────
GROUPS = list("ABCDEFGHIJKL")

NAME_MAP = {
    "Czech Republic":"Czechia","South Korea":"Korea Republic",
    "Iran":"IR Iran","Turkey":"Türkiye","Côte d'Ivoire":"Ivory Coast",
    "DR Congo":"Congo DR","United States":"USA",
    "Bosnia and Herzegovina":"Bosnia and Herzegovina",
    "Cabo Verde":"Cape Verde",
}

BASE_ELO = {
    "Argentina":1622.6,"France":1769.1,"Spain":1565.6,"Brazil":1577.4,
    "England":1549.6,"Germany":1706.6,"Netherlands":1649.5,"Portugal":1524.0,
    "Colombia":1496.0,"Mexico":1400.0,"Morocco":1494.4,"Norway":1470.0,
    "Uruguay":1510.0,"Belgium":1503.2,"Switzerland":1476.0,"USA":1475.0,
    "Japan":1474.0,"Australia":1450.0,"Ivory Coast":1485.0,"Egypt":1471.0,
    "Ecuador":1504.5,"Sweden":1487.0,"Canada":1450.0,"Croatia":1510.0,
    "Czechia":1465.0,"Türkiye":1517.4,"South Africa":1420.0,
    "Algeria":1501.4,"Ghana":1495.9,"Korea Republic":1368.0,
    "Bosnia and Herzegovina":1430.0,"Austria":1450.0,"IR Iran":1500.9,
    "Scotland":1499.8,"Paraguay":1450.0,"Senegal":1480.0,"Tunisia":1430.0,
    "New Zealand":1380.0,"Saudi Arabia":1420.0,"Cape Verde":1390.0,
    "Iraq":1390.0,"Jordan":1380.0,"Congo DR":1390.0,"Uzbekistan":1360.0,
    "Qatar":1370.0,"Curaçao":1350.0,"Haiti":1340.0,"Panama":1380.0,
}

# ── SCRAPE ────────────────────────────────────────────────────────────────────
def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")

def clean(c):
    c = re.sub(r'<[^>]+>','',c)
    c = html_lib.unescape(c)
    c = re.sub(r'\[.*?\]','',c)
    c = re.sub(r'\(.*?\)','',c)
    return c.replace('\xa0',' ').strip()

def parse_group(html, letter):
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>',
        html, re.DOTALL|re.IGNORECASE
    )
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL|re.IGNORECASE)
        teams = []
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL|re.IGNORECASE)
            if len(cells) < 10: continue
            vals = [clean(c) for c in cells]
            try:
                name = NAME_MAP.get(vals[1].strip(), vals[1].strip())
                w,d,l = int(vals[3]),int(vals[4]),int(vals[5])
                gf,ga,pts = int(vals[6]),int(vals[7]),int(vals[9])
                teams.append({
                    "name":name,"pts":pts,"w":w,"d":d,"l":l,
                    "gf":gf,"ga":ga,"gd":gf-ga,"played":w+d+l
                })
            except (ValueError,IndexError):
                continue
        if len(teams) == 4:
            teams.sort(key=lambda x: (-x["pts"],-x["gd"],-x["gf"]))
            return {"group":letter,"teams":teams}
    return None

def fetch_groups():
    groups = []
    for g in GROUPS:
        try:
            url = f"https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{g}"
            page = fetch_page(url)
            grp = parse_group(page, g)
            if grp:
                groups.append(grp)
                t = grp["teams"]
                print(f"  Group {g}: {t[0]['name']}({t[0]['pts']}) "
                      f"{t[1]['name']}({t[1]['pts']}) "
                      f"{t[2]['name']}({t[2]['pts']}) "
                      f"{t[3]['name']}({t[3]['pts']})")
            else:
                print(f"  Group {g}: could not parse")
        except Exception as e:
            print(f"  Group {g}: error — {e}")
    return groups

# ── ELO ───────────────────────────────────────────────────────────────────────
ALIASES = {
    "Türkiye":"Turkey","IR Iran":"Iran","Czechia":"Czech Republic",
    "Bosnia and Herzegovina":"Bosnia and Herzegovina",
    "Korea Republic":"Korea Republic","Congo DR":"Cameroon",
    "Ivory Coast":"Côte d'Ivoire"
}

def get_elo(name, groups):
    base = BASE_ELO.get(name) or BASE_ELO.get(ALIASES.get(name,"")) or 1470
    for g in groups:
        for t in g["teams"]:
            if t["name"] == name:
                bonus = max(-80, min(80, (t["w"]*3+t["d"])*5+(t["gf"]-t["ga"])*3))
                return base + bonus
    return base

def win_prob(a, b, groups):
    ea, eb = get_elo(a,groups), get_elo(b,groups)
    return 1 / (1 + 10**((eb-ea)/400))

# ── MONTE CARLO ───────────────────────────────────────────────────────────────
def get_qualified(groups):
    q = []
    thirds = []
    for g in groups:
        s = sorted(g["teams"], key=lambda x: (-x["pts"],-x["gd"],-x["gf"]))
        q += [s[0]["name"], s[1]["name"]]
        e = get_elo(s[2]["name"], groups)
        thirds.append({**s[2], "group":g["group"], "_elo":e})
    thirds.sort(key=lambda x: (-x["pts"],-x["gd"],-x["gf"],-x["_elo"]))
    for t in thirds[:8]:
        q.append(t["name"])
    return list(set(q))

def monte_carlo(groups, n=5000):
    qualified = get_qualified(groups)
    wins={}; finals={}; semis={}; qf_c={}
    for _ in range(n):
        remaining = list(qualified)
        random.shuffle(remaining)
        rnd = 0
        while len(remaining) > 1:
            nxt = []
            for i in range(0, len(remaining), 2):
                if i+1 >= len(remaining):
                    nxt.append(remaining[i]); continue
                a,b = remaining[i], remaining[i+1]
                p = win_prob(a, b, groups)
                w = a if random.random() < p else b
                nxt.append(w)
                if rnd == 2:
                    qf_c[a] = qf_c.get(a,0)+1
                    qf_c[b] = qf_c.get(b,0)+1
            if len(remaining) == 4:
                for t in remaining: semis[t] = semis.get(t,0)+1
            if len(remaining) == 2:
                for t in remaining: finals[t] = finals.get(t,0)+1
            remaining = nxt; rnd += 1
        if remaining: wins[remaining[0]] = wins.get(remaining[0],0)+1
    return {
        "win_pcts":   {t:round(wins.get(t,0)/n*100,1) for t in qualified},
        "final_pcts": {t:round(finals.get(t,0)/n*100,1) for t in qualified},
        "semi_pcts":  {t:round(semis.get(t,0)/n*100,1) for t in qualified},
        "qf_pcts":    {t:round(qf_c.get(t,0)/n*100,1) for t in qualified},
    }

# ── BRACKET PROPAGATION ───────────────────────────────────────────────────────
def get_winner(match_id, smap):
    m = smap.get(match_id)
    if not m or not m.get("result"): return None
    r = m["result"]
    if r["home"] > r["away"]: return m["home"]
    if r["away"] > r["home"]: return m["away"]
    return None

def propagate_bracket(schedule):
    smap = {m["id"]: m for m in schedule}
    def fill(mid, slot, team):
        if mid in smap and smap[mid][slot] == "TBD":
            smap[mid][slot] = team
            print(f"  Bracket: M{mid} {slot} → {team}")

    # R32 → R16
    for (m1,m2,r16) in [(73,74,89),(75,76,90),(77,78,91),(79,80,92),(81,82,93),(83,84,94),(85,86,95),(87,88,96)]:
        w1 = get_winner(m1, smap)
        w2 = get_winner(m2, smap)
        if w1: fill(r16, "home", w1)
        if w2: fill(r16, "away", w2)
    # R16 → QF
    for (m1,m2,qf) in [(89,90,97),(91,92,98),(93,94,99),(95,96,100)]:
        w1 = get_winner(m1, smap)
        w2 = get_winner(m2, smap)
        if w1: fill(qf, "home", w1)
        if w2: fill(qf, "away", w2)
    # QF → SF
    for (m1,m2,sf) in [(97,98,101),(99,100,102)]:
        w1 = get_winner(m1, smap)
        w2 = get_winner(m2, smap)
        if w1: fill(sf, "home", w1)
        if w2: fill(sf, "away", w2)
    # SF → Final + 3rd place
    for sf_id, final_slot in [(101,"home"),(102,"away")]:
        w = get_winner(sf_id, smap)
        if w: fill(104, final_slot, w)
    # SF losers → 3rd place
    third_slots = ["home","away"]
    third_idx = 0
    for sf_id in [101,102]:
        m = smap.get(sf_id)
        if not m or not m.get("result"): continue
        r = m["result"]
        loser = m["away"] if r["home"] > r["away"] else m["home"]
        if third_idx < 2:
            fill(103, third_slots[third_idx], loser)
            third_idx += 1
    return list(smap.values())

def fetch_results(schedule):
    """Try to pull completed scores from Wikipedia knockout page."""
    try:
        page = fetch_page("https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage")
        smap = {m["id"]: m for m in schedule}
        # Look for score boxes: "1–0", "2–1" etc near match numbers
        # Pattern: "Match 73" then within ~500 chars a score like "2–1"
        for m in schedule:
            if m.get("result"): continue  # already have result
            pattern = rf'Match\s+{m["id"]}[^<]{{0,600}}?(\d+)\s*[–\-]\s*(\d+)'
            match = re.search(pattern, page, re.DOTALL)
            if match:
                hs, as_ = int(match.group(1)), int(match.group(2))
                m["result"] = {"home": hs, "away": as_}
                print(f"  Result: M{m['id']} {m['home']} {hs}–{as_} {m['away']}")
    except Exception as e:
        print(f"  Result fetch failed: {e}")
    return schedule

# ── BUILD HTML ────────────────────────────────────────────────────────────────
def build_html(groups, mc, schedule, elo_history, historical_elo, combo_map):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")

    with open("template.html") as f:
        html = f.read()

    html = html.replace("%%UPDATED%%", updated)
    html = html.replace("%%GROUPS_DATA%%",    json.dumps(groups,          separators=(',',':'), ensure_ascii=True))
    html = html.replace("%%HISTORICAL_ELO%%", json.dumps(historical_elo,  ensure_ascii=False))
    html = html.replace("%%COMBO_MAP%%",      json.dumps(combo_map,       ensure_ascii=False))
    html = html.replace("%%ELO_HISTORY%%",    json.dumps(elo_history,     ensure_ascii=False))
    html = html.replace("%%WIN_PCTS%%",       json.dumps(mc["win_pcts"],  ensure_ascii=True))
    html = html.replace("%%FINAL_PCTS%%",     json.dumps(mc["final_pcts"],ensure_ascii=True))
    html = html.replace("%%SEMI_PCTS%%",      json.dumps(mc["semi_pcts"], ensure_ascii=True))
    html = html.replace("%%QF_PCTS%%",        json.dumps(mc["qf_pcts"],   ensure_ascii=True))
    html = html.replace("%%SCHEDULE%%",       json.dumps(schedule,        separators=(',',':'), ensure_ascii=True))

    with open("index.html", "w") as f:
        f.write(html)
    print(f"index.html built — {updated} ({len(html):,} chars)")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Load static data files (committed to repo)
    with open("elo_history.json")  as f: elo_history   = json.load(f)
    with open("historical_elo.json") as f: historical_elo = json.load(f)
    with open("combo_map.json")    as f: combo_map     = json.load(f)
    with open("schedule.json")     as f: schedule      = json.load(f)

    print("Fetching standings from Wikipedia...")
    groups = fetch_groups()

    if len(groups) < 6:
        print(f"Only got {len(groups)} groups — aborting")
        raise SystemExit(1)

    print(f"\nRunning Monte Carlo ({len(get_qualified(groups))} qualified teams)...")
    mc = monte_carlo(groups, n=5000)
    top5 = sorted(mc["win_pcts"].items(), key=lambda x:-x[1])[:5]
    print("Top 5:", ", ".join(f"{t}({p}%)" for t,p in top5))

    print("\nChecking for new results...")
    schedule = fetch_results(schedule)
    schedule = propagate_bracket(schedule)

    # Save updated schedule back
    with open("schedule.json", "w") as f:
        json.dump(schedule, f)

    print("\nBuilding index.html...")
    build_html(groups, mc, schedule, elo_history, historical_elo, combo_map)
