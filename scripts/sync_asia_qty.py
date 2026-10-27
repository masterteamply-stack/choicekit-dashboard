#!/usr/bin/env python3
"""ASIA Sell-in 수량·품목을 제공 자료 한 장으로 다시 만든다.

  python3 scripts/sync_asia_qty.py --src <수량자료.txt|.tsv>   # 자료에서 새로 만들고 반영
  python3 scripts/sync_asia_qty.py                             # json 으로 반영만
  python3 scripts/sync_asia_qty.py --check                     # 쓰지 않고 변경 여부만

자료는 탭으로 나뉜 한 장이고 다음 열이 있어야 한다.
  Customer · Branch · Buyer code · 월(YYYY-MM) · ctr_no · old_ctr_no · 수량

예전에는 2025 는 제공 자료, 2026 은 연관 오더 원장에서 따로 뽑아 코드 체계가 달라
품목을 1:1 로 잇지 못했다. 이제 두 해가 같은 자료·같은 ctr_no 라 품목 비교가 되고,
그래서 '2026 에 처음 들어온 품목(신규)' 을 셀 수 있다.

금액은 이 자료에 없어 customer_orders.json(SAP 전 품목 오더 원장)에서 가져온다 —
ASIA 오더 금액은 대시보드 전체가 그 원장을 쓰므로 기준이 섞이지 않는다.
"""
import json, os, re, sys, csv, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
SRC = os.path.join(ROOT, 'asia_sellin_qty.json')
CO = os.path.join(ROOT, 'customer_orders.json')

COUNTRY = {'Mast': '베트남', 'Nam Bac': '베트남', 'GTA': '베트남', 'Chuan Lam': '필리핀',
           'Young Auto': '필리핀', 'ATC': '태국', 'CSH': '태국', 'GP': '태국',
           'SERI': '태국', 'PT Densocentra': '인도네시아', 'Zentralink': '인도네시아',
           'Marboro': '말레이시아'}
# 금액은 원장 고객코드로 가져온다 (scripts/sync_customer_orders.py 와 같은 표)
LEDGER = {'Mast': ['200371', '288138'], 'Nam Bac': ['200464', '288130'],
          'GTA': ['289997', '200770', '290561'], 'Chuan Lam': ['200241'],
          'Young Auto': ['200242'], 'ATC': ['200332'], 'CSH': ['200691'],
          'GP': ['288352'], 'PT Densocentra': ['288291'], 'Marboro': ['200264'],
          'SERI': ['289248'], 'Zentralink': ['200335']}

