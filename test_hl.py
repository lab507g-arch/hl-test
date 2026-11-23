import json, time, urllib.request, urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

API = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
results, S = {}, {}


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
        fn()
        results[name] = "OK"
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code}")
        results[name] = "FAIL"
    except Exception as e:
        print(f"FAIL {type(e).__name__}: {e}")
        results[name] = "FAIL"


def av(r):
    return float(r.get("accountValue", 0))


def vlm(r, window="day"):
    for w in r.get("windowPerformances", []):
        if w[0] == window:
            return float(w[1].get("vlm", 0))
    return 0.0


def state(addr):
    _, s = post({"type": "clearinghouseState", "user": addr})
    return [p["position"] for p in s.get("assetPositions", [])]


def where_am_i():
    _, d = get("https://ipinfo.io/json")
    print("country:", d.get("country"), "| org:", d.get("org"))


def leaderboard():
    status, d = get(LEADERBOARD)
    rows = d.get("leaderboardRows", d) if isinstance(d, dict) else d
    print("HTTP", status, "| rows:", len(rows))
    for t in (1e4, 1e5, 1e6):
        print(f"accountValue >= ${int(t):,}:", sum(av(r) >= t for r in rows))
    active = [r for r in rows if av(r) >= 1e4 and vlm(r) > 0]
    print("active (>= $10k and day volume > 0):", len(active))
    S["cand"] = sorted(active, key=vlm, reverse=True)
    assert S["cand"], "no candidates"


def positions():
    tried = found = with_liq = 0
    for r in S["cand"][:60]:
        tried += 1
        ps = state(r["ethAddress"])
        if not ps:
            continue
        found += 1
        a = r["ethAddress"]
        print(f"{a[:6]}...{a[-4:]} positions: {len(ps)}")
        for p in ps[:3]:
            side = "long" if float(p["szi"]) > 0 else "short"
            print("   ", p["coin"], side, "liqPx:", p.get("liquidationPx"))
        with_liq += sum(1 for p in ps if p.get("liquidationPx"))
        if found >= 5:
            break
    print(f"tried {tried} | wallets with positions {found} | positions with liqPx {with_liq}")
    assert found and with_liq, "no positions with liquidationPx found"


def rate():
    addrs = [r["ethAddress"] for r in S["cand"][60:360]]
    assert addrs, "not enough candidates"

    def one(a):
        try:
            state(a)
            return 200
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return "err"

    t = time.time()
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(one, addrs))
    dt = time.time() - t
    print(dict(Counter(codes)), f"| {len(addrs)} requests in {dt:.1f}s = {len(addrs)/dt*60:.0f}/min")
    assert Counter(codes).get(200, 0) == len(addrs), "some requests failed (see codes above)"


step("where_am_i", where_am_i)
step("leaderboard", leaderboard)
if "cand" in S:
    step("positions", positions)
    step("rate", rate)

print("\n== SUMMARY")
for k, v in results.items():
    print(f"{k}: {v}")
