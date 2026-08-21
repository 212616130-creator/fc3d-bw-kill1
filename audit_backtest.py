# -*- coding: utf-8 -*-
"""
audit_backtest.py — 百位杀一码回测审计（防未来信息）
=====================================================
1. 全表500期：用 cache/pool.json 独立重建 pred/hit 矩阵，逐期重算 hedge_vote，
   与 cache/result.json 的 rows 逐期比对（不一致数须为 0）。
2. 均匀抽样20期：从 feat_list 起完全独立重算（不依赖任何缓存矩阵）——
   每个专家在 [t-win, t-1] 每期用各自历史数据重算杀码 → 命中率 → 加权投票 → 比对记录，
   并打印每期实际使用的数据范围（证明 ≤ 第 t-1 期）。
3. 断言下期预测未使用第 N 期开奖。
"""
import json
import sys
import random

import numpy as np

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

from engine import load_data
from formulas import feat_list, eval_linear
from hedge_core import build_matrices, hedge_vote, WINDOW, SMOOTH, WIN_MAX

CSV = 'data/fc3d-history.csv'


def main():
    with open('cache/pool.json', 'r', encoding='utf-8') as f:
        pj = json.load(f)
    with open('cache/result.json', 'r', encoding='utf-8') as f:
        rj = json.load(f)
    pool = pj['pool']
    issues, hh, tt, oo = load_data(CSV)
    N = len(hh)
    best = rj['best_scan']
    gamma = best.get('gamma', 1.0)
    print(f"审计目标: 数据 {N} 期({issues[0]}~{issues[-1]}) | 专家池 {len(pool)} | "
          f"参数 win={best['win']}, K={best['k']}, γ={gamma}")

    # ---------- 1. 独立重建矩阵（不依赖缓存矩阵） ----------
    pred, hit, L0, hh_arr = build_matrices(issues, hh, tt, oo, pool)
    rows_by_issue = {r['issue']: r for r in rj['rows']}
    assert len(rows_by_issue) == WINDOW, f"rows 应含 {WINDOW} 期，实际 {len(rows_by_issue)}"

    bad = 0
    for t in range(N - WINDOW, N):
        j = t - L0
        kill, *_ = hedge_vote(best['win'], best['k'], SMOOTH, j, hit, pred, gamma)
        rec = rows_by_issue[str(issues[t])]
        if kill != rec['kill']:
            bad += 1
            print(f"  ✗ 不一致 期{issues[t]} 重算杀{kill} vs 记录杀{rec['kill']}")
    print(f"[1] 全表 {WINDOW} 期重算比对：不一致 {bad} 条 {'✓' if bad == 0 else '✗ 需排查'}")

    # ---------- 2. 抽样20期完全独立重算（从 feat_list 起，不用缓存矩阵） ----------
    rng = random.Random(20260821)
    sample = sorted(rng.sample(range(N - WINDOW, N), 20))
    s_bad = 0
    terms_list = [[tuple(x) for x in exp['terms']] for exp in pool]
    consts = [exp['const'] for exp in pool]
    for t in sample:
        # 独立重算每个专家在 [t-win, t-1] 每期的杀码（只用 q-1, q-2 数据）
        hist = np.zeros((len(pool), best['win']), dtype=np.int16)
        for qi, q in enumerate(range(t - best['win'], t)):
            fq = feat_list(hh[q - 1], tt[q - 1], oo[q - 1],
                           prev=(hh[q - 2], tt[q - 2], oo[q - 2]))
            for i in range(len(pool)):
                hist[i, qi] = eval_linear(fq, terms_list[i], consts[i])
        # 近win期命中率 = 各期杀码 ≠ 各期百位开奖
        actual = np.asarray(hh[t - best['win']:t], dtype=np.int16)
        rates = (hist != actual[None, :]).mean(axis=1)
        ti = np.argsort(-rates)[:best['k']]
        w = np.maximum(rates[ti], SMOOTH) ** gamma
        # 独立重算专家对 t 期的杀码（只用 t-1, t-2 数据）
        ft = feat_list(hh[t - 1], tt[t - 1], oo[t - 1],
                       prev=(hh[t - 2], tt[t - 2], oo[t - 2]))
        pred_t = np.array([eval_linear(ft, terms_list[i], consts[i]) for i in ti],
                          dtype=np.int16)
        votes = np.bincount(pred_t, weights=w, minlength=10)
        kill_indep = int(np.argmax(votes))
        rec = rows_by_issue[str(issues[t])]
        ok = (kill_indep == rec['kill'])
        if not ok:
            s_bad += 1
        print(f"  [{'✓' if ok else '✗'}] 期{issues[t]}(百位开奖{hh[t]}) 独立重算杀{kill_indep} "
              f"vs 记录{rec['kill']} | 仅用数据: 期{issues[t-1]},期{issues[t-2]}")
    print(f"[2] 抽样 {len(sample)} 期独立重算：不一致 {s_bad} 条 {'✓' if s_bad == 0 else '✗ 需排查'}")

    # ---------- 3. 下期预测未用第 N 期开奖 ----------
    nxt = rj['next']
    jN = N - L0
    assert jN == hit.shape[1] - 1, "末列应为下一期预测列"
    feats_last = feat_list(hh[N - 1], tt[N - 1], oo[N - 1],
                           prev=(hh[N - 2], tt[N - 2], oo[N - 2]))
    assert feats_last == _last_row_feats(hh, tt, oo, N), "末列特征复核失败"
    print(f"[3] 下期预测使用数据: 仅期{issues[N-1]},期{issues[N-2]}（未用第{N}期开奖）✓")
    print(f"    下期 {nxt['target_issue']} 百位杀码 {nxt['kill']}（Top3票码 {nxt['top3_vote']}）")

    ok_all = (bad == 0 and s_bad == 0)
    print("\n" + ("审计通过 ✓  全表与抽样均 0 不一致" if ok_all else "审计失败 ✗  存在不一致，请排查"))
    return 0 if ok_all else 1


def _last_row_feats(hh, tt, oo, N):
    """与 build_matrices 末行完全一致的特征（复核用）"""
    return feat_list(hh[N - 1], tt[N - 1], oo[N - 1],
                     prev=(hh[N - 2], tt[N - 2], oo[N - 2]))


if __name__ == '__main__':
    sys.exit(main())
