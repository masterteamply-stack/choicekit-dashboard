#!/usr/bin/env python3
"""중국차 오더 분석 파일의 '요약' 시트 → const CNSUM.

  python3 scripts/sync_cn_summary.py --src <중국차오더분석_2026_r5.xlsx>
  python3 scripts/sync_cn_summary.py            # cn_summary.json 으로 반영만
  python3 scripts/sync_cn_summary.py ... --check

p8(중국차 오더 리포트)의 월별 3기준 표는 이미 이 파일과 같은 수치임.
여기서는 그 표에 없는 것만 가져옴 — 2025 대비, 권역별, 차종, 부품 종류별.

요약 시트는 이미 집계된 표라 그대로 읽음. 오더라인 시트를 다시 세지 않음.
파일의 '대시보드대조' 시트가 1~9월 원본 재집계와 화면값이 같음을 보여 준다(차이 0).
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'cn_summary.json')
NUM = lambda v: float(v) if isinstance(v, (int, float)) else 0.0


def grid(path):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)['요약']
    return [list(r) for r in ws.iter_rows(values_only=True)]


def find(G, text, col=0):
    for i, r in enumerate(G):
        v = r[col] if col < len(r) else None
        if v and text in str(v): return i
    return -1


def table(G, start, cols):
    """머리글 다음 행부터 첫 열이 빌 때까지 읽음."""
    out = []
    for r in G[start:]:
        k = r[0] if r else None
        if k is None or str(k).strip() == '': break
        out.append([r[i] if i < len(r) else None for i in cols])
    return out


if '--src' in sys.argv:
    src = sys.argv[sys.argv.index('--src') + 1]
    G = grid(src)

    # 2. 월별 2025 vs 2026 — '기준 | 연도 | 1..12월 | 1~10월 합계 | 연간 합계'
    i = find(G, '기준')
    hdr = -1
    for j, r in enumerate(G):
        if r and str(r[0] or '').strip() == '기준' and str((r[1] if len(r) > 1 else '') or '').strip() == '연도':
            hdr = j; break
    if hdr < 0:
        print("'기준 | 연도' 머리글을 찾지 못했음."); sys.exit(1)
    series, cur = [], None
    for r in G[hdr + 1:]:
        a = str(r[0] or '').strip(); b = str(r[1] or '').strip()
        if a and '기준' in a and not b: break
        if a: cur = a
        if not cur or b not in ('2025', '2026'): continue
        series.append(dict(k=cur, y=int(b), m=[round(NUM(r[2 + x]), 2) for x in range(12)],
                           ytd=round(NUM(r[14]), 2) if len(r) > 14 else 0.0))
        if len(series) > 12: break

    def region_tbl(title, cols):
        s = find(G, title)
        if s < 0: return []
        h = next((j for j in range(s, min(s + 6, len(G)))
                  if G[j] and str(G[j][0] or '').strip() == '권역'), -1)
        if h < 0: return []
        rows = []
        for r in G[h + 1:]:
            k = str(r[0] or '').strip()
            if not k: break
            if k == '합계': break
            # 비율 열(share·yoy)은 원본이 소수라 퍼센트로 맞춤 — 차종·부품 표와 같은 단위
            d = {}
            for c, i in cols.items():
                v = r[i] if i < len(r) else None
                if isinstance(v, (int, float)):
                    v = round(v * 100, 1) if c.startswith(('share', 'yoy')) else round(v, 2)
                d[c] = v
            rows.append(d | {'k': k})
        return rows

    regions = region_tbl('3a.', {'a26': 1, 'share': 2, 'q26': 3, 'cust': 4, 'sku': 5,
                                 'a25': 6, 'share25': 7, 'yoy': 8, 'cust25': 9})
    regions_cn = region_tbl('3b.', {'a26': 1, 'share': 2, 'q26': 3, 'cust': 4, 'sku': 5,
                                    'a25': 6, 'share25': 7, 'yoy': 8, 'cust25': 9,
                                    'new26': 10, 'new_cust': 11})

    # 4. 차종 Top — 머리글 행을 바로 찾는다('4.' 로 앵커를 잡으면 다른 셀에 걸림)
    h = next((j for j, r in enumerate(G)
              if r and str(r[0] or '').strip() == '차종'), -1)
    models = []
    if h >= 0:
        for r in G[h + 1:]:
            k = str(r[0] or '').strip()
            if not k or k == '합계': break
            models.append(dict(k=k, a26=round(NUM(r[1]), 2), q26=int(NUM(r[2])),
                               parts=str(r[3] or ''), a25=round(NUM(r[4]), 2),
                               yoy=(round(NUM(r[5]) * 100, 1) if isinstance(r[5], (int, float)) else None),
                               plist=str(r[6] or '')))

    # 5. 부품 종류별
    h = next((j for j, r in enumerate(G)
              if r and '부품 종류' in str(r[0] or '')), -1)
    parts = []
    if h >= 0:
        for r in G[h + 1:]:
            k = str(r[0] or '').strip()
            if not k or k == '합계': break
            if not NUM(r[1]) and not NUM(r[5]): continue
            parts.append(dict(k=k, a26=round(NUM(r[1]), 2), share=round(NUM(r[2]) * 100, 1),
                              q26=int(NUM(r[3])), sku=int(NUM(r[4])), a25=round(NUM(r[5]), 2),
                              yoy=(round(NUM(r[7]) * 100, 1) if isinstance(r[7], (int, float)) else None)))

    agg = dict(_readme='중국차 2026 오더 분석 요약 시트에서 읽은 값. '
                       '재생성: python3 scripts/sync_cn_summary.py --src <xlsx>',
               src=re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(src)),
               series=series, regions=regions, regions_cn=regions_cn,
               models=models[:15], parts=parts,
               note='월별 3기준 표(위)와 같은 자료임. 여기에는 그 표에 없는 2025 대비·권역·차종·부품만 둠.')
    json.dump(agg, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
else:
    agg = json.load(open(OUT, encoding='utf-8'))

html = open(HTML, encoding='utf-8', newline='').read()
blk = '<script>const CNSUM = ' + json.dumps(
    {k: v for k, v in agg.items() if not k.startswith('_')},
    ensure_ascii=False, separators=(',', ':')) + ';</script>'
pat = re.compile(r'<script>const CNSUM = \{.*?\};</script>', re.S)
if pat.search(html):
    out = pat.sub(lambda _: blk, html, count=1)
else:
    anchor = '<script>const CIS10 = '
    if anchor not in html:
        print('CNSUM 자리를 만들 기준을 찾지 못했음.'); sys.exit(1)
    out = html.replace(anchor, blk + '\n' + anchor, 1)

changed = out != html
if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"중국차 요약 · 자료 {agg['src']}")
for s in agg['series']:
    print(f"  {s['k'][:22]:<24}{s['y']}  1~10월 {s['ytd']:>14,.2f}")
print(f"  권역 {len(agg['regions'])}개 · 중국전용 권역 {len(agg['regions_cn'])}개 "
      f"· 차종 {len(agg['models'])}개 · 부품 {len(agg['parts'])}종")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
