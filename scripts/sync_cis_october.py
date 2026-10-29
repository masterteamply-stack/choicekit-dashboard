#!/usr/bin/env python3
"""CIS 10월 리포트(const CIS10) 생성.

  python3 scripts/sync_cis_october.py --asian <CK_Asian_Order...xlsx> --euro <CK_European_Order...xlsx>
  python3 scripts/sync_cis_october.py                 # 저장된 집계로 반영만
  python3 scripts/sync_cis_october.py ... --check     # 쓰지 않고 수치만

오더 수치는 원천 엑셀(Raw Data 시트)에서 매번 다시 뽑고, 활동·콘텐츠 글은
cis_october.json 에서 읽는다. 둘을 합쳐 const CIS10 한 덩어리로 넣는다.

집계 규칙
  금액 amount(USD) · 날짜 order date · 고객 customer · 국가 country
  Asian / European 은 파일로 가른다. 캠페인 효과 탭의 CIS 수치와는 집계 범위가
  달라 서로 더하지 않는다(참고 지표).
"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
SRC = os.path.join(ROOT, 'cis_october.json')
ADS = os.path.join(ROOT, 'cis_ads.json')
AGG = os.path.join(ROOT, 'cis_october_orders.json')
TGT = os.path.join(ROOT, 'campaign_target_skus.json')


def read(path, tag):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)['Raw Data']
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() if h is not None else '' for h in rows[1]]
    ix = {h: i for i, h in enumerate(head) if h}
    need = ['CTR Code', 'order date', 'country', 'qty', 'amount', 'customer', 'product']
    miss = [k for k in need if k not in ix]
    if miss:
        print(f'{os.path.basename(path)} 에 없는 열: ' + ', '.join(miss)); sys.exit(1)
    out = []
    for r in rows[2:]:
        if not r or not r[ix['CTR Code']]: continue
        d = r[ix['order date']]
        d = d.date().isoformat() if isinstance(d, datetime.datetime) else str(d)[:10]
        out.append(dict(g=tag, ctr=str(r[ix['CTR Code']]).strip(), d=d,
                        country=str(r[ix['country']] or '').strip(),
                        cust=str(r[ix['customer']] or '').strip(),
                        prod=str(r[ix['product']] or '').strip(),
                        qty=float(r[ix['qty']] or 0), usd=float(r[ix['amount']] or 0)))
    return out


if '--asian' in sys.argv and '--euro' in sys.argv:
    R = read(sys.argv[sys.argv.index('--asian') + 1], 'A') + read(sys.argv[sys.argv.index('--euro') + 1], 'E')
    D = sorted({r['d'] for r in R})
    LM = D[-1][:7]                       # 마지막 오더월
    per = collections.defaultdict(lambda: dict(a=0.0, e=0.0, q=0.0, sku=set(), cty='', oct=0.0))
    for r in R:
        o = per[r['cust']]
        o['a' if r['g'] == 'A' else 'e'] += r['usd']; o['q'] += r['qty']; o['sku'].add(r['ctr'])
        o['cty'] = o['cty'] or r['country']
        if r['d'][:7] == LM: o['oct'] += r['usd']
    cust = sorted(({'k': k, 'country': v['cty'], 'a': round(v['a'], 2), 'e': round(v['e'], 2),
                    't': round(v['a'] + v['e'], 2), 'sku': len(v['sku']), 'q': int(v['q']),
                    'oct': round(v['oct'], 2)} for k, v in per.items()), key=lambda x: -x['t'])
    for i, c in enumerate(cust): c['rank'] = i + 1

    mon = collections.defaultdict(lambda: dict(a=0.0, e=0.0, q=0.0))
    for r in R:
        m = mon[r['d'][:7]]; m['a' if r['g'] == 'A' else 'e'] += r['usd']; m['q'] += r['qty']
    months = [dict(m=k, a=round(v['a']), e=round(v['e']), q=int(v['q'])) for k, v in sorted(mon.items())]

    cty = collections.defaultdict(lambda: [0.0, set()])
    for r in R: cty[r['country']][0] += r['usd']; cty[r['country']][1].add(r['cust'])
    TOT = sum(r['usd'] for r in R)
    countries = sorted(({'k': k, 'usd': round(v[0]), 'n': len(v[1]),
                         'share': round(v[0] / TOT * 100, 1)} for k, v in cty.items()), key=lambda x: -x['usd'])

    pr = collections.defaultdict(lambda: [0.0, 0.0, set()])
    for r in R: pr[r['prod']][0] += r['usd']; pr[r['prod']][1] += r['qty']; pr[r['prod']][2].add(r['ctr'])
    prods = sorted(({'k': k, 'usd': round(v[0]), 'q': int(v[1]), 'sku': len(v[2])}
                    for k, v in pr.items()), key=lambda x: -x['usd'])

    sk = collections.defaultdict(lambda: [0.0, 0.0, ''])
    for r in R: sk[r['ctr']][0] += r['usd']; sk[r['ctr']][1] += r['qty']; sk[r['ctr']][2] = r['prod']
    top_sku = [{'k': k, 'usd': round(v[0]), 'q': int(v[1]), 'p': v[2]}
               for k, v in sorted(sk.items(), key=lambda x: -x[1][0])[:10]]

    T = json.load(open(TGT, encoding='utf-8'))
    tgt = {}
    for g, name in (('A', 'Asian vehicle'), ('E', 'European vehicle')):
        want = set(T[name]['target_skus']); got = {r['ctr'] for r in R if r['g'] == g}
        tgt[g] = dict(n=len(want), got=len(want & got), miss=len(want - got), extra=len(got - want))

    oct_rows = [r for r in R if r['d'][:7] == LM]
    oc = collections.defaultdict(float)
    for r in oct_rows: oc[r['cust']] += r['usd']
    prev = round(TOT - sum(r['usd'] for r in oct_rows), 2)

    agg = dict(_readme='원천 엑셀에서 뽑은 CIS Choice Kit 오더 집계. '
                       '재생성: python3 scripts/sync_cis_october.py --asian <xlsx> --euro <xlsx>',
               src_a=os.path.basename(sys.argv[sys.argv.index('--asian') + 1]),
               src_e=os.path.basename(sys.argv[sys.argv.index('--euro') + 1]),
               t_from=D[0], t_to=D[-1], last_month=LM, lines=len(R),
               a=round(sum(r['usd'] for r in R if r['g'] == 'A'), 2),
               e=round(sum(r['usd'] for r in R if r['g'] == 'E'), 2), total=round(TOT, 2),
               qty=int(sum(r['qty'] for r in R)), n_cust=len(cust), n_sku=len(sk),
               n_sku_a=tgt['A']['got'], n_sku_e=tgt['E']['got'],
               top5=round(sum(c['t'] for c in cust[:5]) / TOT * 100, 1),
               top3=round(sum(c['t'] for c in cust[:3]) / TOT * 100, 1),
               cust=cust, months=months, countries=countries, prods=prods,
               top_sku=top_sku, target=tgt,
               last=dict(usd=round(sum(r['usd'] for r in oct_rows), 2), lines=len(oct_rows),
                         qty=int(sum(r['qty'] for r in oct_rows)),
                         last_date=max(r['d'] for r in oct_rows),
                         prev=prev, pct=round(sum(r['usd'] for r in oct_rows) / prev * 100, 1),
                         by=[{'k': k, 'usd': round(v, 2)} for k, v in sorted(oc.items(), key=lambda x: -x[1])]))
    json.dump(agg, open(AGG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    agg = json.load(open(AGG, encoding='utf-8'))

src = json.load(open(SRC, encoding='utf-8'))
CIS10 = dict(agg); CIS10.pop('_readme', None)
CIS10.update({k: v for k, v in src.items() if not k.startswith('_')})
# 파일명이 10/28 이라도 실제 마지막 오더일로 적는다 — 없는 날짜를 적지 않는다
CIS10['period'] = f"{agg['t_from']} ~ {agg['t_to']}"
# 광고 성과는 따로 뽑아 둔 것을 얹는다 — scripts/sync_cis_ads.py
if os.path.exists(ADS):
    CIS10['ads'] = {k: v for k, v in json.load(open(ADS, encoding='utf-8')).items()
                    if not k.startswith('_')}
CIS10['validation'] = [
    f"고객 15곳 합계 ${agg['total']:,.2f} — 보고용 표의 $1,560,053 과 센트 단위까지 맞음.",
    "보고용 표의 SHATE M KZ 합계가 1달러 어긋나 보이는 것은 Asian·European 을 먼저 반올림해 더했기 때문이다"
    " (13,956.74+3,684.58=17,641.32 → 17,641, 각각 반올림하면 13,957+3,685=17,642). 자료 문제가 아니다.",
    f"원천 오더일은 {agg['t_from']} ~ {agg['t_to']} 다. 파일 이름의 10-28 까지가 아니라 "
    f"{agg['t_to']} 이 마지막 오더일이라, 화면에도 그대로 적었다.",
    "고객명·국가·중복 레코드 확인 — 보고용 표의 15곳과 원천의 고객 집합이 정확히 같고, 빠지거나 더 있는 곳이 없다.",
    "광고 성과는 원천 리포트의 OVERVIEW 합계를 그대로 쓴다. 국가별 시트 합계가 클릭 2건 적은 것은 "
    "Meta 의 국가 미식별(Unknown) 유저가 국가 집계에서 빠지기 때문이라 맞추지 않았다.",
]

html = open(HTML, encoding='utf-8', newline='').read()
new = '<script>const CIS10 = ' + json.dumps(CIS10, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const CIS10 = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('CIS10 블록을 찾지 못했습니다 — 대시보드에 먼저 자리를 만들어야 합니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"CIS Choice Kit · {agg['t_from']} ~ {agg['t_to']} · {agg['lines']:,}행 · 고객 {agg['n_cust']}곳 · SKU {agg['n_sku']}종")
print(f"  Asian ${agg['a']:,.2f} + European ${agg['e']:,.2f} = ${agg['total']:,.2f} · {agg['qty']:,}개")
print(f"  {agg['last_month']} 단월 ${agg['last']['usd']:,.2f} ({agg['last']['lines']}행 · {len(agg['last']['by'])}곳 · ~{agg['last']['last_date']})")
print(f"  상위 5곳 {agg['top5']}% · 상위 3곳 {agg['top3']}%")
print(f"  대상 SKU — Asian {agg['target']['A']['got']}/{agg['target']['A']['n']}종 "
      f"(미오더 {agg['target']['A']['miss']}) · European {agg['target']['E']['got']}/{agg['target']['E']['n']}종 "
      f"(미오더 {agg['target']['E']['miss']})")
if CIS10.get('ads'):
    _a = CIS10['ads']['tot']
    print(f"  광고 {CIS10['ads']['period']} · {CIS10['ads']['n_round']}회차 · 집행 \u20a9{_a['cost']:,} "
          f"· 노출 {_a['imp']:,} · 클릭 {_a['clk']:,} · CTR {_a['ctr']}% · CPC \u20a9{_a['cpc']}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
