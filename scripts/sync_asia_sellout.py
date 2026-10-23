#!/usr/bin/env python3
"""asia_sellout.json(단일 소스) → promo_dashboard_v10_6.html 반영.
사용: 1) asia_sellout.json 의 rows 수정  2) python3 scripts/sync_asia_sellout.py
 · 효과 대시보드의 const AO = {...} 블록을 통째로 갈아끼운다.
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'asia_sellout.json'), encoding='utf-8'))
MN = src['months']
rows = []
for r in src['rows']:
    m = [round(x) for x in r['m']]
    rows.append(dict(
        k=r['k'], code=r['code'], codes=r.get('codes') or [r['code']],
        country=r['country'], cur=r['cur'], fx=r['fx'],
        programs=r.get('programs', []), m=m, usd=r.get('usd') or sum(m),
        last=r.get('last', ''), status=r.get('status', ''), dup=r.get('dup', '')))
rows.sort(key=lambda r: -r['usd'])
tgt = src['target']
usd = sum(r['usd'] for r in rows)
mtot = [sum(r['m'][i] for r in rows) for i in range(len(MN))]
tot = dict(tgt=tgt, usd=usd, att=round(usd / tgt * 100, 1) if tgt else None, m=mtot)
AO = dict(src=src['source_file'], asof=src['asof'], months=MN, n=len(rows), rows=rows, tot=tot,
          note_dup=src.get('note_dup', ''), note_scope=src.get('note_scope', ''),
          target_src=src.get('target_src', ''),
          have=sum(1 for r in rows if r['usd'] > 0),
          pending=[r['k'] for r in rows if r['usd'] == 0])

f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8', newline='').read()
new = '<script>const AO = ' + json.dumps(AO, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const AO = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('AO 블록을 찾지 못했습니다 — 대시보드에 먼저 삽입이 필요합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed:
    open(f, 'w', encoding='utf-8', newline='').write(out)
print(f"ASIA sell-out {len(rows)}곳 · 실적 {usd:,} / 목표 {tgt:,} ({tot['att']}%)")
print('월별 ' + ' · '.join(f"{m[5:]}월 {v:,}" for m, v in zip(MN, mtot)))
print('자료 미수령: ' + (', '.join(AO['pending']) or '없음'))
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
