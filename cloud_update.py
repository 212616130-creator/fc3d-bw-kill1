# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — 云端全自动更新（GitHub Actions）
======================================================
流程：多源降级抓取最新开奖(云端自动追加CSV)
      → 若期数变化/特征版本变化 → 重新暴力穷举选专家池(最新500期)
      → Hedge 网格扫描自动选参 → 500期逐期真实回测(walk-forward)
      → 下期预测 → 生成 index.html（GitHub Pages 根目录部署）

与本地 D:\\百位杀一码\\ 的关系：
  - 本仓库是**独立云端副本**，不覆盖任何原有项目/仓库
  - engine.py / formulas.py / bruteforce500.py / hedge_core.py / fetch.py 与本地同源
  - cache/pool.json 由云端自行维护（期数变化才重跑穷举，单次 cron 3 分钟内完成）

硬约束（与本地一致）：
  - walk-forward：第 t 期预测只用第 t-1 / t-2 期数据，严格不偷看未来
  - 命中 = 杀码 != 当期百位开奖；基线 = 90%
  - 500期回测表 = 逐期真实预测记录，可对账
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BJT = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE, 'data', 'fc3d-history.csv')
POOL_JSON = os.path.join(BASE, 'cache', 'pool.json')
RESULT_JSON = os.path.join(BASE, 'cache', 'result.json')
OUT_HTML = os.path.join(BASE, 'index.html')

os.chdir(BASE)          # 所有相对路径/模块导入基于仓库根
sys.path.insert(0, BASE)

# ★ 锁定参数（2026-08-22 老板拍板）：确定性模式 —— 专家池与 win/k/γ 永久固定，
#   发布值 = 回测值，可随时对账。勿改，除非老板重新拍板。
#   2026-08-22 网格扫描最新最优（8731期数据）：win=90,K=64,γ=8.0 → 500/500=100%
LOCKED_PARAMS = {'win': 90, 'k': 64, 'gamma': 8.0}


def log(msg):
    print(f"[{datetime.now(BJT).strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


def _lock_pool_params():
    """把 win/k/γ 锁定参数写入 cache/pool.json 的 locked 字段。
    之后：① 专家池永久固定不再重选  ② Hedge 参数固定不再网格扫描
    → 每天发布的预测 = 开奖完回测表同一期数值（纯确定性函数）。
    幂等：已锁定则跳过；若已锁定值与 LOCKED_PARAMS 不一致则告警（防参数漂移）。
    """
    try:
        with open(POOL_JSON, 'r', encoding='utf-8') as f:
            pj = json.load(f)
        if pj.get('locked'):
            cur = pj['locked']
            if cur != LOCKED_PARAMS:
                log(f"⚠ 已锁定参数 {cur} ≠ 代码 LOCKED_PARAMS {LOCKED_PARAMS}，请人工核对！")
            return
        pj['locked'] = dict(LOCKED_PARAMS)
        pj['locked_at'] = datetime.now(BJT).strftime('%Y-%m-%d %H:%M:%S')
        pj['lock_note'] = '确定性模式：专家池与win/k/γ永久固定，发布值=回测值'
        with open(POOL_JSON, 'w', encoding='utf-8') as f:
            json.dump(pj, f, ensure_ascii=False)
        log(f"★ 已锁定参数 win={LOCKED_PARAMS['win']} k={LOCKED_PARAMS['k']} γ={LOCKED_PARAMS['gamma']}（确定性模式）")
    except Exception as e:
        log(f"⚠ 锁定参数失败: {str(e)[:80]}")


def current_fingerprint():
    from engine import load_data
    issues, _, _, _ = load_data(CSV)
    return f"{len(issues)}_{issues[-1]}"


def ensure_pool(fp):
    """专家池缓存：期数/最新期/特征版本任一变化 → 重跑 2356万×500 穷举（约3分钟）。
    锁定模式：专家池永久固定，期数变化也不重选（确定性）。"""
    from formulas import FEAT_VERSION
    if os.path.exists(POOL_JSON):
        with open(POOL_JSON, 'r', encoding='utf-8') as f:
            pj = json.load(f)
        if pj.get('locked'):
            log(f"★ 专家池已锁定（确定性模式，固定 {len(pj.get('pool', []))} 专家）—— 跳过穷举")
            return
        pfp = f"{pj['data_info']['n_issues']}_{pj['data_info']['last']}"
        if pfp == fp and pj.get('feat_version') == FEAT_VERSION:
            log(f"专家池缓存命中（{fp} {FEAT_VERSION}），跳过穷举")
            return
        log(f"专家池过期（{pfp} → {fp}），重新穷举…")
    else:
        log("首次运行，暴力穷举选专家池（2356万公式×500期）…")
    import bruteforce500
    bruteforce500.main(verbose=True)
    # 穷举完成后锁定参数（确定性模式）
    _lock_pool_params()


def compute_result():
    """网格扫描 + 500期回测 + 下期预测，写 cache/result.json（与本地 hedge_core.main 同构）"""
    import hedge_core as _hc
    with open(POOL_JSON, 'r', encoding='utf-8') as f:
        _pj = json.load(f)
    if _pj.get('locked'):
        log(f"参数已锁定 win={_pj['locked'].get('win')} k={_pj['locked'].get('k')} γ={_pj['locked'].get('gamma')}（确定性模式，跳过网格扫描）")
    else:
        log(f"网格扫描（{len(_hc.WIN_GRID)}×{len(_hc.K_GRID)}×{len(_hc.GAMMA_GRID)} 组合 win×K×γ 自动选优）")
    log("500期 Hedge 逐期真实回测（walk-forward）+ 下期预测")
    _hc.main()


def compute_engineB():
    """B系统：从A系统专家库(238条)取TopM加权投票，1000期网格扫描选优后锁定（v2）"""
    import hedge_engine_lib
    hedge_engine_lib.run()
    hedge_engine_lib.lock_best()


def gen_html():
    """生成 index.html（Pages 根目录入口）。
    gen_site.py 直接输出 index.html（A/B 双面板）。"""
    import gen_site
    gen_site.main()
    if not os.path.exists(OUT_HTML):
        raise RuntimeError(f"gen_site 未产出 {OUT_HTML}")
    log(f"已生成 {OUT_HTML}")


def main():
    t0 = time.time()
    log("=" * 46)
    log("  福彩3D 百位杀一码 · 云端全自动更新")
    log("=" * 46)

    # ---- [1/5] 数据同步（多源降级 + 云端自动追加CSV）----
    log("[1/5] 同步最新数据（多源降级抓取）")
    added = 0
    try:
        import fetch
        nxt, added = fetch.sync_data()
    except Exception as e:
        log(f"⚠ 数据同步异常，沿用现有CSV: {str(e)[:80]}")
    fp = current_fingerprint()
    log(f"数据指纹: {fp}（新增 {added} 期）")

    # ---- [2/5] 专家池（锁定则固定；未锁定期数变化才重跑穷举）----
    log("[2/5] 专家池准备")
    ensure_pool(fp)

    # ---- [3/5][4/5] 网格扫描 + 500期回测 + 下期预测 ----
    log("[3/5] 参数解析 + [4/5] 500期回测 + 下期预测")
    compute_result()

    # ---- [4.5/5] B系统 专家库选优引擎（双系统）----
    log("[4.5/5] B系统 专家库选优引擎（双系统）")
    compute_engineB()

    # ---- [5/5] 生成 index.html ----
    log("[5/5] 生成 index.html（A/B 双面板）")
    gen_html()

    log(f"完成 ✓ 总耗时 {time.time()-t0:.1f}s（新增{added}期，指纹 {fp}）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
