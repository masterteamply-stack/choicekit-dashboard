#!/usr/bin/env python3
"""중국차 오더 리포트(const CNORD)에 월 오더 export 한 달을 더한다.

  python3 scripts/sync_cn_orders.py --cover <중국부품 브랜드정리.xlsx> --xlsx <월 export.XLSX>
  python3 scripts/sync_cn_orders.py --xlsx <월 export.XLSX>          # 커버는 cn_cover.json 재사용
  python3 scripts/sync_cn_orders.py --xlsx <...> --check             # 쓰지 않고 수치만 출력

기준 (화면 설명과 같다)
  ① 중국차 커버 전체 — 브랜드커버 파일의 CTR Code 전부
  ② 중국 전용      — 그중 'Make (except CN)' 이 '-' 인 코드
  ③ 신규 SKU 확대  — ② 중 2026-04 까지 오더 이력이 없고 5월 이후 첫 오더가 난 코드
                     (2024~2025 이력은 기존 CNORD 의 판정을 그대로 믿는다)

금액은 export 의 '정가(USD)', 월은 '생성일' 기준. 권역은 D.customers 의 고객 권역.
"""
import json, os, re, sys, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
COVER = os.path.join(ROOT, 'cn_cover.json')
REG_FIX = {'200505': 'CIS', '289087': 'EU', '200716': 'MENA',
           '200666': 'NA', '200219': 'CIS', '200697': 'CIS'}
REG_MAP = {'EUROPE': 'EU', 'OCEANIA': 'OC', 'Korea': 'KR'}


def load_cover(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h or '').strip() for h in rows[0]]
    ix = {h: i for i, h in enumerate(head)}
    for k in ('CTR Code', 'Make (only CN)', 'Make (except CN)', 'Status'):
        if k not in ix:
            print(f'커버 파일에 "{k}" 열이 없습니다.'); sys.exit(1)
    out = {}
    for r in rows[1:]:
        if not r or not r[ix['CTR Code']]: continue
        out[str(r[ix['CTR Code']]).strip()] = dict(
            cn=str(r[ix['Make (only CN)']] or '').strip(),
            ex=str(r[ix['Make (except CN)']] or '').strip(),
            st=str(r[ix['Status']] or '').strip())
    return out


def read_export(path):
    import openpyxl
    it = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True)
    head = next(it)
    ix = {str(h).strip(): i for i, h in enumerate(head) if h is not None}
    for k in ('CTR Code', '판매처', '정가(USD)', '생성일'):
        if k not in ix:
            print(f'export 에 "{k}" 열이 없습니다.'); sys.exit(1)
    out = []
    for r in it:
        if not r or not r[ix['CTR Code']]: continue
        d = r[ix['생성일']]
        d = d.date().isoformat() if isinstance(d, datetime.datetime) else str(d)[:10]
        v = r[ix['정가(USD)']]
        out.append((str(r[ix['CTR Code']]).strip(), str(r[ix['판매처']] or '').strip(),
                    float(v) if isinstance(v, (int, float)) else 0.0, d))
    return out


cover = load_cover(sys.argv[sys.argv.index('--cover') + 1]) if '--cover' in sys.argv else \
    (json.load(open(COVER, encoding='utf-8'))['codes'] if os.path.exists(COVER) else None)
if cover is None:
    print('--cover <브랜드커버 xlsx> 가 한 번은 필요합니다.'); sys.exit(1)
