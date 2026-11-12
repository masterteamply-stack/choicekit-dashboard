#!/usr/bin/env python3
"""LATAM CTR MarketFit — 대상 SKU 목록(모델군별 게시일) × 연관 오더 원장을 다시 집계해
latam_marketfit.json 을 갱신하고 promo_dashboard_v10_6.html 의 const MF 를 갈아끼움.

게시날짜 = 그 모델군 품번의 프로모션 적용 시작일. 품번마다 자기 게시일 이후 오더만 셈.
사용: python3 scripts/sync_latam_marketfit.py [--xlsx <대상 SKU 파일>] [--check]
  · --xlsx 를 주면 그 파일에서 대상 목록을 다시 읽어 json 을 새로 씀.
  · 주지 않으면 json 의 rows 를 그대로 쓰고 원장 집계만 다시 함."""
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

# 국가 × 고객사 — 이 캠페인은 다루는 품번·금액이 작아서 모델군보다 '어느 나라
# 어느 고객이 몇 종을 얼마에 사갔나' 가 더 읽힌다.
# 원장의 국가명이 한글·영문으로 섞여 있어(ECUADOR / 에콰도르) 그대로 묶으면
# 같은 고객사가 두 줄로 쪼개진다. 한글로 통일한다.
CTRY = {'ECUADOR': '에콰도르', 'PERU': '페루', 'COLOMBIA': '콜롬비아', 'CHILE': '칠레',
        'GUATEMALA': '과테말라', 'PANAMA': '파나마', 'ARGENTINA': '아르헨티나',
        'COSTA RICA': '코스타리카', 'BARBADOS': '바베이도스', 'PARAGUAY': '파라과이',
        'GUYANA': '가이아나', 'DOMINICAN REPUBLIC': '도미니카 공화국',
        'PUERTO RICO': '푸에르토리코', 'BRAZIL': '브라질', 'EL SALVADOR': '엘살바도르',
        'HONDURAS': '온두라스', 'MEXICO': '멕시코', 'BOLIVIA': '볼리비아',
        'NICARAGUA': '니카라과', 'URUGUAY': '우루과이', 'VENEZUELA': '베네수엘라',
        'TRINIDAD AND TOBAGO': '트리니다드토바고', 'SURINAME': '수리남',
        'JAMAICA': '자메이카', 'BELIZE': '벨리즈', 'HAITI': '아이티',
        'CUBA': '쿠바', 'SAINT LUCIA': '세인트루시아'}
def ctry(v):
    v = (v or '').strip()
    return CTRY.get(v.upper(), v)
cu = collections.defaultdict(lambda: {'sku': set(), 'q': 0.0, 'a': 0.0, 'n': 0,
                                      'first': '9999', 'last': ''})
for r in orders:
    c = r['CTR Code'].strip()
    if c not in start: continue
    d = r['order date']
    if d < start[c]: continue
    k = (ctry(r['country']), r['customer'].strip())
    v = cu[k]
    v['sku'].add(c); v['q'] += float(r['qty'] or 0); v['a'] += float(r['amount'] or 0)
    v['n'] += 1
    if d < v['first']: v['first'] = d
    if d > v['last']: v['last'] = d
cust_rows = sorted(
    [{'country': k[0], 'cust': k[1], 'sku': len(v['sku']), 'q': round(v['q']),
      'a': round(v['a']), 'n': v['n'], 'first': v['first'], 'last': v['last'],
      'avg': round(v['a'] / len(v['sku'])) if v['sku'] else 0}
     for k, v in cu.items()], key=lambda x: -x['a'])
cust_tot = {'n_country': len({x['country'] for x in cust_rows}),
            'n_cust': len(cust_rows),
            'sku': len({c for v in cu.values() for c in v['sku']}),
            'a': round(sum(x['a'] for x in cust_rows)),
            'q': round(sum(x['q'] for x in cust_rows)),
            'n': sum(x['n'] for x in cust_rows)}

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
src.update(rows=rows, tot=tot, cut=cut, cust_rows=cust_rows, cust_tot=cust_tot,
           ledger='orders.csv (연관 오더 원장 · ~' + cut + ')',
           note_pre='게시일 이전 오더는 캠페인 실적에서 뺐음 — %d종 $%s.' % (tot['pre_n'], format(tot['pre_a'], ',')))

MF = {k: src[k] for k in ('source_file', 'asof', 'ledger', 'cut', 'note', 'note_pre',
                          'rows', 'tot', 'cust_rows', 'cust_tot')}
f = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
html = open(f, encoding='utf-8', newline='').read()
new = '<script>const MF = ' + json.dumps(MF, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const MF = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('MF 블록을 찾지 못했음 — 대시보드에 먼저 삽입이 필요함.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
json.dump(src, open(JS, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if changed:
    open(f, 'w', encoding='utf-8', newline='').write(out)
print(f"LATAM MarketFit · 대상 {tot['n']}종 / {tot['groups']}개 모델군 · 전환 {tot['hit']}종 ({tot['hit']/tot['n']*100:.0f}%)")
print(f"금액 ${tot['a']:,} · 수량 {tot['q']:,} · 고객 {tot['cust']}곳 · 원장 ~{cut}")
print(f"국가 {cust_tot['n_country']}곳 · 고객사 {cust_tot['n_cust']}곳 · 전환 {cust_tot['sku']}종 · ${cust_tot['a']:,}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
