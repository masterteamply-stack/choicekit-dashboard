#!/usr/bin/env python3
"""PLUSCAR 월별 Sell-out 스냅샷 → const PLSO.

  python3 scripts/sync_pluscar_sellout.py --src <PlusCar_..._sell-out_data.xlsx>
  python3 scripts/sync_pluscar_sellout.py            # pluscar_sellout.json 으로 반영만
  python3 scripts/sync_pluscar_sellout.py ... --check

자료는 품번(CODIGOS) × 스냅 날짜별 수량(CANTIDADES) 한 장임.
머리글의 날짜를 그대로 스냅 이름으로 씀 — 달 이름을 붙이지 않음.

기존 PLUSCAR 카드의 '2024·2025·2026 각 8월' 비교와는 구간이 다름.
그쪽은 해마다 8월 한 달, 이쪽은 올해 세 번의 스냅임. 섞지 않음.
프로모션 대상 품목 구분은 이 자료에 없어 전체 수량만 셈.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'pluscar_sellout.json')


def read(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    # 날짜가 들어 있는 첫 행에서 스냅 열을 찾음
    hi = next((i for i, r in enumerate(rows[:5]) if sum(1 for v in r if hasattr(v, 'year')) >= 2), None)
    if hi is None:
        print('스냅 날짜 행을 찾지 못했음.'); sys.exit(1)
    cols = [i for i, v in enumerate(rows[hi]) if hasattr(v, 'year')]
    snaps = [rows[hi][i].date().isoformat() for i in cols]
    ci = next((i for i, v in enumerate(rows[hi + 1]) if str(v or '').strip().upper().startswith('CODIGO')), None)
    if ci is None:
        print('CODIGOS 열을 찾지 못했음.'); sys.exit(1)
    data = []
    for r in rows[hi + 2:]:
        c = r[ci] if ci < len(r) else None
        if not c or str(c).strip().lower().startswith('total'): continue
        data.append((str(c).strip(), [float(r[i] or 0) if i < len(r) else 0.0 for i in cols]))
    return snaps, data


if '--src' in sys.argv:
    src = sys.argv[sys.argv.index('--src') + 1]
    snaps, data = read(src)
    n = len(snaps)
    tot = [int(sum(d[1][i] for d in data)) for i in range(n)]
    sku = [sum(1 for d in data if d[1][i] > 0) for i in range(n)]
    last, prev = n - 1, n - 2
    movers = sorted(data, key=lambda d: -(d[1][last] - d[1][prev]))[:10]
    tops = sorted(data, key=lambda d: -d[1][last])[:10]
    new_last = [d[0] for d in data if d[1][last] > 0 and all(d[1][i] == 0 for i in range(last))]
    agg = dict(_readme='PLUSCAR 품번별 Sell-out 스냅샷. '
                       '재생성: python3 scripts/sync_pluscar_sellout.py --src <xlsx>',
               src=re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(src)),
               snaps=snaps, n_sku_rows=len(data), tot=tot, sku=sku,
               movers=[{'k': k, 'v': [int(x) for x in v]} for k, v in movers],
               tops=[{'k': k, 'v': [int(x) for x in v]} for k, v in tops],
               n_new=len(new_last),
               note='스냅 날짜는 자료 머리글 그대로임. 달 한 달치가 아니라 그 시점의 집계라 '
                    '위 연도별 8월 비교와 구간이 다름 — 섞지 않음.',
               note_scope='이 자료에는 프로모션 대상 품목 구분이 없어 전체 수량만 셈.')
    json.dump(agg, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    agg = json.load(open(OUT, encoding='utf-8'))

html = open(HTML, encoding='utf-8', newline='').read()
blk = '<script>const PLSO = ' + json.dumps(
    {k: v for k, v in agg.items() if not k.startswith('_')},
    ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const PLSO = \{.*?\};</script>', re.S)
if pat.search(html):
    out = pat.sub(lambda _: blk, html, count=1)
else:
    anchor = '<script>const CIS10 = '
    if anchor not in html:
        print('PLSO 자리를 만들 기준(const CIS10)을 찾지 못했음.'); sys.exit(1)
    out = html.replace(anchor, blk + '\n' + anchor, 1)

changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"PLUSCAR Sell-out · 자료 {agg['src']} · 품번 {agg['n_sku_rows']:,}행")
for i, s in enumerate(agg['snaps']):
    print(f"  {s}  수량 {agg['tot'][i]:>8,}  판매 SKU {agg['sku'][i]:>5,}")
print(f"  마지막 스냅에 처음 팔린 품번 {agg['n_new']}개")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
