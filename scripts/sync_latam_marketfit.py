#!/usr/bin/env python3
"""LATAM CTR MarketFit — 대상 SKU 목록(모델군별 게시일) × 연관 오더 원장을 다시 집계해
latam_marketfit.json 을 갱신하고 promo_dashboard_v10_6.html 의 const MF 를 갈아끼운다.

게시날짜 = 그 모델군 품번의 프로모션 적용 시작일. 품번마다 자기 게시일 이후 오더만 센다.
사용: python3 scripts/sync_latam_marketfit.py [--xlsx <대상 SKU 파일>] [--check]
  · --xlsx 를 주면 그 파일에서 대상 목록을 다시 읽어 json 을 새로 쓴다.
  · 주지 않으면 json 의 rows 를 그대로 쓰고 원장 집계만 다시 한다."""
import json, os, re, sys, csv, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(ROOT, 'latam_marketfit.json')
src = json.load(open(JS, encoding='utf-8'))

xlsx = None
if '--xlsx' in sys.argv:
    xlsx = sys.argv[sys.argv.index('--xlsx') + 1]

groups = collections.OrderedDict()
if xlsx:
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, data_only=True)['Sheet1']
    for r in ws.iter_rows(min_row=2, max_col=11, values_only=True):
        if not r[8]: continue
        key = (str(r[0]).strip(), str(r[1]).strip(), str(r[9])[:10])
        g = groups.setdefault(key, dict(make=key[0], model=key[1], start=key[2],
            yr=(str(int(r[4])) if r[4] else '') + '~' + (str(int(r[5])) if r[5] else ''), skus=[]))
        c = str(r[8]).strip()
        if c not in g['skus']: g['skus'].append(c)
else:
    for r in src['rows']:
        groups[(r['make'], r['model'], r['start'])] = dict(r)

start = {}
for g in groups.values():
    for c in g['skus']:
        start[c] = min(start.get(c, '9999'), g['start'])

orders = [r for r in csv.DictReader(open(os.path.join(ROOT, 'orders.csv'), encoding='utf-8-sig'))
          if r['promotion_category'].strip() == 'CTR MarketFit Campaign']
cut = max(r['order date'] for r in orders)
per = collections.defaultdict(lambda: {'q': 0.0, 'a': 0.0, 'cust': set()})
pre = collections.defaultdict(float)
for r in orders:
    c = r['CTR Code'].strip()
    if c not in start: continue
    d, a, q = r['order date'], float(r['amount'] or 0), float(r['qty'] or 0)
    if d >= start[c]:
        v = per[c]; v['q'] += q; v['a'] += a; v['cust'].add(r['customer'].strip())
    else:
        pre[c] += a

rows = []
for g in groups.values():
    hit = [c for c in g['skus'] if c in per]
    rows.append(dict(make=g['make'], model=g['model'], yr=g.get('yr', ''), start=g['start'],
        n=len(g['skus']), hit=len(hit), skus=g['skus'],
        q=round(sum(per[c]['q'] for c in hit)), a=round(sum(per[c]['a'] for c in hit)),
        cust=len(set().union(*[per[c]['cust'] for c in hit])) if hit else 0,
        started=g['start'] <= cut))
rows.sort(key=lambda r: r['start'])
tot = dict(n=len(start), hit=len(per), groups=len(rows),
           q=round(sum(v['q'] for v in per.values())), a=round(sum(v['a'] for v in per.values())),
           cust=len(set().union(*[v['cust'] for v in per.values()])) if per else 0,
           pre_n=len(pre), pre_a=round(sum(pre.values())))
src.update(rows=rows, tot=tot, cut=cut,
           ledger='orders.csv (연관 오더 원장 · ~' + cut + ')',
           note_pre='게시일 이전 오더는 캠페인 실적에서 뺐다 — %d종 $%s.' % (tot['pre_n'], format(tot['pre_a'], ',')))

MF = {k: src[k] for k in ('source_file', 'asof', 'ledger', 'cut', 'note', 'note_pre', 'rows', 'tot')}
f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8', newline='').read()
new = '<script>const MF = ' + json.dumps(MF, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const MF = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('MF 블록을 찾지 못했습니다 — 대시보드에 먼저 삽입이 필요합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
json.dump(src, open(JS, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if changed:
    open(f, 'w', encoding='utf-8', newline='').write(out)
print(f"LATAM MarketFit · 대상 {tot['n']}종 / {tot['groups']}개 모델군 · 전환 {tot['hit']}종 ({tot['hit']/tot['n']*100:.0f}%)")
print(f"금액 ${tot['a']:,} · 수량 {tot['q']:,} · 고객 {tot['cust']}곳 · 원장 ~{cut}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
