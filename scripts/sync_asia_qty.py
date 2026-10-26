#!/usr/bin/env python3
"""asia_sellin_qty.json(단일 소스) → promo_dashboard_v10_6.html 반영.
사용: 1) asia_sellin_qty.json 수정  2) python3 scripts/sync_asia_qty.py
 · 효과 대시보드의 const AQ = {...} 블록을 통째로 갈아끼운다.
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'asia_sellin_qty.json'), encoding='utf-8'))
rows = src['rows']
S = lambda f: sum(r[f] for r in rows)
M26 = src['months26']
tot = dict(q25=S('q25'), q26=S('q26'), new=S('new'),
           q26_9=S('q26_9'), new_9=S('new_9'), q25_9=S('q25_9'),
           avg26_9=round(sum(r['have26_9'] for r in rows) / max(len(rows), 1), 1),
           m26=[sum(r['m26'][i] for r in rows) for i in range(len(M26))],
           avg26=round(sum(r['have26'] for r in rows) / max(len(rows), 1), 1),
           full26=sum(1 for r in rows if r['have26'] >= len(M26) * 0.7))
# 품목 종수 합계는 고객사끼리 겹쳐 단순 합산이 아니므로 따로 적지 않는다.
AQ = dict(src=src['source_file'], asof=src['asof'], months26=M26, n=len(rows),
          rows=rows, tot=tot, note=src.get('note', ''), note_gap=src.get('note_gap', ''),
          note_cut=src.get('note_cut', ''))

f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8', newline='').read()
new = '<script>const AQ = ' + json.dumps(AQ, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const AQ = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('AQ 블록을 찾지 못했습니다 — 대시보드에 먼저 삽입이 필요합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed:
    open(f, 'w', encoding='utf-8', newline='').write(out)
print(f"ASIA Sell-in 수량 {len(rows)}곳 · 2025 {tot['q25']:,}개 → 2026 {tot['q26']:,}개 (10월까지)")
print(f"신규 품목 합계 {tot['new']:,}종 · 2026 자료 있는 달 평균 {tot['avg26']}/{len(M26)}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
