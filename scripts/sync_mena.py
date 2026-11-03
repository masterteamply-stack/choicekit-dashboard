#!/usr/bin/env python3
"""MENA Portfolio Expansion Program (SHOCK ABSORBER + BRAKE PAD) 단일 소스.

  python3 scripts/sync_mena.py --src <MEA_SA_BP_...xlsx>   # 원본에서 새로 뽑고 반영
  python3 scripts/sync_mena.py                             # mena_sabp.json 으로 반영만
  python3 scripts/sync_mena.py ... --check                 # 쓰지 않고 수치만

왜 이 스크립트가 필요한가
  연관 오더 원장(orders.csv)의 MENA 분에 2025 BRAKE PAD 오더가 빠져 있었다.
  그래서 전년이 SHOCK ABSORBER $2,770 만으로 잡혀 YoY 가 +365.9% 로 부풀었다.
  같은 1~10월로 맞추면 $12,719 → $23,496 (+84.7%) 다. 이 파일이 두 제품·두 해를
  한 장에 담은 원본이라 여기서 다시 센다.

두 가지 구간을 따로 둔다 — 섞으면 안 된다
  ① 1~10월 전체      a25 / a26  — 10월 AL ZAIM 오더가 들어간 값
  ② 캠페인 동일 구간  d25 / d26  — 2026-01-13~09-22 와 2025 같은 날짜 구간
  화면의 '전년 동기' 는 ① 이고, 월별 지속성 차트(mser)는 ② 다.

건드리지 않는 것
  d25/d26 는 대조군 분석(did)에도 쓰이지만 MENA 는 n_ctrl=0 · incr=null 이라
  그 집계에서 빠진다. 그래서 값을 바로잡아도 다른 권역 수치에 영향이 없다.
"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'mena_sabp.json')
KEY = ('MENA', 'Portfolio Expansion Program')
LM = 10                                   # 비교 기준월 — 두 해 모두 1~10월


def read(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)['RAW']
    rows = list(ws.iter_rows(values_only=True))
    h = [str(x).strip() if x is not None else '' for x in rows[0]]
    ix = {v: i for i, v in enumerate(h) if v}
    need = ['연도', '월', '생성일', '국가(명)', '판매처', '판매처(명)',
            '자재(명)', 'CTR Code', '오더 수량', '정가(USD)', '유효(수량>0)']
    miss = [k for k in need if k not in ix]
    if miss:
        print('RAW 시트에 없는 열: ' + ', '.join(miss)); sys.exit(1)
    out = []
    for r in rows[1:]:
        if not r or r[ix['연도']] is None or not int(r[ix['유효(수량>0)']] or 0): continue
        d = r[ix['생성일']]
        d = d.date() if isinstance(d, datetime.datetime) else None
        out.append(dict(y=int(r[ix['연도']]), m=int(r[ix['월']]), d=d,
                        code=str(r[ix['판매처']]).strip(), cust=str(r[ix['판매처(명)']]).strip(),
                        cty=str(r[ix['국가(명)']]).strip(), prod=str(r[ix['자재(명)']]).strip(),
                        ctr=str(r[ix['CTR Code']]).strip(),
                        qty=float(r[ix['오더 수량']] or 0), usd=float(r[ix['정가(USD)']] or 0)))
    return out


def sum2(rows, pick):
    """pick(row) 이 참인 행을 연도별로 더한다."""
    g = collections.defaultdict(float)
    for r in rows:
        if pick(r): g[r['y']] += r['usd']
    return round(g.get(2025, 0), 2), round(g.get(2026, 0), 2)


if '--src' in sys.argv:
    src = sys.argv[sys.argv.index('--src') + 1]
    R = read(src)
    ytd = lambda r: r['m'] <= LM
    a25, a26 = sum2(R, ytd)

    cust = collections.defaultdict(lambda: dict(y25=0.0, y26=0.0, q25=0, q26=0, cty='', code=''))
    for r in R:
        if not ytd(r): continue
        o = cust[r['cust']]; o['cty'] = o['cty'] or r['cty']; o['code'] = o['code'] or r['code']
        o['y%d' % (r['y'] % 100)] += r['usd']; o['q%d' % (r['y'] % 100)] += r['qty']
    custs = sorted(({'k': k, 'code': v['code'], 'country': v['cty'],
                     'a25': round(v['y25'], 2), 'a26': round(v['y26'], 2),
                     'q25': int(v['q25']), 'q26': int(v['q26'])}
                    for k, v in cust.items()), key=lambda x: -x['a26'])

    prod = collections.defaultdict(lambda: dict(y25=0.0, y26=0.0, q25=0, q26=0, s25=set(), s26=set()))
    for r in R:
        if not ytd(r): continue
        o = prod[r['prod']]
        o['y%d' % (r['y'] % 100)] += r['usd']; o['q%d' % (r['y'] % 100)] += r['qty']
        o['s%d' % (r['y'] % 100)].add(r['ctr'])
    prods = sorted(({'k': k, 'a25': round(v['y25'], 2), 'a26': round(v['y26'], 2),
                     'q25': int(v['q25']), 'q26': int(v['q26']),
                     'n25': len(v['s25']), 'n26': len(v['s26'])}
                    for k, v in prod.items()), key=lambda x: -x['a26'])

    mon = {y: [0.0] * 12 for y in (2025, 2026)}
    for r in R:
        if ytd(r): mon[r['y']][r['m'] - 1] += r['usd']
    months = [{'m': i + 1, 'a25': round(mon[2025][i], 2), 'a26': round(mon[2026][i], 2)}
              for i in range(LM)]

    # 마지막 달(10월)에 오더가 난 고객 — 화면에서 '이달 추가분' 을 누가 냈는지 적는다
    lastby = collections.defaultdict(float)
    for r in R:
        if r['y'] == 2026 and r['m'] == LM: lastby[r['cust']] += r['usd']
    last_by = [{'k': k, 'usd': round(v, 2)} for k, v in sorted(lastby.items(), key=lambda x: -x[1])]

    s25 = {r['ctr'] for r in R if r['y'] == 2025 and ytd(r)}
    s26 = {r['ctr'] for r in R if r['y'] == 2026 and ytd(r)}
    top = collections.defaultdict(lambda: [0.0, 0.0, 0, ''])
    for r in R:
        if not ytd(r): continue
        t = top[r['ctr']]; t[0 if r['y'] == 2025 else 1] += r['usd']
        t[2] += int(r['qty']) if r['y'] == 2026 else 0; t[3] = r['prod']
    top_sku = [{'k': k, 'a25': round(v[0], 2), 'a26': round(v[1], 2), 'q26': v[2], 'p': v[3],
                'new': k not in s25}
               for k, v in sorted(top.items(), key=lambda x: -x[1][1])[:12]]

    agg = dict(_readme='MENA SHOCK ABSORBER + BRAKE PAD 오더 단일 소스. '
                       '재생성: python3 scripts/sync_mena.py --src <xlsx>',
               src=re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(src)), last_month=LM,
               a25=a25, a26=a26, yoy=round((a26 - a25) / a25 * 100, 1) if a25 else None,
               q25=int(sum(r['qty'] for r in R if r['y'] == 2025 and ytd(r))),
               q26=int(sum(r['qty'] for r in R if r['y'] == 2026 and ytd(r))),
               n_sku25=len(s25), n_sku26=len(s26), n_new=len(s26 - s25),
               custs=custs, prods=prods, months=months, top_sku=top_sku, last_by=last_by,
               n_cust=len(custs), n_cty=len({c['country'] for c in custs if c['country']}),
               note_basis=f'두 해 모두 1~{LM}월 같은 구간이다. 전년이 SHOCK ABSORBER 만 잡혀 있던 것을 '
                          'BRAKE PAD 까지 넣어 바로잡았다.')
    json.dump(agg, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    agg = json.load(open(OUT, encoding='utf-8'))
    R = None

html = open(HTML, encoding='utf-8', newline='').read()
m = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
if not m:
    print('D 블록을 찾지 못했습니다.'); sys.exit(1)
D = json.loads(m.group(1))
camp = next((c for c in D['campaigns'] if (c.get('region'), c.get('program')) == KEY), None)
if not camp:
    print('MENA 캠페인을 찾지 못했습니다.'); sys.exit(1)

old = (camp.get('a25'), camp.get('a26'), camp.get('yoy'))
camp['a25'] = camp['all25'] = agg['a25']
camp['a26'] = agg['a26']
camp['q25'], camp['q26'] = agg['q25'], agg['q26']
camp['s25'], camp['s26'] = agg['n_sku25'], agg['n_sku26']
camp['yoy'] = camp['yoyA'] = agg['yoy']
camp['basis'] = f"두 해 모두 1~{agg['last_month']}월 · SHOCK ABSORBER + BRAKE PAD · 자료 {agg['src']}"
# 오더가 난 SKU·고객·국가도 원장이 아니라 이 원본 기준으로 맞춘다
camp['ord_sku'] = agg['n_sku26']
camp['n_cust'] = agg['n_cust']
camp['loc'] = f"{agg['n_cty']}개국"

# ── 캠페인 동일 구간(d25/d26)과 월별 지속성(mser) 도 같은 원본으로 다시 센다.
#    구간은 wins 의 첫 칸(2026-01-13~09-22)과 전년 같은 날짜.
if R is not None and camp.get('wins'):
    w0, w1 = camp['wins'][0]
    f = lambda y: (datetime.date(y, *map(int, w0[5:].split('-'))),
                   datetime.date(y, *map(int, w1[5:].split('-'))))
    win = {y: f(y) for y in (2025, 2026)}
    inw = lambda r: r['d'] is not None and win[r['y']][0] <= r['d'] <= win[r['y']][1]
    d25, d26 = sum2(R, inw)
    camp['d25'], camp['d26'] = d25, d26
    camp['dyoy'] = round((d26 - d25) / d25 * 100, 1) if d25 else None
    wm = {y: [0.0] * 12 for y in (2025, 2026)}
    for r in R:
        if inw(r): wm[r['y']][r['m'] - 1] += r['usd']
    ser = []
    for i in range(12):
        p, c = round(wm[2025][i], 1), round(wm[2026][i], 1)
        if not p and not c: continue
        old_e = next((x for x in camp.get('mser', []) if int(x['m'][5:]) == i + 1), {})
        ser.append(dict(m='2026-%02d' % (i + 1), cur=c, prv=p,
                        yoy=(round((c - p) / p * 100, 1) if p else None),
                        days=old_e.get('days', 0), mdays=old_e.get('mdays', 30)))
    camp['mser'] = ser

# ── 고객사별 전년(cust_delta)
touched = []
by_code = {c['code']: c for c in agg['custs']}
for r in D.get('cust_delta', []):
    if (r.get('region'), r.get('program')) != KEY: continue
    s = by_code.get(str(r.get('code', '')))
    if not s: continue
    if r.get('a25') != s['a25'] or r.get('a26') != s['a26']:
        touched.append((r['name'], r.get('a25'), s['a25']))
    r['a25'], r['a26'] = s['a25'], s['a26']

out = html[:m.start(1)] + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]

# ── 블록용 const MENA10
blk = '<script>const MENA10 = ' + json.dumps(
    {k: v for k, v in agg.items() if not k.startswith('_')},
    ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const MENA10 = \{.*?\};</script>', re.S)
if pat.search(out):
    out = pat.sub(lambda _: blk, out, count=1)
else:
    anchor = '<script>const CIS10 = '
    if anchor not in out:
        print('MENA10 자리를 만들 기준(const CIS10)을 찾지 못했습니다.'); sys.exit(1)
    out = out.replace(anchor, blk + '\n' + anchor, 1)

changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"MENA SA+BP · 자료 {agg['src']} · 1~{agg['last_month']}월")
print(f"  오더  {old[0]:,.2f} → {agg['a25']:,.2f} (전년) · {old[1]:,.2f} → {agg['a26']:,.2f} (당해)")
print(f"  YoY   {old[2]:+.1f}% → {agg['yoy']:+.1f}%   ← 전년에 BRAKE PAD 가 빠져 있던 것을 바로잡음")
if R is not None:
    print(f"  동일 구간 {camp['d25']:,.2f} → {camp['d26']:,.2f} ({camp['dyoy']:+.1f}%) · {camp['wins'][0][0]}~{camp['wins'][0][1]}")
print(f"  수량 {agg['q25']:,} → {agg['q26']:,} · SKU {agg['n_sku25']} → {agg['n_sku26']} (신규 {agg['n_new']})")
for p in agg['prods']:
    print(f"  {p['k']:<18} {p['a25']:>10,.2f} → {p['a26']:>10,.2f}")
for c in agg['custs']:
    print(f"  {c['k'][:26]:<28}{c['country']:<8}{c['a25']:>10,.2f} → {c['a26']:>10,.2f}")
if touched:
    print('  고객사별 전년 보정: ' + ', '.join(f'{n} {o:,.0f}→{v:,.0f}' for n, o, v in touched))
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
