#!/usr/bin/env python3
"""
1. Scrapes live WC 2026 standings from Wikipedia
2. Runs 5,000 Monte Carlo simulations
3. Generates stat-based team analyses
4. Injects everything into index.html
Run by GitHub Actions every 3 hours — no API key needed.
"""
import json, re, random, urllib.request, html as html_lib
from datetime import datetime, timezone

GROUPS_LETTERS = list("ABCDEFGHIJKL")
NAME_MAP = {
    "Czech Republic":"Czechia","South Korea":"Korea Republic",
    "Iran":"IR Iran","Turkey":"Türkiye","Côte d'Ivoire":"Ivory Coast",
    "DR Congo":"Congo DR","United States":"USA",
    "Bosnia and Herzegovina":"Bosnia and Herzegovina",
}
BASE_ELO = {
    "Argentina":1622.6,"France":1769.1,"Spain":1565.6,"Brazil":1577.4,
    "England":1549.6,"Germany":1706.6,"Netherlands":1649.5,"Portugal":1524.0,
    "Colombia":1496.0,"Mexico":1400.0,"Morocco":1494.4,"Norway":1470.0,
    "Uruguay":1510.0,"Belgium":1503.2,"Switzerland":1476.0,"USA":1475.0,
    "Japan":1474.0,"Australia":1450.0,"Ivory Coast":1485.0,"Egypt":1471.0,
    "Ecuador":1504.5,"Sweden":1487.0,"Canada":1450.0,"Croatia":1510.0,
    "Czechia":1465.0,"Türkiye":1517.4,"Turkey":1517.4,"South Africa":1420.0,
    "Algeria":1501.4,"Ghana":1495.9,"Korea Republic":1368.0,
    "Bosnia and Herzegovina":1430.0,"Austria":1450.0,"IR Iran":1500.9,
    "Scotland":1499.8,"Paraguay":1450.0,"Senegal":1480.0,"Tunisia":1430.0,
    "New Zealand":1380.0,"Saudi Arabia":1420.0,"Cape Verde":1390.0,
    "Iraq":1390.0,"Jordan":1380.0,"Congo DR":1390.0,"Uzbekistan":1360.0,
    "Qatar":1370.0,"Curaçao":1350.0,"Haiti":1340.0,"Panama":1380.0,
}
ALIASES = {"Türkiye":"Turkey","IR Iran":"Iran","Czechia":"Czech Republic",
           "Bosnia and Herzegovina":"Bosnia and Herzegovina","Korea Republic":"Korea Republic",
           "Congo DR":"Cameroon","Ivory Coast":"Côte d'Ivoire"}

def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r: return r.read().decode("utf-8")

def clean(c):
    c = re.sub(r'<[^>]+>','',c); c = html_lib.unescape(c)
    c = re.sub(r'\[.*?\]','',c); c = re.sub(r'\(.*?\)','',c)
    return c.replace('\xa0',' ').strip()

