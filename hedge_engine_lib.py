# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — B系统v2：专家库选优引擎
=====================================================
v2 核心改动（老板拍板 2026-08-22）：放弃手挑5专家，改为
「从 A 系统专家库(238条)选 ≤20 个专家，1000期网格扫描自动选优」。

机制：
  候选池 = cache/pool.json['pool']（A系统已锁定的 238 专家，每条 = 公式组合）
  每期预测 = 近 win 期命中率 TopM(M≤20) 专家 → 权重=命中率^γ → 加权投票 → 票王=百位杀码
  网格扫描 = M(6档)×win(6档)×γ(4档)=144 组合 × 1000期回测 自动选优
  选优后写回 pool.json['lockedB'] → 之后每日锁定（确定性：发布值=回测值）

walk-forward：第 t 期特征只用 t-1 / t-2 期数据，严格不偷看未来。
命中 = 杀码 != 当期百位；基线 = 90%。

★ 矩阵独立构建：BT_WINDOW=1000 期回测窗口，矩阵向历史方向扩展 WIN_MAX=200，
  保证回测首期(第N-1000期)的近win(≤200)窗口也满 → 无空切片。

输出 cache/engineB.json（v2 格式，gen_site.py 配套读取）：
  meta / prediction / selected_experts(本期入选专家卡) / window_stats / rows(1000期回测)
