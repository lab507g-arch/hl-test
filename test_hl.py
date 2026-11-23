import json, urllib.request, urllib.error

API = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"  # from memory, may be wrong
results = {}


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read())


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


def step(name, fn):
    print(f"\n== {name}")
    try:
        out = fn()
        results[name] = "OK"
        return out
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code}")
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {e}")
    results[name] = "FAIL"


def where_am_i():
    _, d = get("https://ipinfo.io/json")
    print("country:", d.get("country"), "| org:", d.get("org"))


def all_mids():
    status, d = post({"type": "allMids"})
    print("HTTP", status, "| coins:", len(d), "| BTC:", d.get("BTC"))


def leaderboard():
    status, d = get(LEADERBOARD)
    rows = d.get("leaderboardRows", d) if isinstance(d, dict) else d
    print("HTTP", status, "| rows:", len(rows))
    return rows


def positions(rows):
    top = sorted(rows, key=lambda r: float(r.get("accountValue", 0)), reverse=True)[:5]
    for r in top:
        addr = r["ethAddress"]
        _, s = post({"type": "clearinghouseState", "user": addr})
        ps = [p["position"] for p in s.get("assetPositions", [])]
        print(f"{addr[:6]}...{addr[-4:]} positions: {len(ps)}")
        for p in ps[:3]:
            side = "long" if float(p["szi"]) > 0 else "short"
            print("   ", p["coin"], side, "liqPx:", p.get("liquidationPx"))


step("where_am_i", where_am_i)
step("allMids", all_mids)
rows = step("leaderboard", leaderboard)
if rows:
    step("clearinghouseState", lambda: positions(rows))

print("\n== SUMMARY")
for k, v in results.items():
    print(f"{k}: {v}")