def parse_group(html, letter):
    tables = re.findall(r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>.*?</table>', html, re.DOTALL|re.IGNORECASE)
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
                teams.append({"name":name,"pts":pts,"w":w,"d":d,"l":l,"gf":gf,"ga":ga,"gd":gf-ga,"played":w+d+l})
            except (ValueError,IndexError): continue
        if len(teams)==4:
            teams.sort(key=lambda x:(-x["pts"],-x["gd"],-x["gf"]))
            return {"group":letter,"teams":teams}
    return None

def fetch_groups():
    groups = []
    for g in GROUPS_LETTERS:
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

def get_elo(name, groups):
    base = BASE_ELO.get(name) or BASE_ELO.get(ALIASES.get(name,"")) or 1470
    for g in groups:
        for t in g["teams"]:
            if t["name"]==name:
                return base + max(-80,min(80,(t["w"]*3+t["d"])*5+(t["gf"]-t["ga"])*3))
    return base

def get_qualified(groups):
    q = []
    thirds = []
    for g in groups:
        s = sorted(g["teams"],key=lambda x:(-x["pts"],-x["gd"],-x["gf"]))
        q += [s[0]["name"],s[1]["name"]]
        thirds.append({**s[2],"group":g["group"]})
    thirds.sort(key=lambda x:(-x["pts"],-x["gd"],-x["gf"]))
    for t in thirds[:8]: q.append(t["name"])
    return list(set(q))

def monte_carlo(groups, n=5000):
    qualified = get_qualified(groups)
    wins={};finals={};semis={};qf_counts={}
    for _ in range(n):
        remaining=list(qualified); random.shuffle(remaining)
        rnd=0
        while len(remaining)>1:
            nxt=[]
            for i in range(0,len(remaining),2):
                if i+1>=len(remaining): nxt.append(remaining[i]); continue
                a,b=remaining[i],remaining[i+1]
                ea,eb=get_elo(a,groups),get_elo(b,groups)
                p=1/(1+10**((eb-ea)/400))
                w=a if random.random()<p else b
                nxt.append(w)
                if rnd==2:
                    qf_counts[a]=qf_counts.get(a,0)+1
                    qf_counts[b]=qf_counts.get(b,0)+1
            if len(remaining)==4:
                for t in remaining: semis[t]=semis.get(t,0)+1
            if len(remaining)==2:
                for t in remaining: finals[t]=finals.get(t,0)+1
            remaining=nxt; rnd+=1
        if remaining: wins[remaining[0]]=wins.get(remaining[0],0)+1
    return {
        "win_pcts":  {t:round(wins.get(t,0)/n*100,1) for t in qualified},
        "final_pcts":{t:round(finals.get(t,0)/n*100,1) for t in qualified},
        "semi_pcts": {t:round(semis.get(t,0)/n*100,1) for t in qualified},
        "qf_pcts":   {t:round(qf_counts.get(t,0)/n*100,1) for t in qualified},
    }

def make_analyses(groups, mc):
    analyses={}
    for g in groups:
        for t in g["teams"]:
            name=t["name"]; pct=mc["win_pcts"].get(name,0)
            elo=round(get_elo(name,groups)); gd=t["gf"]-t["ga"]
            analyses[name]=(f"{t['w']}W {t['d']}D {t['l']}L · {t['gf']} scored · {t['ga']} conceded · "
                f"GD {'+' if gd>=0 else ''}{gd} · ELO {elo} · "
                f"Win {pct}% · Final {mc['final_pcts'].get(name,0)}% · Semi {mc['semi_pcts'].get(name,0)}%")
    return analyses

def inject(groups, mc, analyses, schedule):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    with open("index.html") as f: c = f.read()

    def replace_const(content, name, value_str):
        for variant in [f"const {name}=", f"const {name} ="]:
            if variant not in content: continue
            i = content.index(variant)
            first = content[content.index(variant)+len(variant):].lstrip()[0]
            if first in '[{':
                bs = content.index(first, i)
                depth, pos = 0, bs
                oc,cc = first,(']' if first=='[' else '}')
                while pos<len(content):
                    if content[pos]==oc: depth+=1
                    elif content[pos]==cc: depth-=1
                    if depth==0: break
                    pos+=1
                content = content[:i]+variant+value_str+content[pos+1:]
            elif first=='"':
                s=content.index('"',i+len(variant))
                e=content.index('";',s+1)
                content=content[:i]+variant+value_str+content[e+1:]
            return content
        return content

    # Timestamp
    for ts in ['const UPDATED="','const UPDATED ="','const UPDATED = "']:
        if ts in c:
            i=c.index(ts); j=c.index('";',i)+2
            c=c[:i]+ts+updated+'";'+c[j:]; break
    if '<strong id="updatedAt">' in c:
        i=c.index('<strong id="updatedAt">')+len('<strong id="updatedAt">')
        j=c.index('</strong>',i); c=c[:i]+updated+c[j:]

    c = replace_const(c, "GROUPS_DATA", json.dumps(groups,separators=(',',':'),ensure_ascii=True))
    c = replace_const(c, "WIN_PCTS",    json.dumps(mc["win_pcts"],ensure_ascii=True))
    c = replace_const(c, "FINAL_PCTS",  json.dumps(mc["final_pcts"],ensure_ascii=True))
    c = replace_const(c, "SEMI_PCTS",   json.dumps(mc["semi_pcts"],ensure_ascii=True))
    c = replace_const(c, "QF_PCTS",     json.dumps(mc["qf_pcts"],ensure_ascii=True))
    c = replace_const(c, "ANALYSES",    json.dumps(analyses,ensure_ascii=False))

    with open("index.html","w") as f: f.write(c)
    print(f"index.html updated — {updated}")

if __name__=="__main__":
    print("Fetching standings from Wikipedia...")
    groups = fetch_groups()
    if len(groups)<6: print("Too few groups — aborting"); raise SystemExit(1)
    print(f"Running Monte Carlo ({len(get_qualified(groups))} teams)...")
    mc = monte_carlo(groups, n=5000)
    top5=sorted(mc["win_pcts"].items(),key=lambda x:-x[1])[:5]
    print("Top 5:", ", ".join(f"{t}({p}%)" for t,p in top5))
    analyses = make_analyses(groups, mc)
    inject(groups, mc, analyses)

# ── SCHEDULE & RESULTS ────────────────────────────────────────────────────────

# ── BRACKET PROPAGATION ───────────────────────────────────────────────────────
# Maps R32 match winners to their R16 match slot
# Based on official FIFA bracket tree
R32_TO_R16 = {
    # (r32_match_id, r32_match_id) -> r16_match_id
    (73, 74): 89,   # W73 vs W74 -> M89
    (75, 76): 90,   # W75 vs W76 -> M90
    (77, 78): 91,   # W77 vs W78 -> M91
    (79, 80): 92,   # W79 vs W80 -> M92
    (81, 82): 93,   # W81 vs W82 -> M93
    (83, 84): 94,   # W83 vs W84 -> M94
    (85, 86): 95,   # W85 vs W86 -> M95
    (87, 88): 96,   # W87 vs W88 -> M96
}
R16_TO_QF = {
    (89, 90): 97,
    (91, 92): 98,
    (93, 94): 99,
    (95, 96): 100,
}
QF_TO_SF = {
    (97, 98): 101,
    (99, 100): 102,
}
SF_TO_FINAL = {
    (101, 102): 104,
}
SF_TO_3RD = {
    # losers of semis play 3rd place
    101: 103,
    102: 103,
}

def get_winner(match, schedule_map):
    """Return winning team name from a completed match, or None."""
    m = schedule_map.get(match['id'])
    if not m or not m.get('result'):
        return None
    r = m['result']
    if r['home'] > r['away']:
        return m['home']
    elif r['away'] > r['home']:
        return m['away']
    # Draw — shouldn't happen in knockout but handle gracefully
    return None

def propagate_bracket(schedule):
    """Fill in team names for future rounds based on completed results."""
    smap = {m['id']: m for m in schedule}

    def fill_slot(match_id, home_or_away, team_name):
        if match_id in smap and smap[match_id][home_or_away] == 'TBD':
            smap[match_id][home_or_away] = team_name
            print(f"  Bracket: M{match_id} {home_or_away} → {team_name}")

    # R32 -> R16
    slots = [
        (73, 74, 89), (75, 76, 90), (77, 78, 91), (79, 80, 92),
        (81, 82, 93), (83, 84, 94), (85, 86, 95), (87, 88, 96),
    ]
    for m1_id, m2_id, r16_id in slots:
        w1 = get_winner(smap[m1_id], smap) if m1_id in smap else None
        w2 = get_winner(smap[m2_id], smap) if m2_id in smap else None
        if w1: fill_slot(r16_id, 'home', w1)
        if w2: fill_slot(r16_id, 'away', w2)

    # R16 -> QF
    slots = [(89,90,97),(91,92,98),(93,94,99),(95,96,100)]
    for m1_id, m2_id, qf_id in slots:
        w1 = get_winner(smap[m1_id], smap) if m1_id in smap else None
        w2 = get_winner(smap[m2_id], smap) if m2_id in smap else None
        if w1: fill_slot(qf_id, 'home', w1)
        if w2: fill_slot(qf_id, 'away', w2)

    # QF -> SF
    slots = [(97,98,101),(99,100,102)]
    for m1_id, m2_id, sf_id in slots:
        w1 = get_winner(smap[m1_id], smap) if m1_id in smap else None
        w2 = get_winner(smap[m2_id], smap) if m2_id in smap else None
        if w1: fill_slot(sf_id, 'home', w1)
        if w2: fill_slot(sf_id, 'away', w2)

    # SF -> Final and 3rd place
    for sf_id, final_slot in [(101,'home'),(102,'away')]:
        winner = get_winner(smap[sf_id], smap) if sf_id in smap else None
        if winner: fill_slot(104, final_slot, winner)

    # SF losers -> 3rd place match
    for sf_id in [101, 102]:
        m = smap.get(sf_id)
        if not m or not m.get('result'): continue
        r = m['result']
        if r['home'] > r['away']:
            loser = m['away']
        elif r['away'] > r['home']:
            loser = m['home']
        else:
            continue
        existing_103 = smap.get(103, {})
        if existing_103.get('home') == 'TBD':
            fill_slot(103, 'home', loser)
        elif existing_103.get('away') == 'TBD':
            fill_slot(103, 'away', loser)

    return list(smap.values())

def fetch_results(schedule):
    """
    Try to update match results from Wikipedia knockout stage page.
    Marks completed matches with {home: X, away: Y} result dicts.
    """
    try:
        page = fetch_page("https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage")
        # Look for score patterns like "2–1", "3–0" etc next to team names
        # Simple approach: find "X – Y" patterns and map to schedule by match number
        score_pattern = re.compile(r'Match\s+(\d+).*?(\d+)\s*[–-]\s*(\d+)', re.DOTALL)
        for m in score_pattern.finditer(page):
            match_id = int(m.group(1))
            home_score = int(m.group(2))
            away_score = int(m.group(3))
            for s in schedule:
                if s['id'] == match_id and not s['result']:
                    s['result'] = {'home': home_score, 'away': away_score}
                    print(f"  Result found: M{match_id} {home_score}–{away_score}")
        return schedule
    except Exception as e:
        print(f"  Result fetch failed: {e}")
        return schedule
