#!/usr/bin/env python3
"""SEA 고객사 오더 라인(품번 × 오더일) 분석용 자료만 뽑음.

  python3 scripts/sync_sea_lines.py --src Customer_order_data_SEA_202610.xlsx

내보내는 것
  sea_order_lines.csv   품번 × 오더일 × 고객(지점) 한 줄씩 — 수량만
  sea_order_lines.json  달·고객·나라별 묶음과 범위 메모

화면에 쓰지 않는 이유 (중요)
  이 자료의 2026 쪽은 화면의 ASIA Sell-in 수량(asia_sellin_qty.json)과 집계
  범위가 다름. 같은 12개 고객사인데 2026 합계가 630,889 → 133,435 로,
  2025 합계는 461,981 → 822,331 로 양쪽이 반대로 어긋남. 오더일 최댓값이
  2026-10-08 이고 10월은 3일치 5개 고객뿐임. 어느 쪽이 맞는지 ASIA 팀 확인
  전까지 화면 수치는 건드리지 않고, 이 파일은 품번 × 일자 분석용으로만 둠.

  금액은 이 자료에 없음 — 수량만 있음. 금액이 필요한 집계에 쓰지 말 것.
"""
import argparse, collections, csv, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAT = {'VN': '베트남', 'PH': '필리핀', 'TH': '태국', 'ID': '인도네시아', 'MY': '말레이시아'}
COLS = ['order_date', 'order_month', 'member_id', 'customer', 'branch',
        'nation', 'country', 'ctr_no', 'old_ctr_no', 'qty']


def rows_of(ws):
    return list(ws.iter_rows(values_only=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default=ROOT)
    a = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(a.src, read_only=True, data_only=True)

    # 고객코드 → 고객사·지점 (매핑 시트가 없으면 'customer info' 로 대체)
    name = {}
    for sh in ('고객코드_매핑', 'customer info'):
        if sh not in wb.sheetnames: continue
        rs = rows_of(wb[sh])
        hdr = [str(x or '').strip() for x in rs[0]]
        try:
            ic, ib, ik = hdr.index('Buyer code'), hdr.index('Branch'), hdr.index('Customer')
        except ValueError:
            continue
        cur = ''
        for r in rs[1:]:
            if not r or len(r) <= max(ic, ib, ik): continue
            code = str(r[ic] or '').strip()
            cur = str(r[ik] or '').strip() or cur     # customer info 는 고객명이 병합돼 빈 칸임
            if code: name[code] = (cur, str(r[ib] or '').strip())
        if name: break

    rs = rows_of(wb['raw data'])
    hdr = [str(x or '').strip() for x in rs[0]]
    ix = {k: hdr.index(k) for k in ('member_id', 'ctr_no', 'old_ctr_no',
                                    'order_date', 'qty', 'nation') if k in hdr}
    out, miss = [], set()
    for r in rs[1:]:
        if not r or not r[ix['member_id']]: continue
        code = str(r[ix['member_id']]).strip()
        d = str(r[ix['order_date']])[:10]
        nat = str(r[ix['nation']] or '').strip()
        k, b = name.get(code, ('', ''))
        if not k: miss.add(code)
        out.append({'order_date': d, 'order_month': d[:7], 'member_id': code,
                    'customer': k, 'branch': b, 'nation': nat,
                    'country': NAT.get(nat, nat),
                    'ctr_no': str(r[ix['ctr_no']] or '').strip(),
                    'old_ctr_no': str(r[ix['old_ctr_no']] or '').strip(),
                    'qty': int(float(r[ix['qty']] or 0))})
    wb.close()
    out.sort(key=lambda x: (x['order_date'], x['customer'], x['ctr_no']))

    p = os.path.join(a.out, 'sea_order_lines.csv')
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader(); w.writerows(out)

    bym = collections.defaultdict(lambda: [0, 0, set()])
    byc = collections.defaultdict(lambda: [0, 0, set()])
    byn = collections.defaultdict(lambda: [0, 0, set()])
    for r in out:
        for d, key in ((bym, r['order_month']), (byc, r['customer'] or r['member_id']),
                       (byn, r['country'])):
            v = d[key]; v[0] += 1; v[1] += r['qty']; v[2].add(r['ctr_no'])
    pack = lambda d: {k: {'lines': v[0], 'qty': v[1], 'skus': len(v[2])}
                      for k, v in sorted(d.items())}

    meta = {
        '_readme': 'SEA 고객사 오더 라인(품번 × 오더일) — 분석용. 수량만 있고 금액은 없음. '
                   '재생성: python3 scripts/sync_sea_lines.py --src <xlsx>',
        '_scope_warning': '화면의 ASIA Sell-in 수량(asia_sellin_qty.json)과 집계 범위가 달라 '
                          '섞지 말 것. 같은 12개 고객사인데 2026 합계 630,889 → 133,435, '
                          '2025 합계 461,981 → 822,331 로 양쪽이 반대로 어긋남. '
                          'ASIA 팀 확인 전까지 화면 수치에 반영하지 않음.',
        'src': os.path.basename(a.src),
        'lines': len(out), 'qty': sum(r['qty'] for r in out),
        'skus': len({r['ctr_no'] for r in out}),
        'customers': len({r['member_id'] for r in out}),
        'date_from': out[0]['order_date'], 'date_to': out[-1]['order_date'],
        'by_month': pack(bym), 'by_customer': pack(byc), 'by_country': pack(byn),
        'unmapped_codes': sorted(miss),
    }
    json.dump(meta, open(os.path.join(a.out, 'sea_order_lines.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print(f"sea_order_lines.csv — {len(out):,} 줄 · {meta['date_from']} ~ {meta['date_to']}")
    print(f"  수량 {meta['qty']:,} · 품목 {meta['skus']:,} · 고객코드 {meta['customers']}개"
          + (f" · 고객명 못 찾은 코드 {len(miss)}개" if miss else ''))
    for y in ('2025', '2026'):
        ms = {k: v for k, v in meta['by_month'].items() if k.startswith(y)}
        print(f"  {y}  라인 {sum(v['lines'] for v in ms.values()):>6,} · "
              f"수량 {sum(v['qty'] for v in ms.values()):>9,} · {len(ms)}개월")
    print('  나라별 ' + ' · '.join(f"{k} {v['qty']:,}" for k, v in meta['by_country'].items()))


if __name__ == '__main__':
    main()