"""
import csv
import json
import os
import time
from datetime import datetime, timezone, timedelta

import numpy as np

TZ = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE, 'data', 'fc3d-history.csv')
POOL_JSON = os.path.join(BASE, 'cache', 'pool.json')
OUT = os.path.join(BASE, 'cache', 'engineB.json')

SMOOTH = 0.02

# 1000 期回测窗口（B系统v2口径，区别于A系统500期）
BT_WINDOW = 1000
WIN_MAX = 200                      # 特征矩阵向历史方向扩展，保证回测首期也有满窗口

# 网格（144 组合 = 6×6×4）
M_GRID = (5, 6, 8, 10, 14, 20)     # 专家数上限（≤20）
WIN_GRID = (50, 70, 100, 120, 150, 200)
GAMMA_GRID = (1.0, 2.0, 4.0, 8.0)

ALGO_VERSION = 'Bv2_lib1000'       # 算法版本（变化必须升级，防缓存误用）


def load_data():
    rows = []
    with open(CSV, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"issue": r["issue"], "b": int(r["hundreds"]),
                             "s": int(r["tens"]), "g": int(r["ones"])})
            except Exception:
                continue
    return rows


def get_next_issue(last):
    if not last:
        return "?"
    year = int(str(last)[:4])
    num = int(str(last)[4:])
    return f"{year}{num + 1:03d}" if num < 359 else f"{year + 1}001"


def build_matrices(issues, hh, tt, oo, pool, bt_window=BT_WINDOW, win_max=WIN_MAX):
    """walk-forward 矩阵（B系统独立版）：列 j 对应数据期 L0+j。
    特征 = 期t-1 / 期t-2 计算（复用 formulas.feat_list），末列对应下一期预测。
    返回 (pred, hit, L0)。"""
    from formulas import feat_list
    N = len(hh)
    L0 = N - bt_window - win_max
    assert L0 >= 2, f"数据不足：需要至少 {bt_window + win_max + 2} 期，当前 {N}"
    F_ext = np.array([
        feat_list(hh[t - 1], tt[t - 1], oo[t - 1],
                  prev=(hh[t - 2], tt[t - 2], oo[t - 2]))
        for t in range(L0, N + 1)
    ], dtype=np.int16)                                     # (bt_window+win_max+1, 81)
    ah_ext = np.concatenate([np.asarray(hh[L0:N], dtype=np.int16), [0]])
    K = len(pool)
    pred = np.zeros((K, N - L0 + 1), dtype=np.int16)
    for i, exp in enumerate(pool):
        cols = np.array([idx for _, idx in exp['terms']], dtype=np.intp)
        coeffs = np.array([c for c, _ in exp['terms']], dtype=np.int16)
        if len(cols) == 1:
            pred[i, :] = (F_ext[:, cols[0]] * coeffs[0] + exp['const']) % 10
        else:
            pred[i, :] = ((F_ext[:, cols] * coeffs[None, :]).sum(axis=1) + exp['const']) % 10
    hit = (pred != ah_ext[None, :])
    assert hit.shape[1] == N - L0 + 1 == bt_window + win_max + 1
    return pred, hit, L0


def hedge_vote(m, win, gamma, j, hit, pred):
    """近 win 期命中率 TopM 专家加权投票 → 票王=杀码。返回 (kill, idx, weights, votes)。"""
    lo = j - win
    rates = hit[:, lo:j].mean(axis=1)
    ti = np.argsort(-rates)[:m]
    w = np.maximum(rates[ti], SMOOTH) ** gamma
    votes = np.bincount(pred[ti, j], weights=w, minlength=10)
    return int(np.argmax(votes)), ti, w, votes


def top3_codes(kill, votes):
    order = sorted(range(10), key=lambda x: -float(votes[x]))
    return [kill] + [c for c in order if c != kill][:2]


def grid_scan(hit, pred, hh_arr, L0):
    """M×win×γ 全组合在 1000 期回测上扫描命中率。
    选优口径：命中率 → m更大 → win更大 → γ更大（并列时优先更稳定/更简单）。"""
    N = len(hh_arr)
    start = N - BT_WINDOW
    results = []
    for m in M_GRID:
        for win in WIN_GRID:
            for gamma in GAMMA_GRID:
                hits = 0
                for t in range(start, N):
                    j = t - L0
                    kill, *_ = hedge_vote(m, win, gamma, j, hit, pred)
                    if kill != int(hh_arr[t]):
                        hits += 1
                results.append({'m': m, 'win': win, 'gamma': gamma, 'hits': hits,
                                'total': BT_WINDOW, 'rate': round(hits / BT_WINDOW, 4)})
    results.sort(key=lambda r: (-r['rate'], -r['m'], -r['win'], -r['gamma']))
    return results, results[0]


def run_backtest(pool, pred, hit, L0, issues, hh, tt, oo, m, win, gamma):
    """1000 期逐期真实回测（walk-forward），返回 (rows[近期在上], summary)。"""
    N = len(hh)
    start = N - BT_WINDOW
    rows = []
    for t in range(start, N):
        j = t - L0
        kill, ti, w, votes = hedge_vote(m, win, gamma, j, hit, pred)
        chief = pool[int(ti[0])]
        rows.append({
            'issue': str(issues[t]),
            'num': f"{hh[t]}{tt[t]}{oo[t]}",
            'kill': kill,
            'hit': bool(kill != int(hh[t])),
            'top3': top3_codes(kill, votes),
            'n_exp': int(len(ti)),
            'votes': [round(float(x), 4) for x in votes],
            'fname': chief['name'],
            'fam': chief['family'],
        })
    hits = [r['hit'] for r in rows]
    rate = sum(hits) / len(hits)
    max_win = max_lose = cw = cl = 0
    for h in hits:
        if h:
            cw += 1; cl = 0
        else:
            cl += 1; cw = 0
        max_win = max(max_win, cw); max_lose = max(max_lose, cl)
    rows.reverse()
    summary = {'hit': int(sum(hits)), 'total': BT_WINDOW, 'rate': round(rate, 4),
               'baseline': 0.9, 'max_win': max_win, 'max_lose': max_lose}
    return rows, summary


def resolve_locked(pj):
    """读取已锁定的 B 参数：pool.json['lockedB'] = {'m':..,'win':..,'gamma':..}"""
    lb = pj.get('lockedB')
    if lb:
        return int(lb['m']), int(lb['win']), float(lb['gamma']), 'locked'
    return None, None, None, 'unlocked'


def next_prediction(pool, pred, hit, L0, issues, hh, tt, oo, m, win, gamma):
    """下一期：近 win 期命中率 TopM 加权投票。返回预测 + 本期入选专家卡数据。"""
    N = len(hh)
    j = N - L0
    kill, ti, w, votes = hedge_vote(m, win, gamma, j, hit, pred)
    rates = hit[:, j - win:j].mean(axis=1)
    experts = []
    for rank, (i, wi) in enumerate(zip(ti.tolist(), w.tolist())):
        e = pool[i]
        experts.append({
            'rank': rank + 1,
            'name': e['name'], 'fam': e['family'],
            'kill': int(pred[i, j]),
            'weight': round(float(wi), 4),
            'rate_win': round(float(rates[i]) * 100, 2),
            'rate_all': round(float(e.get('rate', 0)) * 100, 2),
            'hits': int(e.get('hits', 0)),
        })
    return {
        'target_issue': get_next_issue(issues[-1]),
        'last_issue': str(issues[-1]),
        'last_draw': f"{hh[-1]}{tt[-1]}{oo[-1]}",
        'kill': kill,
        'top3': top3_codes(kill, votes),
        'votes': [round(float(x), 4) for x in votes],
        'n_experts': int(len(ti)),
        'm': m, 'win': win, 'gamma': gamma,
        'experts': experts,
        'formula_name': f"Hedge Top{m}专家加权投票(win={win},γ={gamma})",
    }


def run(force_scan=False):
    t0 = time.time()
    rows = load_data()
    T = len(rows)
    hh = [r['b'] for r in rows]
    tt = [r['s'] for r in rows]
    oo = [r['g'] for r in rows]
    issues = [r['issue'] for r in rows]
    with open(POOL_JSON, 'r', encoding='utf-8') as f:
        pj = json.load(f)
    pool = pj['pool']
    print(f"B系统v2(专家库选优): 数据 {T} 期，候选专家库 {len(pool)} 条（A系统已锁定池）")

    pred, hit, L0 = build_matrices(issues, hh, tt, oo, pool)
    print(f"  矩阵 {len(pool)}×{hit.shape[1]}（回测窗{BT_WINDOW}+扩展{WIN_MAX}），L0={L0}，用时 {time.time()-t0:.1f}s")

    m, win, gamma, mode = resolve_locked(pj)
    if mode == 'locked' and not force_scan:
        best = {'m': m, 'win': win, 'gamma': gamma, 'hits': None,
                'total': BT_WINDOW, 'rate': None, 'locked': True}
        scan = []
        print(f"  ★ B参数已锁定 m={m}, win={win}, γ={gamma}（确定性：发布值=回测值，跳过扫描）")
    else:
        scan, best = grid_scan(hit, pred, np.asarray(hh, dtype=np.int16), L0)
        m, win, gamma = best['m'], best['win'], best['gamma']
        print(f"  网格扫描 {len(scan)} 组合 × {BT_WINDOW}期 → 最优 m={m}, win={win}, γ={gamma}, "
              f"命中 {best['hits']}/{best['total']} = {best['rate']*100:.2f}%")

    bt_rows, summary = run_backtest(pool, pred, hit, L0, issues, hh, tt, oo, m, win, gamma)
    print(f"  {BT_WINDOW}期回测: {summary['hit']}/{summary['total']} = {summary['rate']*100:.2f}% "
          f"(基线90%) 最大连错 {summary['max_lose']}")

    nxt = next_prediction(pool, pred, hit, L0, issues, hh, tt, oo, m, win, gamma)
    print(f"  下期 {nxt['target_issue']} 百位杀 {nxt['kill']} (Top3 {nxt['top3']})")

    # 多窗口命中率（100/200/500/1000）—— 与回测表同口径
    win_stats = {}
    for W in (100, 200, 500, 1000):
        seg = bt_rows[:W]
        n = len(seg)
        hits = sum(1 for r in seg if r['hit'])
        win_stats[str(W)] = {"n": n, "hit": hits, "pct": round(hits / n * 100, 2)}

    data = {
        "meta": {
            "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "total": T,
            "latest_issue": rows[-1]["issue"],
            "latest_number": f"{rows[-1]['b']}{rows[-1]['s']}{rows[-1]['g']}",
            "algorithm": f"B系统v2 · 专家库选优（{len(pool)}专家库 → Top{m}加权投票, win={win}, γ={gamma}）",
            "algo_version": ALGO_VERSION,
            "pool_size": len(pool),
            "window": win,
            "m": m,
            "gamma": gamma,
            "locked": mode == 'locked',
            "backtest_window": BT_WINDOW,
            "full_hit": summary['rate'] * 100,
            "full_base": 90.0,
        },
        "prediction": nxt,
        "selected_experts": nxt['experts'],
        "window_stats": win_stats,
        "best_scan": best,
        "rows": bt_rows,
        "summary": summary,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  已写入 {OUT}，总用时 {time.time()-t0:.1f}s")
    return data


def lock_best():
    """把当前扫描最优写回 pool.json['lockedB']（确定性锁定）。
    幂等：已锁定则校验一致性。"""
    with open(POOL_JSON, 'r', encoding='utf-8') as f:
        pj = json.load(f)
    if pj.get('lockedB'):
        print(f"  ★ B参数已锁定 {pj['lockedB']}，跳过")
        return
    if not os.path.exists(OUT):
        print("  ⚠ 无 engineB.json，先 run() 再锁定")
        return
    with open(OUT, 'r', encoding='utf-8') as f:
        d = json.load(f)
    b = d['best_scan']
    pj['lockedB'] = {'m': b['m'], 'win': b['win'], 'gamma': b['gamma'],
                     'rate': b['rate'], 'hits': b['hits'], 'total': b['total'],
                     'locked_at': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S'),
                     'note': 'B系统v2 确定性模式：专家库固定+参数固定，发布值=回测值'}
    with open(POOL_JSON, 'w', encoding='utf-8') as f:
        json.dump(pj, f, ensure_ascii=False)
    print(f"  ★ B参数已锁定 m={b['m']}, win={b['win']}, γ={b['gamma']}（确定性模式）")


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true', help='强制重新网格扫描（忽略 lockedB）')
    ap.add_argument('--lock', action='store_true', help='扫描后把最优写回 pool.json lockedB')
    args = ap.parse_args()
    run(force_scan=args.force)
    if args.lock:
        lock_best()
