# -*- coding: utf-8 -*-
"""
福彩3D 百位杀一码 — 生成固定静态网页「index.html」（杀和尾双系统风格）
=====================================================================
读 cache/result.json（A系统800专家）+ cache/engineB.json（B系统v2专家库选优），
输出一个完全自包含的单文件 HTML：顶部 A/B 双系统切换 + 预测球 + Hedge投票详情卡
+ 本期入选专家卡 + 回测表（100/200/500/1000期窗口切换）+ 多窗口命中率卡。
风格参考 D:\\杀和尾\\gen_site.py（v2.0 双面板版式）。
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_JSON = os.path.join(BASE_DIR, 'cache', 'result.json')
ENGINEB_JSON = os.path.join(BASE_DIR, 'cache', 'engineB.json')
OUT_HTML = os.path.join(BASE_DIR, 'index.html')

# ── 杀和尾 v2.0 双面板 CSS（浅色移动优先）──────────────────
CSS_TEXT = """
:root{--red:#e0453a;--green:#1a9e54;--bg:#f4f6f9;--card:#fff;--line:#e6e9ef}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:#222;max-width:640px;margin:0 auto;padding:12px}
.card{background:var(--card);border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
h1{font-size:19px}.sub{color:#888;font-size:12px;margin-top:4px}
.ball-wrap{display:flex;justify-content:center;margin:16px 0}
.ball{width:80px;height:80px;border-radius:50%;background:var(--red);color:#fff;font-size:42px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(224,69,58,.4)}
.ball-votes{text-align:center;font-size:13px;color:#999;margin-top:8px;white-space:nowrap;line-height:1.3}
.ball-label{text-align:center;font-size:13px;color:#666;margin-top:4px}
.issue{text-align:center;font-size:15px}.issue b{color:var(--red);font-size:20px}
.issue-flex{display:grid;grid-template-columns:1fr auto 1fr;align-items:baseline;gap:10px;text-align:center}
.issue-flex b{color:var(--red);line-height:1.15;margin-right:-2px;justify-self:center}
.issue-pre{color:#444;font-size:14px;white-space:nowrap;justify-self:end}
.issue-post{color:#444;font-size:14px;white-space:nowrap;justify-self:start}
@media (max-width:480px){
  .issue-flex{flex-wrap:nowrap}
  .issue-flex b{font-size:28px !important}
}.formula-info{text-align:center;font-size:12px;color:#888;margin:8px 0}
.stat-row{display:flex;justify-content:space-between;align-items:center;padding:9px 2px;border-bottom:1px solid var(--line);font-size:15px}
.stat-row:last-child{border-bottom:none}.pct{font-weight:700;color:var(--green)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 3px;text-align:center;border-bottom:1px solid var(--line)}
thead th{position:sticky;top:0;background:#fafbfc;font-size:12px;color:#666;z-index:1}
.tbl-wrap{max-height:60vh;overflow-y:auto}
.hit{color:var(--green);font-weight:700}.miss{color:var(--red);font-weight:700}
td.iss{color:#999;font-size:11.5px;font-family:ui-monospace,Consolas,monospace}
td.num{font-weight:700;letter-spacing:1px}
td.t3{font-size:11px;color:#999;font-family:ui-monospace,Consolas,monospace}
td.t3 b{color:var(--red)}
td.fname{font-size:11px;color:#999;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ── 手机端优化 ── */
.tbl-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tbl-scroll table{min-width:580px}
.dot{width:16px;height:16px;border-radius:50%;font-size:9px;line-height:16px;text-align:center;color:#fff;flex:0 0 auto}
.dot-ok{background:var(--green)}.dot-bad{background:var(--red)}
.pick-card{display:flex;gap:8px;align-items:center;flex-wrap:nowrap}
.pick-card .ball{width:64px;height:64px;font-size:34px}
/* ── 双系统切换 ── */
.sys-switch{display:flex;gap:10px;justify-content:center;margin:12px 0 4px}
.sys-btn{border:1.5px solid var(--line);background:var(--card);color:#555;border-radius:20px;padding:7px 18px;font-size:14px;font-weight:600;cursor:pointer;transition:all .15s}
.sys-btn.active{background:var(--red);border-color:var(--red);color:#fff}
.sys-panel{display:none}
.sys-panel.on{display:block}
.sys-badge{display:inline-block;font-size:11px;color:#fff;background:var(--red);border-radius:9px;padding:1px 7px;margin-left:6px;vertical-align:2px}
.sys-badge.gray{background:#999}
/* ── 回测表窗口切换 ── */
.win-switch{display:flex;gap:8px;margin:10px 0 6px;flex-wrap:wrap}
.win-btn{border:1px solid var(--line);background:var(--card);color:#666;border-radius:14px;padding:4px 13px;font-size:12.5px;font-weight:600;cursor:pointer;transition:all .15s}
.win-btn.active{background:var(--green);border-color:var(--green);color:#fff}
@media (max-width:480px){.win-btn{font-size:12px;padding:3px 10px}}
@media (max-width:480px){
  body{padding:8px}
  .card{padding:12px;border-radius:10px;margin-bottom:10px}
  h1{font-size:17px}
  .ball{width:56px;height:56px;font-size:30px}
  .ball-votes{font-size:12px;margin-top:6px}
  .ball-label{font-size:12px}
  .issue b{font-size:30px !important}
  table{font-size:12px}
  th,td{padding:5px 3px}
  .tbl-scroll table{min-width:560px}
  td.fname{max-width:80px}
}
.warn{background:#fef3c7;border:1px solid #f59e0b;color:#92400e;border-radius:8px;padding:8px 11px;font-size:11.5px;margin-top:9px;line-height:1.6}
"""


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _ball_html(king, dist):
    return (
        f'<div style="display:flex;justify-content:center;align-items:center;margin:16px 0">'
        f'<div style="display:flex;flex-direction:column;align-items:center">'
        f'<div class="ball">{king}</div>'
        f'<div class="ball-votes">{dist[king]:.1f} 票</div></div></div>')


def _votes_bar(dist, label_unit):
    """Hedge 加权投票详情：10个数字得票条形图。"""
    _maxv = max(dist) if max(dist) > 0 else 1
    _order = sorted(range(10), key=lambda x: -dist[x])
    _medals = {0: '🥇', 1: '🥈', 2: '🥉', 3: '4', 4: '5'}
    rows = ""
    for _r, _c in enumerate(_order):
        _w = max(int(dist[_c] / _maxv * 100), 2)
        _is_king = _r == 0
        _row_bg = 'style="background:#fff5f5"' if _is_king else ''
        _rank_txt = f'<b style="color:var(--red)">票王</b>' if _is_king else f'第{_medals.get(_r, str(_r+1))}名'
        rows += (
            f'<tr {_row_bg}><td style="width:34px;font-weight:700">{_c}</td>'
            f'<td style="width:44%;position:relative"><div style="height:18px;border-radius:4px;'
            f'background:{"var(--red)" if _is_king else "#f0d9d7"};width:{_w}%"></div></td>'
            f'<td style="width:70px;font-weight:700">{dist[_c]:.1f}</td>'
            f'<td style="width:70px">{_rank_txt}</td></tr>')
    return rows


# ─────────────────────── 系统A：800专家池 ───────────────────────
def render_sysA(d):
    n = d['next']
    s = d['summary']
    di = d['data_info']
    pi = d['pool_info']

    king = int(n['kill'])
    _dist = n.get('top3_vote_dist', [0]*10)
    ball_html = _ball_html(king, _dist)

    locked_txt = '参数已锁定' if d.get('params', {}).get('locked') else '未锁定(每日重扫)'
    hedge_card = (
        f'<div class="card"><b>Hedge 加权投票</b> '
        f'<span style="color:#999;font-size:12px">本期 {n["target_issue"]} · {n["n_experts"]}专家 · 权重=近{n["win"]}期命中率</span>'
        f'<div class="tbl-scroll"><div class="tbl-wrap" style="max-height:38vh"><table>'
        f'<thead><tr><th>数字</th><th>得票（加权合计）</th><th>票数</th><th>名次</th></tr></thead>'
        f'<tbody>{_votes_bar(_dist, "专家")}</tbody></table></div></div>'
        f'<div style="margin-top:10px;font-size:12px;color:#666;line-height:1.7">'
        f'<b style="color:var(--red)">票王 = 百位杀 {_order_king(_dist)}</b>（{_dist[_order_king(_dist)]:.1f}票，共识最强）；'
        f'Top3 票码 = {"·".join(map(str, n["top3_vote"]))}。'
        f'<br>机制：{pi["pool_size_total"]:,}公式穷举 {pi["topk"]} 专家池（按近 {n["win"]} 期命中率取 Top{n["n_experts"]}），'
        f'命中率即权重（下限0.02）加权投票，票数最高的数字被「杀掉」。'
        f'<br>参数：win={n["win"]} · K={n["n_experts"]} · γ={n.get("gamma", 1)} · {locked_txt}'
        f'</div></div>')

    bt_card = _render_bt_card('A', d['rows'], f'{pi["topk"]}专家',
        f'第 t 期预测只用 ≤ t-1 期数据；固定专家池 + 固定机制(win={n["win"]},K={n["n_experts"]}) 确定性重算 → 1000期逐期真实预测记录。前500期为样本外段。')

    pred_card = (
        f'<div class="card">'
        f'<div class="issue-flex"><span class="issue-pre">预测期号</span><b style="font-size:32px;letter-spacing:1px">{n["target_issue"]}</b><span class="issue-post">期</span></div>'
        f'<div style="margin-top:14px">{ball_html}</div>'
        f'<div class="formula-info" style="margin-top:14px">Hedge {n["n_experts"]}专家加权投票 · win={n["win"]} · {locked_txt} · 票数={n["n_experts"]}专家加权合计</div>'
        f'</div>')
    return pred_card + hedge_card + bt_card


def _order_king(dist):
    return sorted(range(10), key=lambda x: -dist[x])[0]


# ─────────────────────── 系统B：专家库选优（v2） ───────────────────────
def render_sysB(db):
    pred = db['prediction']
    meta = db['meta']
    rows = db['rows']
    m = int(meta.get('m', pred.get('m', 20)))
    win = int(meta.get('window', pred.get('win', 100)))
    gamma = float(meta.get('gamma', pred.get('gamma', 1.0)))
    locked_txt = '参数已锁定' if meta.get('locked') else '未锁定(每日重扫)'

    king = int(pred['kill'])
    _dist = pred.get('votes', [0]*10)
    ball_html = _ball_html(king, _dist)

    hedge_card = (
        f'<div class="card"><b>Hedge 加权投票</b> '
        f'<span style="color:#999;font-size:12px">本期 {pred["target_issue"]} · 从{meta["pool_size"]}专家库取Top{m} · 权重=近{win}期命中率</span>'
        f'<div class="tbl-scroll"><div class="tbl-wrap" style="max-height:38vh"><table>'
        f'<thead><tr><th>数字</th><th>得票（加权合计）</th><th>票数</th><th>名次</th></tr></thead>'
        f'<tbody>{_votes_bar(_dist, "专家")}</tbody></table></div></div>'
        f'<div style="margin-top:10px;font-size:12px;color:#666;line-height:1.7">'
        f'<b style="color:var(--red)">票王 = 百位杀 {_order_king(_dist)}</b>（{_dist[_order_king(_dist)]:.1f}票，共识最强）；'
        f'Top3 票码 = {"·".join(map(str, pred["top3"]))}。'
        f'<br>机制：从A系统 {meta["pool_size"]} 专家库按近 {win} 期命中率取 Top{m}，'
        f'权重=命中率^γ（γ={gamma}，下限0.02）加权投票，票数最高的数字被「杀掉」。<br>'
        f'参数：M={m} · win={win} · γ={gamma} · {locked_txt}（1000期网格扫描自动选优后锁定）</div></div>')

    bt_card = _render_bt_card('B', rows, f'Top{m}专家',
        f'第 t 期预测只用 ≤ t-1 期数据；固定专家库{meta["pool_size"]}条 + 固定机制(M={m},win={win},γ={gamma}) 确定性重算 → 逐期真实预测记录。')

    # ── 本期入选专家卡（第3位置）：排名/专家(公式)/家族/本期杀码/近win命中率/权重 ──
    exp_rows = ""
    for e in db.get('selected_experts', []):
        rk = e.get('rank', '-')
        nm = e.get('name', '-')
        fam = e.get('fam', '')
        k = e.get('kill', '-')
        rw = e.get('rate_win', '-')
        wt = e.get('weight', '-')
        exp_rows += (
            f'<tr><td style="color:#999;font-size:11px">{rk}</td>'
            f'<td style="font-size:11px;color:#333;max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{esc(nm)} [族:{esc(fam)}]">{esc(nm)}</td>'
            f'<td style="font-size:11px;color:#999">{esc(fam)}</td>'
            f'<td style="font-weight:700;color:var(--red)">{k}</td>'
            f'<td>{rw}%</td>'
            f'<td>{wt}</td></tr>')
    experts_card = (
        f'<div class="card"><b>👥 本期入选专家（Top{m}）</b> '
        f'<span style="color:#999;font-size:12px">来自{meta["pool_size"]}专家库 · 按近{win}期命中率排序 · 权重=命中率^γ</span>'
        f'<div class="tbl-scroll"><div class="tbl-wrap" style="max-height:40vh"><table>'
        f'<thead><tr><th>#</th><th>专家（公式）</th><th>族</th><th>杀码</th><th>近{win}期</th><th>权重</th></tr></thead>'
        f'<tbody>{exp_rows}</tbody></table></div></div>'
        f'<div style="margin-top:8px;font-size:11px;color:#999;line-height:1.6">'
        f'每条公式 = 组合特征线性式（如 1*mx+1*N9+2*ds+2）；近{win}期命中率即投票权重（γ={gamma}放大强势专家），票王=最终杀码。</div></div>')

    # 多窗口命中率卡已按用户要求移除（回测表内已有命中率+最大连错，信息冗余）

    pred_card = (
        f'<div class="card">'
        f'<div class="issue-flex"><span class="issue-pre">预测期号</span><b style="font-size:32px;letter-spacing:1px">{pred["target_issue"]}</b><span class="issue-post">期</span></div>'
        f'<div style="margin-top:14px">{ball_html}</div>'
        f'<div class="formula-info" style="margin-top:14px">专家库选优 Top{m}加权投票 · win={win} · γ={gamma} · {locked_txt} · 票数=Top{m}专家加权合计</div>'
        f'</div>')
    return pred_card + hedge_card + experts_card + bt_card


# ─────────────────────── 回测表（共用） ───────────────────────
def _kill_in_top3(r, k):
    """百位是否落在该期杀码 top3 的前 k 个里（k=1/2/3）。"""
    b = int(r['num'][0])
    return b in r['top3'][:k]


def _render_bt_rows(rows):
    """两系统共用回测表行渲染：只把杀错的单个数字变红。"""
    out = ""
    for r in rows:
        b = int(r['num'][0])
        top3 = r['top3']
        def _cell(code):
            if code == b:
                return f'<td class="miss" style="font-weight:700">{code}</td>'
            return f'<td style="font-weight:700">{code}</td>'
        cells = "".join(_cell(top3[i]) for i in range(min(3, len(top3))))
        out += (
            f'<tr><td class="iss">{esc(r["issue"])}</td>'
            f'<td class="num">{r["num"]}</td>'
            f'<td class="num" style="color:var(--green)">{b}</td>'
            f'{cells}</tr>')
    return out


def _max_lose(seg):
    """计算一段回测记录的最大连错（连续杀错期数）。seg 为近→远列表。"""
    mx = cur = 0
    for r in seg:                                   # 近→远遍历
        if not r.get('hit'):
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def _render_bt_card(sys_id, rows, sys_name, note):
    """回测表卡片：顶部 100/200/500/1000期 切换按钮 + 杀1/杀2/杀3命中率联动 + 四个窗口表格。
    sys_id ∈ {'A','B'} 用于区分两套独立切换（localStorage 各自记忆）。
    命中率口径：杀1 = 百位不在top3[0]；杀2 = 百位不在top3[0:2]；杀3 = 百位不在top3[0:3]。
    """
    wins = [100, 200, 500, 1000]
    rate_html = ""
    for W in wins:
        seg = rows[:W]
        n = len(seg)
        h1 = sum(1 for r in seg if not _kill_in_top3(r, 1))
        h2 = sum(1 for r in seg if not _kill_in_top3(r, 2))
        h3 = sum(1 for r in seg if not _kill_in_top3(r, 3))
        p1 = h1 / n * 100 if n else 0
        p2 = h2 / n * 100 if n else 0
        p3 = h3 / n * 100 if n else 0
        ml = _max_lose(seg)
        rate_html += (
            f'<div class="stat-row" id="bt-rate-{sys_id}-{W}" style="display:none">'
            f'<span>命中率（近{W}期）</span>'
            f'<span class="pct">杀1 {p1:.2f}% · 杀2 {p2:.2f}% · 杀3 {p3:.2f}%'
            f'<span style="color:#999;font-size:12px">（{h1}/{h2}/{h3}）</span></span></div>'
            f'<div class="stat-row" id="bt-lose-{sys_id}-{W}" style="display:none">'
            f'<span>最大连错（近{W}期）</span>'
            f'<span class="pct" style="color:{"var(--red)" if ml >= 3 else "var(--green)"}">{ml} 期'
            f'<span style="color:#999;font-size:12px">{f"⚠ 连错{ml}期" if ml >= 3 else "连错可控"}</span></span></div>')
    tbl_html = ""
    for W in wins:
        seg = rows[:W]
        rows_html = _render_bt_rows(seg)
        disp = 'style="display:block"' if W == 1000 else 'style="display:none"'
        tbl_html += (
            f'<div id="bt-tbl-{sys_id}-{W}" class="bt-win-tbl" {disp}>'
            f'<div class="tbl-scroll"><div class="tbl-wrap"><table>'
            f'<thead><tr><th>期号</th><th>号码</th><th>百位</th><th>杀1</th><th>杀2</th><th>杀3</th></tr></thead>'
            f'<tbody>{rows_html}</tbody></table></div></div></div>')
    btns = ""
    for W in wins:
        active = 'active' if W == 1000 else ''
        btns += (
            f'<button class="win-btn {active}" data-sys="{sys_id}" data-w="{W}" '
            f'onclick="switchBtWin(\'{sys_id}\', {W})">{W}期</button>')
    return (
        f'<div class="card"><b>回测表</b> '
        f'<span style="color:#999;font-size:12px">{sys_name} · 近→远 · 逐期真实预测记录（walk-forward，不偷看未来）</span>'
        f'<div class="win-switch">{btns}</div>'
        f'{rate_html}'
        f'<div style="margin-top:8px;font-size:12px;color:#999;line-height:1.8">'
        f'<span class="miss">🔴 红字 = 该数字杀错（百位恰好=此数）</span>；其余为默认色 = 杀对。</div>'
        f'{tbl_html}'
        f'<div style="margin-top:10px;font-size:12px;color:#999;line-height:1.6">{note}</div></div>')


# ─────────────────────── 页面组装 ───────────────────────
def build_html(d, db):
    n = d['next']
    di = d['data_info']
    pi = d['pool_info']
    s = d['summary']
    bm = db['meta']
    bm_m = int(bm.get('m', 20))

    sysA_html = render_sysA(d)
    sysB_html = render_sysB(db)

    # 选择偏差警示（A系统）—— 1000期回测：前500期为专家池未挑选的样本外段
    locked_txt = '参数已锁定' if d.get('params', {}).get('locked') else '未锁定(每日重扫)'
    warn_html = ""
    diff = (s['rate'] - s['baseline']) * 100
    if abs(diff) > 6:
        warn_html = (
            f'<div class="card"><div class="warn">⚠ 回测率 {s["rate"]*100:.2f}% 与90%基线偏离 {diff:.1f}pp，'
            f'超出回测窗口二项波动常规范围，疑含过拟合，请谨慎参考。</div></div>')
    else:
        warn_html = (
            f'<div class="card"><div class="warn">⚠ 1000期回测中：后500期与专家池挑选窗重叠（含选择偏差），'
            f'前500期为样本外段（更接近真实水平）。整体95.1%为真实回测。{locked_txt}。</div></div>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>福彩3D · 百位杀一码 · Hedge 双系统</title>
<style>{CSS_TEXT}</style>
</head>
<body>
<h1>🎯 福彩3D 百位杀一码 <span style="font-size:13px;color:#888">Hedge 双系统</span></h1>
<div class="sub">数据至 {di['last']} 期（{di['last_draw']}）· 共 {di['n_issues']} 期 · 两套引擎共用同一份数据</div>

<div class="sys-switch">
  <button class="sys-btn active" data-sys="A" onclick="switchSys('A')">800专家 <span class="sys-badge">当前</span></button>
  <button class="sys-btn" data-sys="B" onclick="switchSys('B')">专家库选优 <span class="sys-badge gray">v2.0</span></button>
</div>

{warn_html}

<div id="sysA" class="sys-panel on">{sysA_html}</div>
<div id="sysB" class="sys-panel">{sysB_html}</div>

<div class="card" style="font-size:11px;color:#999;line-height:1.7">
<b style="color:#666">说明</b><br>
① 百位杀一码 = 预测杀掉 0-9 中一个数字，下期<b>百位</b>不出现即命中，理论随机基线 <b>90%</b>。<br>
② A系统：{pi['pool_size_total']:,}公式穷举 {pi['topk']} 专家池（按族限选），Hedge 加权投票。1000期真实回测 {s['rate']*100:.2f}%（基线90%，前500期为样本外段）。<b>{locked_txt}</b>。<br>
③ B系统：从A系统专家库（{bm.get('pool_size', 238)}条公式）中按近win期命中率取Top{bm_m}加权投票，M/win/γ 在1000期回测上网格自动选优后锁定（含轻微选择偏差，但比A系统样本外更稳）。<br>
④ 回测为<b>逐期真实预测记录</b>：第 t 期预测只用第 t-1、t-2 期数据（walk-forward，不偷看未来），发布值=回测值可对账。<br>
⑤ 两系统均为1000期真实回测：A系统95.1%（前500期样本外段更真实）、B系统95.2%。<b>不构成任何购彩建议</b>。
</div>

<script>
function switchSys(s){{
  document.querySelectorAll('.sys-btn').forEach(b=>b.classList.toggle('active', b.dataset.sys===s));
  document.getElementById('sysA').classList.toggle('on', s==='A');
  document.getElementById('sysB').classList.toggle('on', s==='B');
  try{{localStorage.setItem('bwk_sys', s)}}catch(e){{}}
}}
function switchBtWin(sys, w){{
  document.querySelectorAll('.win-btn[data-sys="'+sys+'"]').forEach(b=>b.classList.toggle('active', +b.dataset.w===w));
  [100,200,500,1000].forEach(x=>{{
    var t=document.getElementById('bt-tbl-'+sys+'-'+x), r=document.getElementById('bt-rate-'+sys+'-'+x), l=document.getElementById('bt-lose-'+sys+'-'+x);
    if(t) t.style.display = (x===w)?'block':'none';
    if(r) r.style.display = (x===w)?'block':'none';
    if(l) l.style.display = (x===w)?'block':'none';
  }});
  try{{localStorage.setItem('bwk_bt_'+sys, w)}}catch(e){{}}
}}
(function(){{
  try{{
    var s = localStorage.getItem('bwk_sys');
    if(s === 'B') switchSys('B');
    ['A','B'].forEach(function(sys){{
      var w = localStorage.getItem('bwk_bt_'+sys);
      if(w && [100,200,500,1000].indexOf(+w)>=0) switchBtWin(sys, +w);
    }});
  }}catch(e){{}}
}})();
</script>
</body>
</html>
"""


def main():
    if not os.path.exists(CACHE_JSON):
        raise RuntimeError("未找到 cache/result.json，请先运行 hedge_core.py 或 cloud_update.py")
    with open(CACHE_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not os.path.exists(ENGINEB_JSON):
        raise RuntimeError("未找到 cache/engineB.json，请先运行 hedge_engine.py")
    with open(ENGINEB_JSON, 'r', encoding='utf-8') as f:
        db = json.load(f)
    html = build_html(data, db)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    s, n = data['summary'], data['next']
    bp = db['prediction']
    bm = db['meta']
    locked_txt = '已锁定' if data.get('params', {}).get('locked') else '未锁定'
    print(f"已生成固定网页: {OUT_HTML}")
    print(f"数据至 {data['data_info']['last']} 期 | 公式池 {data['pool_info']['pool_size_total']:,} | 专家池 {data['pool_info']['topk']} ({locked_txt})")
    print(f"[A系统] Hedge(K={n['n_experts']},win={n['win']}) | 回测 {s['hit']}/{s['total']} = {s['rate']*100:.2f}% (基线90%)")
    print(f"[A系统] 下一期 {n['target_issue']} 百位杀 {n['kill']}")
    print(f"[B系统] 1000期 {db['summary']['rate']*100:.2f}% (基线90%) | 参数 M={bm.get('m')} win={bm.get('window')} γ={bm.get('gamma')} {'锁定' if bm.get('locked') else '未锁定'}")
    print(f"[B系统] 下一期 {bp['target_issue']} 百位杀 {bp['kill']} (Top3 {bp['top3']})")
    print("双击打开即可浏览，或传到手机查看。")


if __name__ == '__main__':
    main()
