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


def log(msg):
    print(f"[{datetime.now(BJT).strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


def current_fingerprint():
    from engine import load_data
    issues, _, _, _ = load_data(CSV)
    return f"{len(issues)}_{issues[-1]}"


def ensure_pool(fp):
    """专家池缓存：期数/最新期/特征版本任一变化 → 重跑 2356万×500 穷举（约3分钟）"""
    from formulas import FEAT_VERSION
    if os.path.exists(POOL_JSON):
        with open(POOL_JSON, 'r', encoding='utf-8') as f:
            pj = json.load(f)
        pfp = f"{pj['data_info']['n_issues']}_{pj['data_info']['last']}"
        if pfp == fp and pj.get('feat_version') == FEAT_VERSION:
            log(f"专家池缓存命中（{fp} v{FEAT_VERSION}），跳过穷举")
            return
        log(f"专家池过期（{pfp} → {fp}），重新穷举…")
    else:
        log("首次运行，暴力穷举选专家池（2356万公式×500期）…")
    import bruteforce500
    bruteforce500.main(verbose=True)


def compute_result():
    """网格扫描 + 500期回测 + 下期预测，写 cache/result.json（与本地 hedge_core.main 同构）"""
    import hedge_core as _hc
    log(f"网格扫描（{len(_hc.WIN_GRID)}×{len(_hc.K_GRID)}×{len(_hc.GAMMA_GRID)} 组合 win×K×γ 自动选优）")
    log("500期 Hedge 逐期真实回测（walk-forward）+ 下期预测")
    _hc.main()


def gen_html():
    """生成 index.html（Pages 根目录入口）。
    复用本地已验证的 gen_site.main() 输出「百位杀一码.html」，再重命名为 index.html，
    保证云端页面与本地页面 100% 同源。"""
    import gen_site
    gen_site.main()
    src = os.path.join(BASE, '百位杀一码.html')
    if os.path.exists(src):
        os.replace(src, OUT_HTML)
        log(f"已生成 {OUT_HTML}")
    else:
        raise RuntimeError(f"gen_site 未产出 {src}")


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

    # ---- [2/5] 专家池（期数变化自动重跑穷举）----
    log("[2/5] 专家池准备")
    ensure_pool(fp)

    # ---- [3/5][4/5] 网格扫描 + 500期回测 + 下期预测 ----
    log("[3/5] 网格扫描选参 + [4/5] 500期回测 + 下期预测")
    compute_result()

    # ---- [5/5] 生成 index.html ----
    log("[5/5] 生成 index.html")
    gen_html()

    log(f"完成 ✓ 总耗时 {time.time()-t0:.1f}s（新增{added}期，指纹 {fp}）")
    return 0


if __name__ == '__main__':
    sys.exit(main())
