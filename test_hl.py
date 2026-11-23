"""Tier sampling: how much near-price liquidation exposure sits below the $10k cutoff?"""
import json, random, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

API = "https://api.hyperliquid.xyz/info"
LEADERBOARD = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
N = 300            # wallets sampled per tier
NEAR = 0.15        # "near price" = liquidation within +-15% of mid
GAP = 0.125        # 8 requests/s = 480/min, under the 600/min limit
TIERS = [("<1k", 0, 1e3), ("1k-10k", 1e3, 1e4), ("10k-100k", 1e4, 1e5), (">=100k", 1e5, float("inf"))]

_lock, _next = threading.Lock(), [0.0]


def throttle():
    with _lock:
        now = time.time()
        t = max(now, _next[0])
        _next[0] = t + GAP
    time.sleep(max(0.0, t - now))


def post(body):
    for attempt in range(4):
        throttle()
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def av(r):
    return float(r.get("accountValue", 0))


def wallet_stats(addr, mids):
    """-> (n_positions, total_notional, near_liq_notional) or None on error"""
    try:
        s = post({"type": "clearinghouseState", "user": addr})
    except Exception:
        return None
    n = tot = near = 0.0
    for ap in s.get("assetPositions", []):
        p = ap["position"]
        n += 1
        pv = abs(float(p.get("positionValue") or 0))
        tot += pv
        lp, m = p.get("liquidationPx"), mids.get(p["coin"])
        if lp and m:
            lp, m = float(lp), float(m)
            if abs(lp - m) / m <= NEAR:
                near += pv
    return n, tot, near


def analyze(pops, samples, boot=500):
    """pops: {tier: population}; samples: {tier: [near_notional per wallet]}"""
    est = {t: pops[t] * (sum(v) / len(v)) for t, v in samples.items() if v}
    total = sum(est.values()) or 1.0
    small = [t for t, lo, hi in TIERS if hi <= 1e4 and t in est]
    missing = sum(est[t] for t in small) / total
    rnd = random.Random(1)
    bs = []
    for _ in range(boot):
        e = {t: pops[t] * (sum(rs) / len(rs))
             for t, v in samples.items() if v for rs in [[rnd.choice(v) for _ in v]]}
        tt = sum(e.values()) or 1.0
        bs.append(sum(e[t] for t in small) / tt)
    bs.sort()
    return est, total, missing, bs[int(0.05 * boot)], bs[int(0.95 * boot)]


def main():
    random.seed(7)
    mids = post({"type": "allMids"})
    d = get(LEADERBOARD)
    rows = d.get("leaderboardRows", d) if isinstance(d, dict) else d
    print("leaderboard rows:", len(rows), "| BTC mid:", mids.get("BTC"))
    pops, picked = {}, {}
    for name, lo, hi in TIERS:
        tier_rows = [r for r in rows if lo <= av(r) < hi]
        pops[name] = len(tier_rows)
        picked[name] = random.sample(tier_rows, min(N, len(tier_rows)))
    jobs = [(name, r["ethAddress"]) for name, rs in picked.items() for r in rs]
    print(f"querying {len(jobs)} wallets at ~{int(60 / GAP)}/min ...")
    with ThreadPoolExecutor(8) as ex:
        out = list(ex.map(lambda j: wallet_stats(j[1], mids), jobs))
    errors = sum(o is None for o in out)
    samples = {name: [] for name in pops}
    withpos = {name: 0 for name in pops}
    for (name, _), o in zip(jobs, out):
        if o is None:
            continue
        samples[name].append(o[2])
        withpos[name] += o[0] > 0
    est, total, missing, lo, hi = analyze(pops, samples)
    print(f"\nerrors: {errors}/{len(jobs)}  (near = liquidation within +-{int(NEAR * 100)}% of price)")
    print(f"{'tier':<10}{'wallets':>8}{'sample':>7}{'w/pos%':>8}{'avg near $':>12}{'est near $M':>13}{'share%':>8}")
    for name, _, _ in TIERS:
        v = samples[name]
        if not v:
            continue
        print(f"{name:<10}{pops[name]:>8}{len(v):>7}{100 * withpos[name] / len(v):>8.0f}"
              f"{sum(v) / len(v):>12,.0f}{est[name] / 1e6:>13,.1f}{100 * est[name] / total:>8.1f}")
    print(f"\nmissed by a $10k cutoff: {100 * missing:.1f}%  (rough 90% range {100 * lo:.1f}% - {100 * hi:.1f}%)")
    assert errors < 0.05 * len(jobs), "too many failed requests"


if __name__ == "__main__":
    main()
