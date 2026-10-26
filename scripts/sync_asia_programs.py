#!/usr/bin/env python3
"""asia_sellout_programs.json(단일 소스) → promo_dashboard_v10_6.html 반영.
사용: 1) asia_sellout_programs.json 수정  2) python3 scripts/sync_asia_programs.py
 · 효과 대시보드의 const AP = {...} 블록을 통째로 갈아끼운다.
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'asia_sellout_programs.json'), encoding='utf-8'))
rows = src['rows']
n = lambda v: 0 if v is None else float(v)
for r in rows:
    r['att'] = round(n(r['act']) / n(r['tgt']) * 100, 1) if n(r['tgt']) else None

ORDER = []
for r in rows:
    if r['p'] not in ORDER: ORDER.append(r['p'])
g = collections.OrderedDict()
for p in ORDER:
    rs = [r for r in rows if r['p'] == p]
    t, a = sum(n(r['tgt']) for r in rs), sum(n(r['act']) for r in rs)
    g[p] = dict(p=p, n=len(rs), tgt=t, act=a, bud=sum(n(r['bud']) for r in rs),
                rew=sum(n(r['rew']) for r in rs),
                att=round(a / t * 100, 1) if t else None)

tot = dict(tgt=sum(n(r['tgt']) for r in rows), act=sum(n(r['act']) for r in rows),
           bud=sum(n(r['bud']) for r in rows), rew=sum(n(r['rew']) for r in rows), n=len(rows))
tot['att'] = round(tot['act'] / tot['tgt'] * 100, 1) if tot['tgt'] else None
AP = dict(src=src['source_file'], asof=src['asof'], cut=src.get('cut', ''),
          rows=rows, groups=list(g.values()), tot=tot,
          dedup=src.get('dedup_total'), note=src.get('note', ''), note_dup=src.get('note_dup', ''))

f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8', newline='').read()
new = '<script>const AP = ' + json.dumps(AP, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const AP = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('AP 블록을 찾지 못했습니다 — 대시보드에 먼저 삽입이 필요합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed:
    open(f, 'w', encoding='utf-8', newline='').write(out)
print(f"ASIA Sell-out 프로그램 {len(rows)}건 · 목표 {tot['tgt']:,.0f} / 실적 {tot['act']:,.0f} ({tot['att']}%)")
print(f"예산 {tot['bud']:,.0f} · 지급 리워드 {tot['rew']:,.2f} · 기준 {AP['cut']}")
for v in g.values():
    print(f"  {v['p']:<26}{v['n']}곳  {v['act']:>10,.0f} / {v['tgt']:>10,.0f}  {v['att'] if v['att'] is not None else '-'}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
