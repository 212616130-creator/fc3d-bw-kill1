# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — B系统（5专家 Hedge 加权投票）
=====================================================
算法: 5个低相关固定规则专家（只预测百位）→ 近 WIN 期命中率加权投票。
与 A系统（800专家池，样本内极限）并列，B系统追求无选择偏差的真实稳健。

五个专家（全部只用历史数据 ≤ 上期）:
  E1 A9       : (9 - 上期百位) % 10              → 百位反码
  E2 h1s3     : (上期百位 + 上期跨度 + 3) % 10    → 百位+跨度  （原冠军）
  E3 freq_all : 全史出现次数最少的百位数字         → 全史冷号
  E4 freq50   : 近50期出现次数最少的百位数字       → 短窗冷号
  E5 trans1   : 一阶百位转移概率表中概率最低的百位  → 马尔可夫

命中 = 杀码 != 当期百位；基线 = 90%。
严格 walk-forward：第 i 期只用第 i-1 期及之前数据，无未来泄漏。
"""
import csv
import json
import os
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE, 'data', 'fc3d-history.csv')
OUT = os.path.join(BASE, 'cache', 'engineB.json')
WARM = 250
WIN = 150        # 权重评估窗口
SMOOTH = 0.02    # 权重下限

EXPERT_KEYS = ['A9', 'h1s3', 'freq_all', 'freq50', 'trans1']


def load():
    rows = []
    with open(CSV, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                b, s, g = int(r["hundreds"]), int(r["tens"]), int(r["ones"])
                rows.append({"issue": r["issue"], "b": b, "s": s, "g": g})
            except Exception:
                continue
    return rows


def _span(b, s, g):
    return max(b, s, g) - min(b, s, g)


# ========== 专家杀码预计算 (全部只用历史) ==========
def compute_expert_kills(rows):
    T = len(rows)
    b_arr = [r["b"] for r in rows]
    s_arr = [r["s"] for r in rows]
    g_arr = [r["g"] for r in rows]

    kills = {e: [0] * T for e in EXPERT_KEYS}

    # 简单公式
    for i in range(WARM, T):
        kills['A9'][i] = (9 - b_arr[i - 1]) % 10
        kills['h1s3'][i] = (b_arr[i - 1] + _span(b_arr[i - 1], s_arr[i - 1], g_arr[i - 1]) + 3) % 10

    # 频率类: freq_all(全史), freq50(近50) —— 统计到 i-1
    for e, win in (('freq_all', 0), ('freq50', 50)):
        cnt = Counter()
        for i in range(T):
            if i >= WARM:
                if win == 0:
                    cnt[b_arr[i - 1]] += 1
                    tot = i - WARM
                else:
                    lo = max(WARM, i - win)
                    cnt = Counter(b_arr[lo:i])
                    tot = i - lo
                if tot > 0:
                    kills[e][i] = min(range(10), key=lambda t: cnt.get(t, 0))
                else:
                    kills[e][i] = (b_arr[i - 1] + _span(b_arr[i - 1], s_arr[i - 1], g_arr[i - 1]) + 3) % 10

    # trans1: 一阶百位转移概率表 (滚动近300期, 拉普拉斯平滑0.1)
    for i in range(WARM, T):
        lo = max(WARM, i - 300)
        tab = defaultdict(lambda: [0.1] * 10)
        for j in range(lo + 1, i):
            tab[b_arr[j - 1]][b_arr[j]] += 1
        p = tab[b_arr[i - 1]]
        s = sum(p)
        kills['trans1'][i] = min(range(10), key=lambda t: p[t]) if s > 0 else (
            (b_arr[i - 1] + _span(b_arr[i - 1], s_arr[i - 1], g_arr[i - 1]) + 3) % 10)

    return kills, b_arr, s_arr, g_arr


def expert_kill_at(e, i, b_arr, s_arr, g_arr):
    """对任意 i (可为 T, 即预测下一期) 计算专家 e 的杀码, 只用 <=i-1 数据"""
    def h1s3():
        return (b_arr[i - 1] + _span(b_arr[i - 1], s_arr[i - 1], g_arr[i - 1]) + 3) % 10

    if e == 'A9':
        return (9 - b_arr[i - 1]) % 10
    if e == 'h1s3':
        return h1s3()
    if e == 'freq_all':
        cnt = Counter(b_arr[WARM:i])
        if i - WARM <= 0:
            return h1s3()
        return min(range(10), key=lambda t: cnt.get(t, 0))
    if e == 'freq50':
        lo = max(WARM, i - 50)
        cnt = Counter(b_arr[lo:i])
        if i - lo <= 0:
            return h1s3()
        return min(range(10), key=lambda t: cnt.get(t, 0))
    if e == 'trans1':
        lo = max(WARM, i - 300)
        tab = defaultdict(lambda: [0.1] * 10)
        for j in range(lo + 1, i):
            tab[b_arr[j - 1]][b_arr[j]] += 1
        p = tab[b_arr[i - 1]]
        s = sum(p)
        if s <= 0:
            return h1s3()
        return min(range(10), key=lambda t: p[t])
    return 0


def build_hedge_vote_fn(kills, b_arr, s_arr, g_arr, T):
    """返回 fn(i) → (kill, votes10)。i ∈ [WARM, T]，i=T 表示预测下一期。"""
    def fn(i):
        lo = max(WARM, i - WIN)
        if i - lo >= 10:
            ws = {}
            for e in EXPERT_KEYS:
                h = sum(1 for j in range(lo, i) if b_arr[j] != kills[e][j])
                ws[e] = max(SMOOTH, h / (i - lo))
        else:
            ws = {e: 0.9 for e in EXPERT_KEYS}
        votes = [0.0] * 10
        for e in EXPERT_KEYS:
            if i < T:
                k = kills[e][i]
            else:
                k = expert_kill_at(e, i, b_arr, s_arr, g_arr)
            votes[k] += ws[e]
        return max(range(10), key=lambda t: votes[t]), votes
    return fn


def _top3(kill, votes):
    order = sorted(range(10), key=lambda x: -votes[x])
    return [kill] + [c for c in order if c != kill][:2]


def next_issue_calc(last):
    if not last:
        return "?"
    year = int(str(last)[:4])
    num = int(str(last)[4:])
    return f"{year}{num + 1:03d}" if num < 359 else f"{year + 1}001"


def run():
    rows = load()
    T = len(rows)
    kills, b_arr, s_arr, g_arr = compute_expert_kills(rows)
    vote_fn = build_hedge_vote_fn(kills, b_arr, s_arr, g_arr, T)

    # 对照基线 h1s3
    def h1s3_pred(i):
        return (b_arr[i - 1] + _span(b_arr[i - 1], s_arr[i - 1], g_arr[i - 1]) + 3) % 10

    # 预测下一期
    k_next, votes_next = vote_fn(T)
    next_issue = next_issue_calc(rows[-1]["issue"])

    # 多窗口命中率 (Hedge vs 基线)
    win = {}
    for W in (100, 200, 500, 1000):
        lo = max(WARM, T - W)
        n = T - lo
        hits = sum(1 for i in range(lo, T) if b_arr[i] != vote_fn(i)[0])
        hits_base = sum(1 for i in range(lo, T) if b_arr[i] != h1s3_pred(i))
        win[W] = {"n": n, "hit": hits, "pct": round(hits / n * 100, 2),
                  "base_pct": round(hits_base / n * 100, 2),
                  "diff": round((hits - hits_base) / n * 100, 2)}

    # 全量
    full_hits = sum(1 for i in range(WARM, T) if b_arr[i] != vote_fn(i)[0])
    full_base = sum(1 for i in range(WARM, T) if b_arr[i] != h1s3_pred(i))

    # 1000期回测表 (近→远) + 各专家当期杀码 + top3
    BT = 1000
    details = []
    for i in range(T - 1, max(WARM, T - BT) - 1, -1):
        k, v = vote_fn(i)
        exp = {e: kills[e][i] for e in EXPERT_KEYS}
        ok = b_arr[i] != k
        details.append({
            "issue": rows[i]["issue"],
            "num": f"{rows[i]['b']}{rows[i]['s']}{rows[i]['g']}",
            "kill": k, "hit": ok, "experts": exp,
            "top3": _top3(k, v),
            "votes": [round(float(x), 4) for x in v],
        })

    data = {
        "meta": {
            "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "total": T,
            "latest_issue": rows[-1]["issue"],
            "latest_number": f"{rows[-1]['b']}{rows[-1]['s']}{rows[-1]['g']}",
            "algorithm": "Hedge 5专家加权混合 (A9+h1s3+全史频+近50频+转移表) · 百位",
            "window": WIN,
            "full_hit": round(full_hits / (T - WARM) * 100, 2),
            "full_base": round(full_base / (T - WARM) * 100, 2),
        },
        "prediction": {
            "target_issue": next_issue,
            "last_issue": rows[-1]["issue"],
            "last_draw": f"{rows[-1]['b']}{rows[-1]['s']}{rows[-1]['g']}",
            "kill": k_next,
            "top3": _top3(k_next, votes_next),
            "votes": [round(float(x), 4) for x in votes_next],
            "experts": {e: expert_kill_at(e, T, b_arr, s_arr, g_arr) for e in EXPERT_KEYS},
        },
        "window_stats": win,
        "rows": details,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("B系统 5专家引擎 (百位杀码):")
    print(f"  算法: {data['meta']['algorithm']}")
    print(f"  权重窗 {WIN}, 平滑 {SMOOTH}")
    print(f"\n命中率 (Hedge vs 基线h1s3):")
    for W in (100, 200, 500, 1000):
        w = win[W]
        print(f"  近{W:>4}期 {w['pct']}%  (基线{w['base_pct']}%, 差{w['diff']:+.2f}pp)")
    print(f"  全量   {data['meta']['full_hit']}%  (基线{data['meta']['full_base']}%)")
    print(f"  1000期回测表: {len(details)} 行 (近→远)")
    print(f"\n预测 {next_issue} 期: 百位杀 {k_next} (Top3 {data['prediction']['top3']})")
    print(f"  专家投票: {data['prediction']['experts']}")
    print(f"已输出 {OUT}")
    return data


if __name__ == "__main__":
    run()
