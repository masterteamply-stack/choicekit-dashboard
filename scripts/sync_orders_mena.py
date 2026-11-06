#!/usr/bin/env python3
"""MENA SA+BP 오더 원장(xlsx) → orders.csv 의 MENA 행 교체.

  python3 scripts/sync_orders_mena.py --src "MEA_SA_BP 2025vs2026.xlsx"
  python3 scripts/sync_orders_mena.py --src ... --check     # 쓰지 않고 대조만

왜 필요한가
  메인 대시보드는 orders.csv 로 MENA 연관 오더를 세고, 효과 분석 대시보드는
  이 xlsx(mena_sabp.json)로 셈. orders.csv 에 AL ZAIM UNITED 행이 빠져 있어
  두 화면이 $12,906 과 $23,496 으로 달랐음. 같은 원장으로 맞춤.

  MESK AL-BARARI · DYNATRADE 는 품번 단위로 이미 이 원장과 완전히 일치함 —
  빠진 곳만 들어오고 나머지는 그대로일 것임.

EURL TASSRIAA 는 건드리지 않음
  이 원장(SHOCK ABSORBER + BRAKE PAD)에 없는 고객사이고, 두 대시보드 모두
  연관 오더에서 이미 제외하고 있음(사용자 지정). orders.csv 의 그 행은
  전체 오더 쪽에서 쓰이므로 그대로 둠.
"""
import argparse, collections, csv, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSVF = os.path.join(ROOT, 'orders.csv')
KEEP = 'EURL TASSRIAA'              # 이 원장 밖 고객사 — 손대지 않음
COLS = ['CTR Code', 'order date', 'region', 'country', 'promotion_category',
        'promotion_theme', 'product', 'sku', 'part_no', 'position', 'make_model',
        'qty', 'unit_price', 'amount', 'currency', 'target', 'sell_type',
        'customer', 'Customer_No']
FIX = {'promotion_category': 'Portfolio Expansion Program',
       'promotion_theme': 'CHOICE_KIT', 'region': 'MENA',
       'target': 'B2B', 'sell_type': 'SELL-IN', 'currency': 'USD'}


def read_src(path, year):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rs = list(wb['RAW'].iter_rows(values_only=True))
    wb.close()
    h = [str(x).strip() if x is not None else '' for x in rs[0]]
    need = ('연도', '생성일', '국가(명)', '판매처', '판매처(명)', '자재(명)',
            'CTR Code', '자재', '오더 수량', '단가', '정가(USD)', '유효(수량>0)')
    miss = [k for k in need if k not in h]
    if miss:
        sys.exit('RAW 시트에 없는 열: ' + ' · '.join(miss))
    I = {k: h.index(k) for k in need}
    out = []
    for r in rs[1:]:
        if not r or not r[0]: continue
        if str(r[I['유효(수량>0)']]).strip() not in ('1', '1.0'): continue
        if str(r[I['연도']])[:4] != year: continue
        q = float(r[I['오더 수량']] or 0)
        out.append({'order date': str(r[I['생성일']])[:10],
                    'country': str(r[I['국가(명)']] or '').strip(),
                    'product': str(r[I['자재(명)']] or '').strip(),
                    'sku': str(r[I['CTR Code']] or '').strip(),
                    'part_no': str(r[I['자재']] or '').strip(),
                    'qty': int(q),
                    'unit_price': round(float(r[I['단가']] or 0), 4),
                    'amount': round(float(r[I['정가(USD)']] or 0), 2),
                    'customer': str(r[I['판매처(명)']] or '').strip(),
                    'Customer_No': str(r[I['판매처']] or '').strip()})
    return out


def num(v):
    try: return float(str(v).replace(',', '') or 0)
    except ValueError: return 0.0


def key(r):
    return (str(r['sku']).strip(), str(r['order date'])[:10], str(r['customer']).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--year', default='2026')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    old = list(csv.DictReader(open(CSVF, encoding='utf-8')))
    keep = [r for r in old if r['region'] != 'MENA'
            or (r['customer'] or '').strip().upper() == KEEP]
    mena_old = [r for r in old if r['region'] == 'MENA'
                and (r['customer'] or '').strip().upper() != KEEP]

    # 품번별 position·make_model 은 원장에 없어 orders.csv 기존 행에서 물려받음
    meta = {}
    for r in old:
        s = (r['sku'] or '').strip()
        if s and (r['position'] or r['make_model']):
            meta.setdefault(s, (r['position'], r['make_model'], r['part_no']))

    new = []
    for s in read_src(a.src, a.year):
        p, mm, pn = meta.get(s['sku'], ('', '', ''))
        r = dict(FIX)
        r.update(s)
        r['CTR Code'] = s['sku']
        r['position'], r['make_model'] = p, mm
        if pn: r['part_no'] = pn        # orders.csv 쪽 품번 표기를 유지
        new.append(r)

    A = collections.defaultdict(lambda: [0.0, 0.0])
    B = collections.defaultdict(lambda: [0.0, 0.0])
    for r in mena_old:
        v = A[key(r)]; v[0] += num(r['qty']); v[1] += num(r['amount'])
    for r in new:
        v = B[key(r)]; v[0] += num(r['qty']); v[1] += num(r['amount'])
    ks = set(A) | set(B)
    add = [k for k in ks if k not in A]
    rm = [k for k in ks if k not in B]
    chg = [k for k in ks if k in A and k in B and abs(A[k][1] - B[k][1]) > 0.01]

    print(f"MENA 행 {len(mena_old):,} → {len(new):,}  "
          f"({KEEP} {sum(1 for r in keep if r['region']=='MENA'):,} 행은 그대로 · "
          f"다른 권역 {sum(1 for r in keep if r['region']!='MENA'):,} 행도 그대로)")
    print(f"  품번×일자×고객  새로 생김 {len(add):,} · 사라짐 {len(rm):,} · 금액 바뀜 {len(chg):,}")
    if add:
        c = collections.Counter(k[2] for k in add)
        print('  새로 생긴 곳 ' + ' · '.join(f'{n} {v}건' for n, v in c.most_common())
              + f"  합계 ${sum(B[k][1] for k in add):,.2f}")
    if rm:
        c = collections.Counter(k[2] for k in rm)
        print('  사라진 곳 ' + ' · '.join(f'{n} {v}건' for n, v in c.most_common())
              + f"  합계 ${sum(A[k][1] for k in rm):,.2f}")
    oc = collections.defaultdict(float); nc = collections.defaultdict(float)
    for r in mena_old: oc[(r['customer'] or '').strip()] += num(r['amount'])
    for r in new: nc[r['customer']] += num(r['amount'])
    for n in sorted(set(oc) | set(nc)):
        print(f"  {n:<24}${oc.get(n,0):>12,.2f} → ${nc.get(n,0):>12,.2f}")
    print(f"  {'연관 오더 합계':<24}${sum(oc.values()):>12,.2f} → ${sum(nc.values()):>12,.2f}")

    if a.check: return
    rows = keep + new
    rows.sort(key=lambda r: (str(r['order date'])[:10], str(r['promotion_category']),
                             str(r['CTR Code'])))
    with open(CSVF, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    print(f"orders.csv 갱신됨 — 전체 {len(rows):,} 행")


if __name__ == '__main__':
    main()
