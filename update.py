#!/usr/bin/env python3
"""
Fetches live World Cup 2026 standings from worldcup26.ir
and injects them into index.html. Run by GitHub Actions every 3 hours.
"""
import json, re, urllib.request
from datetime import datetime, timezone

FLAGS = {
    "Mexico":"🇲🇽","South Africa":"🇿🇦","Korea Republic":"🇰🇷","Czechia":"🇨🇿",
    "Czech Republic":"🇨🇿","Switzerland":"🇨🇭","Canada":"🇨🇦",
    "Bosnia and Herzegovina":"🇧🇦","Qatar":"🇶🇦","Brazil":"🇧🇷","Morocco":"🇲🇦",
    "Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Haiti":"🇭🇹","USA":"🇺🇸","United States":"🇺🇸",
    "Australia":"🇦🇺","Paraguay":"🇵🇾","Türkiye":"🇹🇷","Turkey":"🇹🇷",
    "Germany":"🇩🇪","Ivory Coast":"🇨🇮","Côte d'Ivoire":"🇨🇮","Ecuador":"🇪🇨",
    "Curaçao":"🇨🇼","Netherlands":"🇳🇱","Japan":"🇯🇵","Sweden":"🇸🇪",
    "Tunisia":"🇹🇳","Egypt":"🇪🇬","Iran":"🇮🇷","IR Iran":"🇮🇷","Belgium":"🇧🇪",
    "New Zealand":"🇳🇿","Spain":"🇪🇸","Uruguay":"🇺🇾","Cape Verde":"🇨🇻",
    "Saudi Arabia":"🇸🇦","France":"🇫🇷","Norway":"🇳🇴","Senegal":"🇸🇳",
    "Iraq":"🇮🇶","Argentina":"🇦🇷","Austria":"🇦🇹","Algeria":"🇩🇿","Jordan":"🇯🇴",
    "Colombia":"🇨🇴","Portugal":"🇵🇹","Congo DR":"🇨🇩","DR Congo":"🇨🇩",
    "Uzbekistan":"🇺🇿","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Ghana":"🇬🇭","Croatia":"🇭🇷","Panama":"🇵🇦",
}

BASE_STR = {
    "Argentina":92,"France":91,"Spain":89,"Brazil":88,"England":86,"Germany":85,
    "Netherlands":84,"Portugal":83,"Colombia":82,"Mexico":81,"Morocco":80,"Norway":79,
    "Uruguay":78,"Belgium":77,"Switzerland":76,"USA":75,"United States":75,"Japan":74,
    "Australia":73,"Ivory Coast":72,"Côte d'Ivoire":72,"Egypt":71,"Ecuador":70,
    "Sweden":69,"Canada":68,"Croatia":67,"Czech Republic":65,"Czechia":65,
    "Türkiye":66,"Turkey":66,"South Africa":64,"Algeria":63,"Ghana":63,
    "Korea Republic":62,"Austria":62,"Bosnia and Herzegovina":61,"Iran":58,"IR Iran":58,
    "Scotland":60,"Paraguay":59,"Senegal":64,"Tunisia":55,"New Zealand":50,
    "Saudi Arabia":54,"Cape Verde":52,"Iraq":51,"Jordan":48,"Congo DR":49,
    "DR Congo":49,"Uzbekistan":46,"Qatar":44,"Curaçao":42,"Haiti":40,
}

def fetch_groups():
    """Try the live API; fall back to reading current index.html data."""
    try:
        req = urllib.request.Request(
            "https://worldcup26.ir/get/groups",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        print("Fetched live data from worldcup26.ir")
        return parse_live(data)
    except Exception as e:
        print(f"Live fetch failed ({e}), reading from existing index.html")
        return read_from_html()

def parse_live(data):
    """Parse worldcup26.ir /get/groups response."""
    groups = []
    items = data if isinstance(data, list) else data.get("groups", data.get("data", []))
    for grp in items:
        letter = grp.get("group", "?")
        teams = []
        for t in grp.get("teams", []):
            w   = int(t.get("w", t.get("wins", 0)))
            d   = int(t.get("d", t.get("draws", 0)))
            l   = int(t.get("l", t.get("losses", 0)))
            gf  = int(t.get("gf", t.get("goals_for", 0)))
            ga  = int(t.get("ga", t.get("goals_against", 0)))
            pts = int(t.get("pts", t.get("points", w*3+d)))
            name = (t.get("name_en") or t.get("name") or "Unknown").strip()
            teams.append({"name":name,"pts":pts,"w":w,"d":d,"l":l,
                          "gf":gf,"ga":ga,"gd":gf-ga,"played":w+d+l})
        teams.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
        groups.append({"group": letter, "teams": teams})
    groups.sort(key=lambda x: x["group"])
    return groups

def read_from_html():
    """Extract GROUPS_DATA from the existing index.html as fallback."""
    with open("index.html", "r") as f:
        html = f.read()
    m = re.search(r"const GROUPS_DATA = (\[.*?\]);", html, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise RuntimeError("Could not parse existing index.html data")

def build_html(groups):
    updated = datetime.now(timezone.utc).strftime("%-d %b %Y, %H:%M UTC")
    with open("index.html", "r") as f:
        html = f.read()

    # Replace both the data block and the timestamp
    html = re.sub(
        r"const UPDATED = \".*?\";",
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
