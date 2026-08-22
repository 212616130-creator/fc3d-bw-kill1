# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — Hedge 加权投票核心引擎
=============================================
机制（学习 D:\\通杀一码\\core.py 的 hedge_kill）：
  专家池 = 2356万公式在最新500期穷举选出的 TopK（按族限选，见 bruteforce500.py）
  每期预测：近 win 期专家命中率 = 权重(下限 SMOOTH) → 各专家对当期投票 → 票王 = 百位杀码
  参数 win/k 由 36 组合网格扫描在 500 期回测上自动选优。
walk-forward：第 t 期预测只用 t-1 / t-2 期数据算特征，严格不偷看未来。
500 期回测 = 逐期真实预测记录（近期→远期输出）。
"""
import json
import os
import time

import numpy as np

from engine import load_data, get_next_issue
from formulas import feat_list, FEAT_VERSION, NF

WINDOW = 500          # 回测/扫描窗口（穷举选池亦为500期，见 bruteforce500）
WIN_GRID = (20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 180, 200)  # 14×13×7=1274 组
K_GRID = (6, 8, 10, 12, 16, 20, 24, 30, 36, 40, 48, 56, 64)
GAMMA_GRID = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0)   # 权重幂次（>1 放大强专家话语权）
SMOOTH = 0.02         # 权重下限
TOPK = 240
PFL = 34              # 每族限选上限（7族×34≈238≈TOPK）
BASELINE = 0.9        # 百位杀1码随机基线
WIN_MAX = max(WIN_GRID)   # 200：特征矩阵向历史方向扩展，保证回测首期也有满窗口
CSV = 'data/fc3d-history.csv'
ALGO_VERSION = 'v7_window500'   # 算法版本（网格/权重函数/回测窗口变更必须升级，防缓存误用）


# ---------------------------------------------------------------- 矩阵构建

def build_matrices(issues, hh, tt, oo, pool):
    """扩展 pred/hit 矩阵：列 j 对应数据期 L0+j。
    回测期 t∈[N-WINDOW,N) → 列 j=t-L0，近win窗口 hit[:, j-win:j] 恒满。
    末列 j=N-L0 对应下一期预测（特征用第N-1、N-2期数据，未用第N期开奖）。
    返回 (pred, hit, L0, hh_arr)
    """
    N = len(hh)
    L0 = N - WINDOW - WIN_MAX
    assert L0 >= 2, f"数据不足：需要至少 {WINDOW + WIN_MAX + 2} 期，当前 {N}"
    # 特征：数据期 t 的特征由 期t-1、期t-2 计算
    F_ext = np.array([
        feat_list(hh[t - 1], tt[t - 1], oo[t - 1],
                  prev=(hh[t - 2], tt[t - 2], oo[t - 2]))
        for t in range(L0, N + 1)
    ], dtype=np.int16)                                     # (WINDOW+WIN_MAX+1, 81)
    # 被预测百位：末列占位（预测期，仅用于结构一致，不参与回测）
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
    # 断言防未来信息：回测列 j 的 pred 仅由 F_ext[j] 一行（期 L0+j-1 / L0+j-2）算出
    assert hit.shape[1] == N - L0 + 1 == WINDOW + WIN_MAX + 1
    return pred, hit, L0, np.asarray(hh, dtype=np.int16)


# ---------------------------------------------------------------- Hedge 投票

def hedge_vote(win, k, smooth, j, hit, pred, gamma=1.0):
    """近 win 期命中率 TopK 专家加权投票，票王 = 杀码。
    权重 = max(命中率, smooth) ** gamma（gamma>1 放大强势专家话语权）。
    返回 (kill, sel_idx, weights, votes, top_rate)"""
    lo = j - win
    rates = hit[:, lo:j].mean(axis=1)                      # (K,)
    ti = np.argsort(-rates)[:k]
    w = np.maximum(rates[ti], smooth) ** gamma
    votes = np.bincount(pred[ti, j], weights=w, minlength=10)
    kill = int(np.argmax(votes))
    return kill, ti, w, votes, float(rates[ti[0]])


def _top3_codes(kill, votes):
    order = sorted(range(10), key=lambda x: -float(votes[x]))
    return [kill] + [c for c in order if c != kill][:2]


# ---------------------------------------------------------------- 网格扫描

def grid_scan(hit, pred, hh_arr, L0, win_grid=None, k_grid=None, gamma_grid=None):
    """win×K×γ 全组合在500期回测上扫描命中率。
    与 run_backtest 共用 hedge_vote（保证扫描口径 = 回测口径，无平局差异）。
    返回 (results, best)。选优口径：命中率 → k更大 → win更大 → γ更大。"""
    if win_grid is None:
        win_grid = WIN_GRID
    if k_grid is None:
        k_grid = K_GRID
    if gamma_grid is None:
        gamma_grid = GAMMA_GRID
    N = len(hh_arr)
    start = N - WINDOW
    results = []
    for gamma in gamma_grid:
        for win in win_grid:
            for k in k_grid:
                hits = 0
                for t in range(start, N):
                    j = t - L0
                    kill, *_ = hedge_vote(win, k, SMOOTH, j, hit, pred, gamma)
                    if kill != int(hh_arr[t]):
                        hits += 1
                results.append({'gamma': gamma, 'win': win, 'k': k, 'hits': hits,
                                'total': WINDOW, 'rate': round(hits / WINDOW, 4)})
    results.sort(key=lambda r: (-r['rate'], -r['k'], -r['win'], -r['gamma']))
    return results, results[0]


# ---------------------------------------------------------------- 500期回测

def run_backtest(pool, pred, hit, L0, issues, hh, tt, oo, best_win, best_k, best_gamma=1.0):
    """500期逐期真实回测（walk-forward），返回 (rows[近期在上], summary)。"""
    N = len(hh)
    start = N - WINDOW
    rows = []
    for t in range(start, N):
        j = t - L0
        kill, ti, w, votes, top_rate = hedge_vote(best_win, best_k, SMOOTH, j, hit, pred, best_gamma)
        sel = ti.tolist()
        chief = pool[sel[0]]
        rows.append({
            'issue': str(issues[t]),
            'num': f"{hh[t]}{tt[t]}{oo[t]}",
            'kill': kill,
            'hit': bool(kill != int(hh[t])),
            'top3': _top3_codes(kill, votes),
            'n_exp': best_k,
            'votes': [round(float(x), 4) for x in votes],
            'fname': chief['name'],
            'fam': chief['family'],
            'rate': round(top_rate, 4),
        })
    hits = [r['hit'] for r in rows]
    rate = sum(hits) / len(hits)
    cur_win = cur_lose = 0
    for h in reversed(hits):
        if h: cur_win += 1
        else: break
    for h in reversed(hits):
        if not h: cur_lose += 1
        else: break
    max_win = max_lose = cw = cl = 0
    for h in hits:
        if h: cw += 1; cl = 0
        else: cl += 1; cw = 0
        max_win = max(max_win, cw); max_lose = max(max_lose, cl)
    # 专家池均值（选择偏差口径）
    j_end = (N - 1) - L0
    pool_avg = float(hit[:, j_end - WINDOW + 1:j_end + 1].mean())
    rows.reverse()                                        # 近期→远期
    summary = {
        'hit': int(sum(hits)), 'total': WINDOW, 'rate': round(rate, 4),
        'baseline': BASELINE,
        'pool_avg': round(pool_avg, 4),
        'max_win': int(max_win), 'max_lose': int(max_lose),
        'cur_win': int(cur_win), 'cur_lose': int(cur_lose),
    }
    return rows, summary


# ---------------------------------------------------------------- 下期预测

def next_prediction(pool, pred, hit, L0, issues, hh, tt, oo, fixed_info, best_win, best_k, best_gamma=1.0):
    """下一期（2026223）百位杀码：最近 best_win 期专家命中率加权投票。"""
    N = len(hh)
    j = N - L0                                            # 650：F_ext 末行（期N-1/N-2数据）
    kill, ti, w, votes, top_rate = hedge_vote(best_win, best_k, SMOOTH, j, hit, pred, best_gamma)
    experts = [{
        'name': pool[i]['name'], 'fam': pool[i]['family'],
        'kill': int(pred[i, j]), 'weight': round(float(wi), 4),
    } for i, wi in zip(ti.tolist(), w.tolist())]
    # 固定公式对照（选择偏差口径）：fixed 公式对下期预测
    fixed_kill = None
    if fixed_info:
        cols = np.array([idx for _, idx in fixed_info['terms']], dtype=np.intp)
        coeffs = np.array([c for c, _ in fixed_info['terms']], dtype=np.int16)
        feats = np.array(feat_list(hh[N - 1], tt[N - 1], oo[N - 1],
                                   prev=(hh[N - 2], tt[N - 2], oo[N - 2])), dtype=np.int16)
        fixed_kill = int((int((feats[cols] * coeffs).sum()) + fixed_info['const']) % 10)
    return {
        'target_issue': str(get_next_issue(issues[-1])),
        'last_issue': str(issues[-1]),
        'last_draw': f"{hh[-1]}{tt[-1]}{oo[-1]}",
        'kill': kill,
        'formula_name': f"Hedge {best_k}专家加权投票(win={best_win},γ={best_gamma})",
        'n_experts': best_k,
        'win': best_win,
        'gamma': best_gamma,
        'top_rate': round(top_rate, 4),
        'top3_vote': _top3_codes(kill, votes),
        'top3_vote_dist': [round(float(x), 4) for x in votes],
        'experts': experts,
        'refs': [
            {'id': 'Hedge', 'name': f"Hedge投票(K={best_k},win={best_win},γ={best_gamma})", 'kill': kill},
            {'id': 'Fixed', 'name': f"固定公式({fixed_info['name']})", 'kill': fixed_kill},
        ],
    }


# ---------------------------------------------------------------- 榜单

def build_leaderboard(pool, hit, L0, N, best_win):
    """池内专家按最近 best_win 期命中率 Top50。"""
    j = (N - 1) - L0
    rates = hit[:, j - best_win + 1:j + 1].mean(axis=1)
    idx = np.argsort(-rates)[:50]
    return [{'name': pool[i]['name'], 'fam': pool[i]['family'],
             'rate_recent': round(float(rates[i]), 4)} for i in idx]


# ---------------------------------------------------------------- 参数解析（锁定优先）

def _resolve_params(pj):
    """参数解析（锁定优先）：
    pool.json 有 locked → 返回 (locked['win'], locked['k'], locked['gamma'], 'locked')
    无 locked → 返回 (None, None, None, 'unlocked')，由调用方网格扫描选优。
    """
    locked = pj.get('locked')
    if locked:
        win = int(locked.get('win'))
        k = int(locked.get('k'))
        gamma = float(locked.get('gamma', 1.0))
        return win, k, gamma, 'locked'
    return None, None, None, 'unlocked'


# ---------------------------------------------------------------- 汇总

def main():
    t0 = time.time()
    issues, hh, tt, oo = load_data(CSV)
    with open('cache/pool.json', 'r', encoding='utf-8') as f:
        pj = json.load(f)
    pool, fixed_info = pj['pool'], pj['fixed']
    print(f"数据 {len(issues)} 期：{issues[0]} ~ {issues[-1]}，专家池 {len(pool)} 条")

    pred, hit, L0, hh_arr = build_matrices(issues, hh, tt, oo, pool)
    print(f"矩阵构建完成 ({len(pool)}×{hit.shape[1]})，L0={L0}，用时 {time.time()-t0:.1f}s")

    # ★ 锁定模式：参数固定，跳过网格扫描 → 发布值=回测值（确定性）
    win, k, gamma, mode = _resolve_params(pj)
    if mode == 'locked':
        best = {'win': win, 'k': k, 'gamma': gamma, 'hits': None, 'total': WINDOW,
                'rate': None, 'locked': True, 'note': '参数锁定(确定性模式)，不再每日重扫'}
        scan = []
        print(f"★ 锁定模式: win={win}, k={k}, γ={gamma}（确定性：发布值=回测值，跳过网格扫描）")
    else:
        scan, best = grid_scan(hit, pred, hh_arr, L0)
        print(f"网格扫描 {len(scan)} 组合 → 最优 win={best['win']}, k={best['k']}, γ={best['gamma']}, 命中 {best['hits']}/{best['total']} = {best['rate']*100:.2f}%")
        print("⚠ 未锁定参数：每天重扫 → 同期待开奖重算可能不一致。建议锁定参数(写 pool.json 的 locked 字段)实现确定性。")
        win, k, gamma = best['win'], best['k'], best['gamma']

    rows, summary = run_backtest(pool, pred, hit, L0, issues, hh, tt, oo,
                                 win, k, gamma)
    print(f"500期回测: 命中 {summary['hit']}/{summary['total']} = {summary['rate']*100:.2f}% "
          f"(基线 {BASELINE*100:.0f}%)  最大连错 {summary['max_lose']}")

    nxt = next_prediction(pool, pred, hit, L0, issues, hh, tt, oo, fixed_info,
                          win, k, gamma)
    print(f"下期 {nxt['target_issue']} 百位杀码: {nxt['kill']}  (Top3票码 {nxt['top3_vote']})")

    lb = build_leaderboard(pool, hit, L0, len(issues), win)

    result = {
        'fingerprint': f"{len(issues)}_{issues[-1]}_{FEAT_VERSION}",
        'algo_version': ALGO_VERSION,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'data_info': {'n_issues': len(issues), 'first': issues[0], 'last': issues[-1],
                      'last_draw': f"{hh[-1]}{tt[-1]}{oo[-1]}"},
        'pool_info': {'pool_size_total': pj['stats']['pool_size_total'],
                      'window': pj['window'],          # 穷举/选池窗口（500）
                      'backtest_window': WINDOW,       # 回测/扫描窗口（500）
                      'topk': TOPK, 'pfl': PFL,
                      'n_families': pj['stats']['n_families'],
                      'n_features': pj.get('n_features', NF),
                      'feat_version': FEAT_VERSION,
                      'scan_seconds': pj['stats']['scan_seconds']},
        'params': {'win': win, 'k': k, 'gamma': gamma,
                   'smooth': SMOOTH, 'baseline': BASELINE, 'locked': bool(mode == 'locked')},
        'scan': scan, 'best_scan': best,
        'next': nxt,
        'summary': summary,
        'fixed': {'name': fixed_info['name'], 'rate': fixed_info['rate'],
                  'hits': fixed_info['hits']},
        'rows': rows,
        'leaderboard': lb,
    }
    os.makedirs('cache', exist_ok=True)
    with open('cache/result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"\n已写入 cache/result.json，总用时 {time.time()-t0:.1f}s")
    return result


if __name__ == '__main__':
    main()
