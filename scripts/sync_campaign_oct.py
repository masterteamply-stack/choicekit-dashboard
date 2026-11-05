#!/usr/bin/env python3
"""캠페인 고객사의 10월 전 품목 오더 → const COCT.

  python3 scripts/sync_campaign_oct.py --html <KV 오더 원장 html>
  python3 scripts/sync_campaign_oct.py              # campaign_oct_orders.json 으로 반영만
  python3 scripts/sync_campaign_oct.py ... --check

왜 '기간 오더' 칸을 덮지 않나
  캠페인 행의 전년·당해(a25/a26)는 캠페인마다 집계 범위가 다름 — CIS 는 대상 SKU
  133·188종, LATAM MarketFit 은 26종, ASIA 는 Sell-out 태그, NA·KR·LATAM Sell-out
  은 전 품목. 오더 원장은 오더 헤더 단위라 품번으로 자를 수 없어 그 칸에 넣으면
  기준이 섞임. 그래서 전 품목 10월 오더는 별도 칸으로만 둠.

겹치는 고객사
  CIS Asian·European 처럼 한 고객사가 두 캠페인에 같이 들어감. 캠페인별 값을 그냥
  더하면 중복이라, 고객사 단위 값(cust)과 캠페인별 고객 코드(codes)를 같이 넘겨
  화면에서 합계는 코드 합집합으로 계산하게 함.
"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'campaign_oct_orders.json')


def grab(s, i):
    d = 0; q = None; j = i
    while j < len(s):
        c = s[j]
        if q:
            if c == '\\': j += 2; continue
            if c == q: q = None
        else:
            if c in '"\'': q = c
            elif c in '{[': d += 1
            elif c in '}]':
                d -= 1
                if d == 0: return s[i:j + 1]
        j += 1
    raise ValueError('괄호가 닫히지 않음')


def read_kv(path, want=None):
    """want='2026-10' 이면 그 달치. 안 주면 '마지막 완결월'.

    원장이 달 중간에서 끊기면(11/03 스냅) 그 달을 집계월로 잡으면 안 됨 —
    며칠치가 한 달처럼 보임. 그래서 기본값은 끝난 달까지만 봄.
    """
    import calendar
    h = open(path, encoding='utf-8', errors='replace').read()
    K = json.loads(grab(h, h.index('const D=') + len('const D=')))
    ep = datetime.date(*map(int, K['meta']['epoch'].split('-')))
    mx = ''
    per = collections.defaultdict(lambda: [0.0, 0.0])
    seen = set()
    rows = []
    for r in K['ord']:
        if r[2] <= -99999: continue
        d = (ep + datetime.timedelta(days=r[2])).isoformat()
        if d > mx: mx = d
        rows.append((d, K['cus'][r[1]][3], r[9], r[7]))
        seen.add(K['cus'][r[1]][3])
    if want:
        mon = want
    else:
        y, m = int(mx[:4]), int(mx[5:7])
        if int(mx[8:10]) < calendar.monthrange(y, m)[1]:
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        mon = '%d-%02d' % (y, m)
    cut = min(mx, '%s-%02d' % (mon, calendar.monthrange(int(mon[:4]), int(mon[5:7]))[1]))
    ytd = collections.defaultdict(lambda: [0.0, 0.0])   # 그 해 1월~마감월 누계
    for d, code, usd, qty in rows:
        if d[:7] == mon:
            v = per[code]; v[0] += usd; v[1] += qty
        if d[:4] == mon[:4] and d <= cut:
            v = ytd[code]; v[0] += usd; v[1] += qty
    return per, ytd, cut, mon, seen, {c[0].strip(): c[3] for c in K['cus']}


html = open(HTML, encoding='utf-8', newline='').read()
m = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
if not m:
    print('D 블록을 찾지 못했음.'); sys.exit(1)
D = json.loads(m.group(1))

if '--html' in sys.argv:
    _w = sys.argv[sys.argv.index('--month') + 1] if '--month' in sys.argv else None
    per, ytd, cut, mon, seen, byname = read_kv(sys.argv[sys.argv.index('--html') + 1], _w)
    rows, cust = [], {}
    for c in D['campaigns']:
        if not c.get('started'): continue
        cds = [r for r in D.get('cust_delta', [])
               if r.get('region') == c['region'] and r.get('program') == c['program']]
        codes, miss = [], []
        for r in cds:
            code = str(r.get('code') or '') or byname.get((r.get('name') or '').strip(), '')
            if not code or code not in seen:
                miss.append(r.get('name', '')); continue
            codes.append(code)
            v, w = per.get(code), ytd.get(code)
            if (v and v[0]) or (w and w[0]):
                # [그 달 USD, 그 달 수량, 고객명, 누계 USD, 누계 수량]
                cust[code] = [round((v or [0, 0])[0], 2), int((v or [0, 0])[1]),
                              (r.get('name') or '').strip(),
                              round((w or [0, 0])[0], 2), int((w or [0, 0])[1])]
        codes = sorted(set(codes))
        usd = sum(per.get(k, [0, 0])[0] for k in codes)
        qty = sum(per.get(k, [0, 0])[1] for k in codes)
        yu = sum(ytd.get(k, [0, 0])[0] for k in codes)
        yq = sum(ytd.get(k, [0, 0])[1] for k in codes)
        rows.append(dict(region=c['region'], program=c['program'], codes=codes,
                         n_cust=len(cds), n_miss=len(miss), miss=miss[:6],
                         usd=round(usd, 2), qty=int(qty),
                         ytd=round(yu, 2), ytd_qty=int(yq)))
    agg = dict(_readme='캠페인 고객사의 전 품목 오더 — 그 달치(usd)와 그 해 누계(ytd) 둘 다. '
                       '캠페인 행의 전년·당해와 집계 범위가 달라 같은 칸에 넣지 않음. '
                       '캠페인별 값은 고객사가 겹쳐 단순 합산 금지 — 합계는 codes 합집합으로 계산함. '
                       '재생성: python3 scripts/sync_campaign_oct.py --html <KV 원장 html>',
               month=mon, cut=cut, rows=rows, cust=cust,
               ytd_from='%s-01' % mon[:4],
               basis='전 품목 오더 원장 · 캠페인 참여 고객사만',
               note='대상 SKU로 좁힌 캠페인 실적과는 집계 범위가 다름 — 더하지 않음.')
    json.dump(agg, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    agg = json.load(open(OUT, encoding='utf-8'))

idx = {(r['region'], r['program']): r for r in agg['rows']}
for c in D['campaigns']:
    r = idx.get((c.get('region'), c.get('program')))
    if not r: continue
    c['oct_all'] = r['usd']
    c['oct_all_q'] = r['qty']
    c['oct_all_n'] = len(r['codes'])
    c['ytd_all'] = r.get('ytd')
    c['ytd_all_q'] = r.get('ytd_qty')

out = html[:m.start(1)] + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
blk = '<script>const COCT = ' + json.dumps(
    {k: v for k, v in agg.items() if not k.startswith('_')},
    ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const COCT = \{.*?\};</script>', re.S)
if pat.search(out):
    out = pat.sub(lambda _: blk, out, count=1)
else:
    anchor = '<script>const CIS10 = '
    if anchor not in out:
        print('COCT 자리를 만들 기준(const CIS10)을 찾지 못했음.'); sys.exit(1)
    out = out.replace(anchor, blk + '\n' + anchor, 1)

changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"캠페인 고객사 전 품목 오더 · 원장 ~{agg['cut']}")
print(f"  {'':<34}{agg['month'][5:]+'월':>12}{'1~'+agg['month'][5:]+'월 누계':>16}")
for r in sorted(agg['rows'], key=lambda x: -(x.get('ytd') or 0)):
    note = f"  (고객 {r['n_cust']}곳 중 {r['n_miss']}곳 원장 밖)" if r['n_miss'] else ''
    print(f"  {r['region']:<6}{r['program'][:26]:<28}{r['usd']:>12,.0f}{r.get('ytd',0):>16,.0f}{note}")
uni = sorted({k for r in agg['rows'] for k in r['codes']})
tot = sum(agg['cust'].get(k, [0, 0, '', 0])[0] for k in uni)
yt = sum((agg['cust'].get(k) or [0, 0, '', 0])[3] for k in uni)
print(f"  {'합계 (고객사 중복 제거)':<32}{tot:>12,.0f}{yt:>16,.0f}  고객 {len(uni)}곳")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
