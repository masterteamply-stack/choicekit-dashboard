#!/usr/bin/env python3
"""고객사별 오더를 KV_Orders 원장(SAP ORD_Progress · CTR K + CTR V)에 맞춘다.

  python3 scripts/sync_customer_orders.py --html <KV_Orders_*.html>   # 원장에서 새로 뽑고 반영
  python3 scripts/sync_customer_orders.py                             # customer_orders.json 으로 반영만
  python3 scripts/sync_customer_orders.py --check                     # 쓰지 않고 변경 여부만

하는 일
 1) 원장 HTML 안의 const D 에서 고객사별 '일자' 오더(전 품목·USD 환산)를 뽑아
    customer_orders.json 으로 저장한다. 원장 HTML 자체는 저장소에 두지 않는다.
 2) asia_choicekit.json 의 오더 칸(a25·got·y25·y25t·y26t)을 원장 기준으로 다시 쓴다.
    브랜치(지점) 오더는 BRANCH 표에 따라 모(母)고객사로 합산한다.
 3) promo_dashboard_v10_6.html 의 const CD 블록에서 SteerStar 고객사의 월별 오더를
    원장 기준으로 다시 쓴다(Lordco 는 Sell-out 원장이라 건드리지 않는다).
 4) 끝으로 scripts/sync_asia.py 를 돌려 const AS 를 갱신한다.

매출(s25·s26)은 이 스크립트가 건드리지 않는다 — AM Sales 파일의 실적이 아직
9월까지라 10월 반영분이 없다. 매출은 AM 파일이 갱신되면 따로 손본다.
"""
import json, os, re, sys, datetime, collections, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CO = os.path.join(ROOT, 'customer_orders.json')
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')

# ── 고객사 → 원장 고객코드. 브랜치는 모고객사로 합산한다.
#    괄호 안은 영업 Buyer code — 고객사가 준 브랜치 표의 코드다.
ASIA = {
    'Mast':           ['200371', '288138'],              # MAST(551-006) · MAST SAIGON(551-906)
    'Nam Bac':        ['200464', '288130'],              # NAM BAC(551-008) · NAM BAC HANOI(551-908)
    'GTA':            ['289997', '200770', '290561'],    # GTA(551-021) · GTB(551-013) · GTA SG(551-022)
    'Chuan Lam':      ['200241'],                        # 510-003
    'Young Auto':     ['200242'],                        # 510-011
    'ATC':            ['200332'],                        # AUTO BUSINESS 530-001
    'CSH':            ['200691'],                        # 530-002
    'GP':             ['288352'],                        # 530-000
    'PT Densocentra': ['288291'],                        # 520-105
    'Marboro':        ['200264'],                        # 560-284
    'SERI':           ['289248'],                        # 530-004
    'Zentralink':     ['200335'],                        # 520-104
}
# LIFEPRO AUTO(551-806)는 Mast 브랜치지만 원장에 고객으로 등재돼 있지 않아 합산되지 않는다.
MISSING = {'Mast': 'LIFEPRO AUTO(551-806) 는 원장에 고객으로 없어 합산되지 않음'}

CD_CUST = {'seri': ['289248'], 'kailos': ['288503'], 'retems': ['290059'],
           'bauten': ['289381'], 'brabham': ['289060'], 'refatrix': ['289404']}
# lordco 는 Sell-out(CTRA_LO) 원장이라 이 스크립트 대상이 아니다.


def grab(s, i):
    """s[i] 의 여는 괄호에 짝이 맞는 닫는 괄호까지 잘라낸다(문자열 안의 괄호는 건너뜀)."""
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


def extract(path):
    h = open(path, encoding='utf-8', errors='replace').read()
    D = json.loads(grab(h, h.index('const D=') + len('const D=')))
    ep = datetime.date(*map(int, D['meta']['epoch'].split('-')))
    CUS, CTY, NOPACK = D['cus'], D['cty'], -99999
    keep = {c for cs in list(ASIA.values()) + list(CD_CUST.values()) for c in cs}
    per = collections.defaultdict(lambda: collections.defaultdict(float))
    info, mx = {}, ''
    for r in D['ord']:
        rd = r[2]
        if rd <= NOPACK: continue
        d = (ep + datetime.timedelta(days=rd)).isoformat()
        if d > mx: mx = d
        c = CUS[r[1]]
        if c[3] not in keep: continue
        info.setdefault(c[3], dict(name=c[0], country=CTY[c[2]]))
        per[c[3]][d] += r[9]
    rows = {k: dict(info[k], d={d: round(v, 2) for d, v in sorted(v.items())}) for k, v in per.items()}
    return dict(_readme='KV_Orders 원장(SAP ORD_Progress · CTR K + CTR V)에서 뽑은 고객사별 일자 오더. '
                        '전 품목 · USD 환산. 재생성: python3 scripts/sync_customer_orders.py --html <KV html>',
                source=D['meta'].get('srcOrder', ''), snap=D['meta'].get('snap', ''),
                gen=D['meta'].get('gen', ''), entities=sorted(D['meta'].get('entStat', {})),
                max_order_date=mx, rows=rows)