if '--src' in sys.argv:
    path = sys.argv[sys.argv.index('--src') + 1]
    with open(path, encoding='utf-8-sig') as f:
        rd = csv.reader(f, delimiter='\t')
        head = [h.strip() for h in next(rd)]
        ix = {h: i for i, h in enumerate(head)}
        for k in ('Customer', 'Branch', 'Buyer code', '월', 'ctr_no', '수량'):
            if k not in ix:
                print(f'자료에 "{k}" 열이 없습니다 — 받은 열: ' + ', '.join(h for h in head if h)); sys.exit(1)
        lines = []
        for r in rd:
            if not r or not (r[ix['Customer']] or '').strip(): continue
            try: q = float((r[ix['수량']] or '0').replace(',', ''))
            except ValueError: q = 0.0
            lines.append((r[ix['Customer']].strip(), (r[ix['Branch']] or '').strip(),
                          (r[ix['Buyer code']] or '').strip(), (r[ix['월']] or '').strip(),
                          (r[ix['ctr_no']] or '').strip(), q))
    yrs = sorted({m[:4] for _n, _b, _c, m, _s, _q in lines if m})
    if len(yrs) < 2:
        print('자료에 두 해가 다 있어야 합니다 — 찾은 해: ' + ', '.join(yrs)); sys.exit(1)
    y25, y26 = yrs[0], yrs[-1]
    M25 = sorted({m for _n, _b, _c, m, _s, _q in lines if m[:4] == y25})
    M26 = sorted({m for _n, _b, _c, m, _s, _q in lines if m[:4] == y26})
    cust = collections.OrderedDict()
    for name, br, code, m, ctr, q in lines:
        o = cust.setdefault(name, dict(k=name, country=COUNTRY.get(name, ''), br=set(),
                                       m25={x: 0.0 for x in M25}, m26={x: 0.0 for x in M26},
                                       c25=set(), c26=set()))
        o['br'].add((br, code))
        if m[:4] == y25: o['m25'][m] += q; o['c25'].add(ctr)
        elif m[:4] == y26: o['m26'][m] += q; o['c26'].add(ctr)
    led = json.load(open(CO, encoding='utf-8')) if os.path.exists(CO) else {'rows': {}}
    LM = int(M26[-1][5:7])
    def amount(name):
        t = 0.0
        for c in LEDGER.get(name, []):
            for d, v in led['rows'].get(c, {}).get('d', {}).items():
                if d[:4] == y26 and int(d[5:7]) <= LM: t += v
        return round(t)
    rows = []
    for o in cust.values():
        new = o['c26'] - o['c25']
        rows.append(dict(k=o['k'], country=o['country'],
                         branches=sorted((b if b != '-' else '-') + ' ' + c for b, c in o['br']),
                         q25=int(sum(o['m25'].values())), q26=int(sum(o['m26'].values())),
                         n25=len(o['c25']), n26=len(o['c26']), new26=len(new),
                         a26=amount(o['k']),
                         m25=[int(o['m25'][x]) for x in M25], m26=[int(o['m26'][x]) for x in M26],
                         last26=max((x for x in M26 if o['m26'][x]), default='')))
    # 업로드 경로의 해시 접두사와 'Pasted_text' 같은 임시 이름은 쓸 만한 이름으로 바꾼다
    label = re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(path))
    if '--label' in sys.argv: label = sys.argv[sys.argv.index('--label') + 1]
    elif re.match(r'(?i)pasted[_ ]?text', label): label = f'ASIA Sell-in 수량 자료 (~{M26[-1]})'
    src = dict(_readme='ASIA Sell-in 수량·품목 단일 소스. 재생성: python3 scripts/sync_asia_qty.py --src <자료>',
               source=label, asof=M26[-1], months25=M25, months26=M26,
               source_amount='customer_orders.json (SAP 전 품목 오더 원장)',
               note='두 해 모두 같은 자료·같은 ctr_no 라 품목을 1:1 로 비교할 수 있다. '
                    '그래서 2026 에 처음 들어온 품목(신규)을 센다.',
               note_amount=f'금액은 수량 자료에 없어 오더 원장에서 가져온 {y26} 1~{LM}월 값이다 — '
                           '수량과 집계 시점이 조금 다를 수 있다.',
               note_fix='GTB(551-013)는 이 수량 자료에 없어 GTA 수량에는 안 잡힌다. 금액 쪽 GTA 는 GTB 를 포함한다.',
               rows=rows)
    json.dump(src, open(SRC, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

src = json.load(open(SRC, encoding='utf-8'))
rows = sorted(src['rows'], key=lambda r: -r['q26'])
S = lambda f: sum(r[f] for r in rows)
M26 = src['months26']
tot = dict(q26=S('q26'), a26=S('a26'), q25=S('q25'), new26=S('new26'),
           m26=[sum(r['m26'][i] for r in rows) for i in range(len(M26))])
tot['ratio'] = round(tot['q26'] / tot['q25'] * 100) if tot['q25'] else None
AQ = dict(src26=src.get('source', ''), src25=src.get('source', ''),
          src_amount=src.get('source_amount', ''), asof=src['asof'],
          months26=M26, n=len(rows), rows=rows, tot=tot,
          note=src.get('note', ''), note_amount=src.get('note_amount', ''),
          note_fix=src.get('note_fix', ''))

html = open(HTML, encoding='utf-8', newline='').read()
new = '<script>const AQ = ' + json.dumps(AQ, ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const AQ = \{.*?\};</script>', re.S)
out = pat.sub(lambda _: new, html, count=1) if pat.search(html) else None
if out is None:
    print('AQ 블록을 찾지 못했습니다.'); sys.exit(1)
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"ASIA Sell-in {len(rows)}곳 · 자료 {src['source']} · ~{src['asof']}")
print(f"{'고객사':16}{'2025 수량':>11}{'2026 수량':>11}{'전년비':>7}{'25 품목':>8}{'26 품목':>8}{'신규':>7}{'2026 금액':>12}")
for r in rows:
    rt = f"{r['q26']/r['q25']*100:.0f}%" if r['q25'] else '–'
    print(f"  {r['k'][:14]:16}{r['q25']:>11,}{r['q26']:>11,}{rt:>7}{r['n25']:>8,}{r['n26']:>8,}{r['new26']:>7,}{r['a26']:>12,}")
print(f"  {'합계':14}{tot['q25']:>11,}{tot['q26']:>11,}{str(tot['ratio'])+'%':>7}{'':>8}{'':>8}{tot['new26']:>7,}{tot['a26']:>12,}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