if '--cover' in sys.argv:
    json.dump(dict(_readme='중국차 커버 품번(브랜드커버 파일). scripts/sync_cn_orders.py 로 만든다.',
                   n=len(cover), codes=cover), open(COVER, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

ONLY = {k for k, v in cover.items() if v['ex'] in ('-', '')}

# 커버 품번의 변형 품번(CL02930P·CE0193C 처럼 같은 베이스를 쓰는 코드)도 그 커버 품번에
# 딸린 것으로 본다. 베이스 = 영문 2자 + 숫자 4자. 중국 전용·신규 판정은 베이스를 따른다.
BASE = lambda c: (re.match(r'^([A-Z]{2}\d{4})', c or '') or [None])
def base_of(c):
    m = re.match(r'^([A-Z]{2}\d{4})', c or '')
    return m.group(1) if m else None
COVBASE = {}
for _k in cover:
    _b = base_of(_k)
    if _b: COVBASE.setdefault(_b, set()).add(_k)

html = open(HTML, encoding='utf-8', newline='').read()
mC = re.search(r'const CNORD=(\{.*?\});\n', html, re.S)
mD = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
if not (mC and mD):
    print('CNORD 또는 D 블록을 찾지 못했습니다.'); sys.exit(1)
CN = json.loads(mC.group(1))
D = json.loads(mD.group(1))
REG_OF = {c['k']: REG_MAP.get(c.get('r'), c.get('r')) for c in D.get('customers', [])}
items = {it[0]: it for it in CN['items']}

if '--xlsx' not in sys.argv:
    print('--xlsx <월 export> 가 필요합니다.'); sys.exit(1)
rows = read_export(sys.argv[sys.argv.index('--xlsx') + 1])
month = max(r[3] for r in rows)[:7]
mm = month[5:7]
if mm in CN['months']:
    print(f'{month} 은(는) 이미 들어 있습니다 — 덮어씁니다.')

per = collections.defaultdict(float)      # (code, region) -> usd
loose = {}        # 변형 품번 -> 딸린 커버 품번들
for code, cu, usd, d in rows:
    if code not in cover:
        kin = COVBASE.get(base_of(code))
        if not kin: continue
        loose[code] = sorted(kin)
    if d[:7] != month: continue
    rg = REG_FIX.get(cu) or REG_OF.get(cu)
    if not rg or rg == 'KR': continue       # 화면 권역 목록에 KR 은 없다
    per[(code, rg)] += usd

# 새 품번은 항목으로 추가 — 2026 에 처음 오더가 난 코드다.
for (code, rg) in per:
    if code not in items:
        kin = loose.get(code)
        v = cover[code] if code in cover else cover[kin[0]]
        is_only = (code in ONLY) if code in cover else all(k in ONLY for k in kin)
        it = [code, 1 if is_only else 0, 0, v['cn'], v['st'], {}]
        items[code] = it; CN['items'].append(it)
        # 2026-04 까지 오더가 없었으니, 중국 전용이면 신규 전환으로 본다
        if it[1] == 1 and int(mm) >= 5: it[2] = 1
for it in CN['items']:
    for rg in list(it[5]): it[5][rg].pop(mm, None)
for (code, rg), v in per.items():
    items[code][5].setdefault(rg, {})[mm] = round(v, 2)
if mm not in CN['months']:
    CN['months'] = sorted(set(CN['months']) | {mm})
CN['src_month'] = month

S = lambda pred: round(sum(v for (c, r), v in per.items() if pred(c)), 2)
lo = round(sum(v for (c, r), v in per.items() if c in loose), 2)
print(f"{month} · export {len(rows):,}행 · 커버 품번 {len(cover)}개 · 변형 품번 {len(loose)}개(+{lo:,.2f})")
print(f"  ① 중국차 커버 전체 : {S(lambda c: True):>12,.2f}")
print(f"  ② 중국 전용        : {S(lambda c: c in ONLY):>12,.2f}")
print(f"  ③ 신규 SKU 확대    : {S(lambda c: items[c][2] == 1):>12,.2f}")
print(f"  오더 발생 품번 {len({c for c, r in per})}개 · 신규 추가 품번 "
      f"{len([c for c, r in per if not any(m for rgm in items[c][5].values() for m in rgm if m != mm)])}개")

out = html[:mC.start()] + 'const CNORD=' + json.dumps(CN, ensure_ascii=False, separators=(',', ':')) + ';\n' + html[mC.end():]
changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
