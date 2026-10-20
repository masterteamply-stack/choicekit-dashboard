#!/usr/bin/env python3
"""asia_choicekit.json(단일 소스) → promo_dashboard_v10_6.html 반영.
사용: 1) asia_choicekit.json 의 rows 수정  2) python3 scripts/sync_asia.py
 · 효과 대시보드의 const AS = {...} 블록을 통째로 갈아끼운다.
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'asia_choicekit.json'), encoding='utf-8'))
rows = []
for r in src['rows']:
    a25, tgt, got = r['a25'], r['tgt'], r['got']
    y25, y25t, y26t = r['y25'], r['y25t'], r['y26t']
    s25, s26pre, s26 = r.get('s25', 0), r.get('s26pre', 0), r.get('s26', 0)
    rows.append(dict(
        k=r['k'], code=r['code'], codes=r.get('codes') or [r['code']],
        name=r['name'], country=r['country'], period=r['period'],
        note=r.get('note', ''), ship_note=r.get('ship_note', ''),
        s25=s25, s26pre=s26pre, s26=s26,
        sratio=(round(s26 / s25 * 100) if s25 else None),
        syoy=(round((s26 - s25) / s25 * 100, 1) if s25 else None),
        scut=(round((s26pre - s26) / s26pre * 100, 1) if s26pre else None),
        a25=a25, tgt=tgt, got=got,
        ratio=(round(got / a25 * 100) if a25 else None),
        yoy=(round((got - a25) / a25 * 100, 1) if a25 else None),
        att=(round(got / tgt * 100, 1) if tgt else None),
        y25=y25, y25t=y25t, y26t=y26t,
        aratio=(round(y26t / y25t * 100) if y25t else None),
        ayoy=(round((y26t - y25t) / y25t * 100, 1) if y25t else None),
        vs25=(round(y26t / y25 * 100) if y25 else None),
        share=(round(got / y26t * 100, 1) if y26t else None)))
rows.sort(key=lambda r: -r['got'])
S = lambda f: sum(r[f] for r in rows)
tot = dict(a25=S('a25'), tgt=S('tgt'), got=S('got'), y25=S('y25'), y25t=S('y25t'), y26t=S('y26t'),
           s25=S('s25'), s26pre=S('s26pre'), s26=S('s26'))
tot.update(sratio=round(tot['s26'] / tot['s25'] * 100) if tot['s25'] else None,
           syoy=round((tot['s26'] - tot['s25']) / tot['s25'] * 100, 1) if tot['s25'] else None,
           scut=round((tot['s26pre'] - tot['s26']) / tot['s26pre'] * 100, 1) if tot['s26pre'] else None)
tot.update(ratio=round(tot['got'] / tot['a25'] * 100),
           yoy=round((tot['got'] - tot['a25']) / tot['a25'] * 100, 1),
           att=round(tot['got'] / tot['tgt'] * 100, 1),
           aratio=round(tot['y26t'] / tot['y25t'] * 100),
           ayoy=round((tot['y26t'] - tot['y25t']) / tot['y25t'] * 100, 1),
           vs25=round(tot['y26t'] / tot['y25'] * 100),
           share=round(tot['got'] / tot['y26t'] * 100, 1))
AS = dict(src=src['source_file'], asof=src['asof'], n=len(rows), rows=rows, tot=tot,
          note_ship=src.get('note_ship', ''),
          hit=sum(1 for r in rows if (r['att'] or 0) >= 100),
          up=sum(1 for r in rows if (r['ratio'] or 0) >= 100))

f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8').read()
new = '<script>const AS = ' + json.dumps(AS, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const AS = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('AS 블록을 찾지 못했습니다 — 대시보드에 먼저 삽입이 필요합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed:
    open(f, 'w', encoding='utf-8').write(out)
print(f"ASIA {len(rows)}곳 · 초이스킷 {tot['a25']:,} → {tot['got']:,} (타깃 {tot['tgt']:,} · {tot['att']}%)")
print(f"전체 오더 25 1~10월 {tot['y25t']:,} → 26 {tot['y26t']:,} ({tot['aratio']}%) · 캠페인 비중 {tot['share']}%")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
