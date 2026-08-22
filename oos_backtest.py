# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — 两系统样本外 1000 期真实回测
==================================================
目标：用专家池从未见过的更早 1000 期（2020293~2023277，挑选窗 2025075 之前）
对 A系统(800专家) 和 B系统(专家库选优) 做前推验证，暴露真实泛化能力。

关键：参数完全复用已锁定配置（不重新扫描选优）——
  A: win=25, K=40, γ=8
  B: M=14, win=100, γ=1
→ 任何选择偏差都被排除，纯检验"固定池+固定参数在陌生数据上的命中率"。
"""
import json
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

from engine import load_data
from formulas import feat_list, FEAT_VERSION

CSV = 'data/fc3d-history.csv'
POOL_JSON = 'cache/pool.json'
OOS_LEN = 1000              # 样本外回测 1000 期
# 样本外段 = 紧邻挑选窗之前的最远 1000 期：
#   挑选窗 = 末尾500期 (issues[N-500]~issues[N-1])
#   样本外 = issues[N-1500]~issues[N-501]  （离挑选窗最近、专家从未见过）
# 实现：N_end = N - 500（段末 exclusive），start = N_end - OOS_LEN = N - 1500
N_END_OFFSET = 500          # 段末 exclusive 距末尾的期数
WIN_MAX = 200               # 特征预热

SMOOTH = 0.02


def build_oos_matrices(hh, tt, oo, pool, L0, N_end):
    """对任意 [L0, N_end] 段构建 walk-forward 矩阵（特征只用 t-1/t-2）。
    返回 (pred, hit, hh_arr)。"""
    F = np.array([
        feat_list(hh[t - 1], tt[t - 1], oo[t - 1],
                  prev=(hh[t - 2], tt[t - 2], oo[t - 2]))
        for t in range(L0, N_end + 1)
    ], dtype=np.int16)
    ah = np.concatenate([np.asarray(hh[L0:N_end], dtype=np.int16), [0]])
    K = len(pool)
    pred = np.zeros((K, N_end - L0 + 1), dtype=np.int16)
    for i, exp in enumerate(pool):
        cols = np.array([idx for _, idx in exp['terms']], dtype=np.intp)
        coeffs = np.array([c for c, _ in exp['terms']], dtype=np.int16)
        if len(cols) == 1:
            pred[i, :] = (F[:, cols[0]] * coeffs[0] + exp['const']) % 10
        else:
            pred[i, :] = ((F[:, cols] * coeffs[None, :]).sum(axis=1) + exp['const']) % 10
    hit = (pred != ah[None, :])
    return pred, hit


def hedge_vote(m, win, gamma, j, hit, pred):
    lo = j - win
    rates = hit[:, lo:j].mean(axis=1)
    ti = np.argsort(-rates)[:m]
    w = np.maximum(rates[ti], SMOOTH) ** gamma
    votes = np.bincount(pred[ti, j], weights=w, minlength=10)
    return int(np.argmax(votes)), ti, w, votes


def run_oos(pool, hh, tt, oo, issues, m, win, gamma, name, win_max=WIN_MAX):
    N = len(hh)
    N_end = N - N_END_OFFSET             # 段末 exclusive（紧邻挑选窗之前）
    L0 = N_end - OOS_LEN - win_max       # 再往前留 win_max 特征预热
    assert L0 >= 2, f"历史不足：L0={L0}"
    pred, hit = build_oos_matrices(hh, tt, oo, pool, L0, N_end)
    hh_arr = np.asarray(hh, dtype=np.int16)
    start = N_end - OOS_LEN
    rows = []
    for t in range(start, N_end):
        j = t - L0
        kill, ti, w, votes = hedge_vote(m, win, gamma, j, hit, pred)
        rows.append({
            'issue': str(issues[t]),
            'num': f"{hh[t]}{tt[t]}{oo[t]}",
            'kill': kill,
            'hit': bool(kill != int(hh[t])),
            'top3': None,
        })
    hits = [r['hit'] for r in rows]
    rate = sum(hits) / len(hits)
    mx = cur = 0
    for h in hits:
        if h:
            cur = 0
        else:
            cur += 1
            mx = max(mx, cur)
    print(f"[{name}] 样本外{OOS_LEN}期回测 ({issues[start]}~{issues[N_end-1]}): "
          f"{sum(hits)}/{len(hits)} = {rate*100:.2f}%  最大连错 {mx}  (基线90%)")
    # 分段
    for lbl, seg in (('近500期', rows[:500]), ('前500期', rows[500:])):
        sh = sum(1 for r in seg if r['hit'])
        print(f"     {lbl}: {sh}/{len(seg)} = {sh/len(seg)*100:.2f}%")
    return rows


def main():
    issues, hh, tt, oo = load_data(CSV)
    with open(POOL_JSON, 'r', encoding='utf-8') as f:
        pj = json.load(f)
    pool = pj['pool']
    N = len(issues)
    oos_start = issues[N - N_END_OFFSET - OOS_LEN]
    oos_end = issues[N - N_END_OFFSET - 1]
    print(f"数据 {N} 期；样本外段 = 挑选窗(近500期)之前紧邻的 {OOS_LEN} 期")
    print(f"  段范围: {oos_start} ~ {oos_end}")
    print(f"  挑选窗(专家见过): {issues[-500]} ~ {issues[-1]}  → 完全不相交 ✓\n")

    # A系统（锁定参数 win=25 K=40 γ=8）
    a_lock = pj['locked']
    print("=== A系统 (800专家池) ===")
    rowsA = run_oos(pool, hh, tt, oo, issues,
                    int(a_lock['k']), int(a_lock['win']), float(a_lock['gamma']),
                    f"A系统(win={a_lock['win']},K={a_lock['k']},γ={a_lock['gamma']})")

    # B系统（锁定参数 M=14 win=100 γ=1）
    b_lock = pj.get('lockedB', {'m': 14, 'win': 100, 'gamma': 1.0})
    print("\n=== B系统 (专家库选优) ===")
    rowsB = run_oos(pool, hh, tt, oo, issues,
                    int(b_lock['m']), int(b_lock['win']), float(b_lock['gamma']),
                    f"B系统(M={b_lock['m']},win={b_lock['win']},γ={b_lock['gamma']})")

    # 汇总输出
    out = {
        'oos_segment': {'start': issues[N-N_END_OFFSET-OOS_LEN],
                        'end': issues[N-N_END_OFFSET-1],
                        'len': OOS_LEN},
        'pick_window': {'start': issues[-500], 'end': issues[-1]},
        'A': {'params': a_lock, 'rows': rowsA},
        'B': {'params': b_lock, 'rows': rowsB},
    }
    with open('cache/oos_backtest.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\n✓ 已写入 cache/oos_backtest.json")


if __name__ == '__main__':
    main()
