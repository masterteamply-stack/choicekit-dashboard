#!/usr/bin/env python3
"""중국차 오더 리포트(const CNORD)의 권역 구분만 오더라인으로 다시 깖.

  python3 scripts/sync_cn_lines_region.py --src <중국차 오더분석 xlsx>
  python3 scripts/sync_cn_lines_region.py --src <파일> --check

왜 필요한가
  CNORD 는 품번별 월별 금액을 권역으로 쪼개 들고 있는데, 그 권역이 러시아와
  우크라이나를 CIS 로 묶어 둔 값임. 그래서 p8 월별 표의 CIS 2026 합계가
  $562.0K 로 남아 있었음(바로잡으면 $209K).
  CNORD 에는 나라 정보가 없어 화면에서 고칠 수 없으므로, 오더라인에서
  품번 × 월 × 권역 금액을 다시 세어 items[*][5] 를 통째로 갈아 끼움.

바꾸는 것은 권역 쪼개기뿐
  품번·브랜드·상태(items 의 나머지 칸)와 월 목록은 건드리지 않음.
  품번별 합계가 달라지면 멈추고 알려 줌 — 원장이 서로 다른 파일이라는 뜻임.
"""
import argparse, collections, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
# scripts/sync_cn_promo.py · sync_cn_summary.py 와 같은 규칙
CTY_REGION = {'RU': 'RUS', 'UA': 'EU'}
ORDER = ['CIS', 'RUS', 'ASIA', 'MENA', 'LATAM', 'NA', 'EU', 'OC']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(a.src, read_only=True, data_only=True)
    if '오더라인_2026' not in wb.sheetnames:
        sys.exit('오더라인_2026 시트가 없음.')
    rs = wb['오더라인_2026'].iter_rows(values_only=True)
    h = [str(x) for x in next(rs)]
    need = ('월', '매칭 코드', '권역', '정가(USD)', 'Cty')
    miss = [k for k in need if k not in h]
    if miss: sys.exit('오더라인_2026 에 없는 열: ' + ' · '.join(miss))
    I = {k: h.index(k) for k in need}
    per = collections.defaultdict(float)     # (code, region, '01'~'12') → usd
    for r in rs:
        if not r or r[0] is None: continue
        code = str(r[I['매칭 코드']] or '').strip()
        if not code: continue
        reg = str(r[I['권역']] or '').strip()
        reg = CTY_REGION.get(str(r[I['Cty']] or '').strip().upper(), reg)
        mo = '%02d' % int(r[I['월']] or 0)
        per[(code, reg, mo)] += float(r[I['정가(USD)']] or 0)
    wb.close()

    html = open(HTML, encoding='utf-8', newline='').read()
    m = re.search(r'const CNORD\s*=\s*(\{.*?\});', html, re.S)
    if not m: sys.exit('CNORD 를 찾지 못했음.')
    C = json.loads(m.group(1))
    MONTHS = C['months']

    by_code = collections.defaultdict(dict)
    for (code, reg, mo), v in per.items():
        if mo not in MONTHS: continue
        by_code[code].setdefault(reg, {})[mo] = round(v, 2)

    before = collections.defaultdict(float)
    for it in C['items']:
        for rg, mm in (it[5] or {}).items(): before[rg] += sum(mm.values())

    bad, n = [], 0
    for it in C['items']:
        code = it[0]
        old = sum(sum(mm.values()) for mm in (it[5] or {}).values())
        new_split = {rg: {k: v for k, v in sorted(mm.items()) if v}
                     for rg, mm in by_code.get(code, {}).items()}
        new_split = {rg: mm for rg, mm in new_split.items() if mm}
        new = sum(sum(mm.values()) for mm in new_split.values())
        if abs(old - new) > 1.0:
            bad.append((code, round(old, 2), round(new, 2))); continue
        if new_split != it[5]: n += 1
        it[5] = {rg: new_split[rg] for rg in ORDER if rg in new_split}
    if bad:
        print('품번별 합계가 달라 멈춤 — 원장이 서로 다른 파일인 듯함:')
        for c, o, w in bad[:8]: print(f'   {c}  {o:,.2f} → {w:,.2f}')
        print(f'   … 모두 {len(bad)}건'); sys.exit(1)

    C['regions'] = [r for r in ORDER if any(r in (it[5] or {}) for it in C['items'])]
    after = collections.defaultdict(float)
    for it in C['items']:
        for rg, mm in (it[5] or {}).items(): after[rg] += sum(mm.values())

    print(f"CNORD 권역 다시 깖 · 품번 {len(C['items'])}개 중 {n}개 바뀜")
    print(f"  {'권역':<7}{'전':>13}{'후':>13}")
    for rg in sorted(set(before) | set(after), key=lambda r: -after.get(r, 0)):
        print(f"  {rg:<7}{before.get(rg,0):>13,.0f}{after.get(rg,0):>13,.0f}")
    print(f"  {'합계':<7}{sum(before.values()):>13,.0f}{sum(after.values()):>13,.0f}")

    out = html[:m.start(1)] + json.dumps(C, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)
    print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))


if __name__ == '__main__':
    main()