def series(src, codes):
    out = collections.defaultdict(float)
    for c in codes:
        for d, v in src['rows'].get(c, {}).get('d', {}).items():
            out[d] += v
    return out


def rng(dd, a, b):
    return round(sum(v for d, v in dd.items() if a <= d <= b))


def months(dd, year):
    m = [0.0] * 12
    for d, v in dd.items():
        if d[:4] == str(year): m[int(d[5:7]) - 1] += v
    return [round(x) for x in m]


# ── 1) 원장에서 뽑기
if '--html' in sys.argv:
    src = extract(sys.argv[sys.argv.index('--html') + 1])
    json.dump(src, open(CO, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f"원장에서 고객 {len(src['rows'])}곳 · 최종 오더일 {src['max_order_date']}")
else:
    src = json.load(open(CO, encoding='utf-8'))
MX = src['max_order_date']
L = int(MX[5:7])          # 당해 마지막 오더월

# ── 2) ASIA 초이스킷
AJ = os.path.join(ROOT, 'asia_choicekit.json')
aj = json.load(open(AJ, encoding='utf-8'))
log = []
for r in aj['rows']:
    dd = series(src, ASIA[r['k']])
    s, e = r['period'].split('~')                 # 2026.05.01~10.31
    s = s.replace('.', '-'); e = '2026-' + e.replace('.', '-')
    e = min(e, MX)                                # 원장이 닿은 날까지만
    got = rng(dd, s, e)
    a25 = rng(dd, str(int(s[:4]) - 1) + s[4:], str(int(e[:4]) - 1) + e[4:])
    m25, m26 = months(dd, 2025), months(dd, 2026)
    old = (r['a25'], r['got'], r['y26t'])
    r.update(a25=a25, got=got, y25=sum(m25), y25t=sum(m25[:L]), y26t=sum(m26[:L]),
             codes=ASIA[r['k']], m26=m26, oct=m26[9] if L >= 10 else 0)
    if MISSING.get(r['k']): r['order_note'] = MISSING[r['k']]
    log.append((r['k'], old, (a25, got, r['y26t'])))
aj['source_order'] = f"{src['source']} (스냅 {src['snap']} · 오더 ~{MX} · {'+'.join(src['entities'])})"
aj['note_order'] = ('오더는 SAP 전 품목 오더 원장 기준이고 브랜치(지점) 오더를 모고객사로 합산했다. '
                    'CTR K·CTR V 두 법인 원장이라 다른 법인을 거친 오더는 빠진다. '
                    'LIFEPRO AUTO(Mast 브랜치)는 원장에 고객으로 없어 합산되지 않음.')
aj['cut_order'] = MX
aj['last_month'] = L

# ── 3) CD 블록(SteerStar 고객사 월별 오더)
html = open(HTML, encoding='utf-8', newline='').read()
m = re.search(r'<script>const CD = (\{.*?\});</script>', html, re.S)
if not m:
    print('CD 블록을 찾지 못했습니다.'); sys.exit(1)
CD = json.loads(m.group(1))
for c in CD['custs']:
    codes = CD_CUST.get(c['id'])
    if not codes: continue
    dd = series(src, codes)
    m25, m26 = months(dd, 2025), months(dd, 2026)
    c.update(y25=m25, y26=m26, last26=L, cut=MX[:7],
             annual25=sum(m25), ytd26=sum(m26[:L]),
             cum25=sum(m25[:L]), cum26=sum(m26[:L]),
             src='KV 오더 원장(CTR K+V)')
CD['cut'] = MX[:7]
CD['src_note'] = (f"SAP 전 품목 오더 원장 {src['source']} (스냅 {src['snap']}) · 오더 ~{MX} · "
                  'Lordco 만 Sell-out 원장(CTRA_LO) 그대로')
out = html[:m.start()] + '<script>const CD = ' + json.dumps(CD, ensure_ascii=False, separators=(',', ':')) \
      + ';</script>' + html[m.end():]
changed = out != html

if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)

json.dump(aj, open(AJ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"\n원장 {src['source']} · {'+'.join(src['entities'])} · ~{MX} (1~{L}월)")
print(f"{'고객사':14}{'초이스킷 a25':>13}{'초이스킷 got':>13}{'전체 1~%d월' % L:>13}")
for k, o, n in log:
    print(f"{k:14}{o[0]:>6,}→{n[0]:>6,}{o[1]:>6,}→{n[1]:>6,}{o[2]:>6,}→{n[2]:>6,}")
print('\nasia_choicekit.json 갱신 · promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'sync_asia.py')],
                   capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())
