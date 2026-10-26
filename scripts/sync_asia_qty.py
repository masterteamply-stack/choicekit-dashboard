#!/usr/bin/env python3
"""asia_sellin_qty.json(단일 소스) → promo_dashboard_v10_6.html 반영.
사용: 1) asia_sellin_qty.json 수정  2) python3 scripts/sync_asia_qty.py
 · 효과 대시보드의 const AQ = {...} 블록을 통째로 갈아끼운다.
 · 2026 은 연관 오더 원장(orders.csv), 2025 는 제공받은 수량 자료에서 온다.
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'asia_sellin_qty.json'), encoding='utf-8'))
rows = sorted(src['rows'], key=lambda r: -r['q26'])
S = lambda f: sum(r[f] for r in rows)
M26 = src['months26']
tot = dict(q26=S('q26'), a26=S('a26'), q25=S('q25'),
           m26=[sum(r['m26'][i] for r in rows) for i in range(len(M26))])
tot['ratio'] = round(tot['q26'] / tot['q25'] * 100) if tot['q25'] else None
# 품목 종수 합계는 고객사끼리 겹쳐 단순 합산이 아니므로 따로 적지 않는다.
AQ = dict(src26=src.get('source_2026', ''), src25=src.get('source_2025', ''),
          asof=src['asof'], months26=M26, n=len(rows), rows=rows, tot=tot,
          note=src.get('note', ''), note_fix=src.get('note_fix', ''))

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
print(f"ASIA Sell-in {len(rows)}곳 · 2026 {tot['q26']:,}개 / ${tot['a26']:,} (오더 원장)")
print(f"2025 {tot['q25']:,}개 (제공 자료) · 전년 대비 {tot['ratio']}%")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
