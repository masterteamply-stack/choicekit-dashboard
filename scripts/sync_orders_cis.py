#!/usr/bin/env python3
"""CIS Choice Kit 오더 원자료(xlsx) → orders.csv 의 CIS 행 교체.

  python3 scripts/sync_orders_cis.py --asian <CK_Asian_Order_*.xlsx> \
                                     --euro  <CK_European_Order_*.xlsx>
  python3 scripts/sync_orders_cis.py ... --check     # 쓰지 않고 대조만

하는 일
  orders.csv 에서 promotion_category 가 'Asian vehicle' · 'European vehicle'
  인 행을 지우고 원자료의 행으로 다시 깖. 다른 캠페인 행은 건드리지 않음.

왜 교체인가
  원자료가 그 캠페인의 전체 기간을 늘 통째로 담고 있음(03-01~10-28).
  덧붙이면 이미 들어 있던 건과 겹치고, 원자료 쪽에서 수정된 건(금액 정정 등)이
  반영되지 않음. 그래서 그 두 캠페인만 통째로 갈아 끼움.

Customer_No
  원자료에 없어 orders.csv 의 기존 행에서 고객명으로 찾음.
  거기에도 없는 곳은 아래 EXTRA 에 적어 둠.
"""
import argparse, collections, csv, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSVF = os.path.join(ROOT, 'orders.csv')
CATS = ('Asian vehicle', 'European vehicle')
EXTRA = {'ARMTEK KZ': '200572'}      # orders.csv 에 아직 없던 고객사
COLS = ['CTR Code', 'order date', 'region', 'country', 'promotion_category',
        'promotion_theme', 'product', 'sku', 'part_no', 'position', 'make_model',
        'qty', 'unit_price', 'amount', 'currency', 'target', 'sell_type',
        'customer', 'Customer_No']


def read_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rs = list(ws.iter_rows(values_only=True))
    wb.close()
    # 머리글 행을 찾음 — 첫 줄에 합계만 있는 파일이 있어 고정 위치로 보지 않음
    hi = next(i for i, r in enumerate(rs[:5])
              if r and str(r[0] or '').strip() == 'CTR Code')
    hdr = [str(x).strip() if x is not None else '' for x in rs[hi]]
    ix = {c: hdr.index(c) for c in COLS if c in hdr}
    out = []
    for r in rs[hi + 1:]:
        if not r or not r[0]: continue
        d = {}
        for c in COLS:
            v = r[ix[c]] if c in ix and ix[c] < len(r) else None
            d[c] = '' if v is None else v
        d['order date'] = str(d['order date'])[:10]
        out.append(d)
    return out


def num(v):
    try: return float(str(v).replace(',', '') or 0)
    except ValueError: return 0.0


def key(r):
    return (r['promotion_category'], str(r['CTR Code']).strip(),
            str(r['order date'])[:10], str(r['customer']).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asian', required=True)
    ap.add_argument('--euro', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    old = list(csv.DictReader(open(CSVF, encoding='utf-8')))
    keep = [r for r in old if r['promotion_category'] not in CATS]
    cis_old = [r for r in old if r['promotion_category'] in CATS]

    cno = collections.defaultdict(collections.Counter)
    for r in old:
        c = (r['customer'] or '').strip()
        if c and r['Customer_No']: cno[c][r['Customer_No']] += 1

    new, miss, fx = [], set(), 0
    for p in (a.asian, a.euro):
        for r in read_xlsx(p):
            c = str(r['customer']).strip()
            n = EXTRA.get(c) or (cno[c].most_common(1)[0][0] if cno.get(c) else '')
            if not n: miss.add(c)
            r['Customer_No'] = n
            r['customer'] = c
            # 원자료는 단가만 현지 통화(EUR)고 amount 는 이미 USD 로 환산돼 있음
            # (10 × 3.75 EUR = 37.50 인데 amount 43.36 — 1.156 이 곱해진 값).
            # currency 를 그대로 두면 메인 대시보드가 amount 를 EUR 로 보고 한 번 더
            # 환산해 CIS 가 부풀음(실제로 $19,239 더 나왔음). USD 로 통일함.
            if str(r['currency']).strip().upper() not in ('', 'USD'):
                q, amt = num(r['qty']), num(r['amount'])
                if q: r['unit_price'] = round(amt / q, 4)
                r['currency'] = 'USD'
                fx += 1
            new.append(r)
    if fx: print(f"  단가 통화 환산: {fx:,} 행을 USD 로 통일 (amount 는 원자료가 이미 USD)")

    # ── 품번별 대조
    A = collections.defaultdict(lambda: [0.0, 0.0])
    B = collections.defaultdict(lambda: [0.0, 0.0])
    for r in cis_old:
        v = A[key(r)]; v[0] += num(r['qty']); v[1] += num(r['amount'])
    for r in new:
        v = B[key(r)]; v[0] += num(r['qty']); v[1] += num(r['amount'])
    ks = set(A) | set(B)
    add = [k for k in ks if k not in A]
    rm = [k for k in ks if k not in B]
    chg = [k for k in ks if k in A and k in B and abs(A[k][1] - B[k][1]) > 0.01]

    print(f"CIS 행 {len(cis_old):,} → {len(new):,}  (다른 캠페인 {len(keep):,} 행은 그대로)")
    print(f"  품번×일자×고객  새로 생김 {len(add):,} · 사라짐 {len(rm):,} · 금액 바뀜 {len(chg):,}")
    ma = collections.Counter(k[2][:7] for k in add)
    if ma: print('  새로 생긴 것 ' + ' · '.join(f'{m[5:]}월 {n}건' for m, n in sorted(ma.items()))
                 + f"  합계 ${sum(B[k][1] for k in add):,.0f}")
    if rm: print(f"  사라진 것 {len(rm)}건 · ${sum(A[k][1] for k in rm):,.0f}")
    for c in CATS:
        o = sum(v[1] for k, v in A.items() if k[0] == c)
        n = sum(v[1] for k, v in B.items() if k[0] == c)
        print(f"  {c:<18}${o:>12,.2f} → ${n:>12,.2f}")
    if miss: print('  Customer_No 를 못 찾은 고객사: ' + ' · '.join(sorted(miss)))

    if a.check: return
    if miss:
        print('  → Customer_No 가 비면 고객 단위 집계가 어긋남. EXTRA 에 적고 다시 돌림.')
        sys.exit(1)

    rows = keep + new
    rows.sort(key=lambda r: (str(r['order date'])[:10], str(r['promotion_category']),
                             str(r['CTR Code'])))
    with open(CSVF, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print(f"orders.csv 갱신됨 — 전체 {len(rows):,} 행")


if __name__ == '__main__':
    main()
