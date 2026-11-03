#!/usr/bin/env python3
"""오더 원장·매출표 HTML 두 개 → 분석 기반 테이블 묶음.

  python3 scripts/build_base.py --orders <KV_Orders_*.html> --sales <AM_SalesDash_*.html> \
                                --out data_base

두 파일 모두 화면용 HTML 안에 압축된 배열을 품고 있어 그대로는 질의가 안 됨.
여기서 한 번 풀어 테이블로 떨궈 두면 이후 분석은 이 테이블만 보면 됨.

내보내는 것
  오더 원장 (KV)
    kv_orders.csv            오더 헤더. 날짜 있음, 품번 없음.
    kv_cust_item_year.csv    고객×품번×연도 수량. 포장 끝난 라인만.
    kv_backorder_lines.csv   백오더 잔량 라인.
    kv_customers.csv / kv_items.csv
  매출표 (AM)
    am_sales_cat.csv         월×고객×품목군 매출. 전 법인.
    am_sales_sku.csv(.gz)    월×고객×CTR 품번 매출. 직거래분만.
    am_plan.csv              사업계획(MP).
    am_buyers.csv / am_items.csv
  manifest.json              행수·합계·커버리지·출처

읽기 전에 아는 게 나은 것
  · 오더는 수주, 매출은 출하·청구임. 같은 칸에서 더하지 않음.
  · 오더 쪽에서 품번은 연도까지만 쪼개짐 — 품번×월은 이 원장에 없음.
  · 매출 쪽 품번 단위(am_sales_sku)는 직거래분만이라 am_sales_cat 합계보다 작음.
"""
import argparse, base64, collections, csv, datetime, gzip, io, json, os, re, sys


def grab(s, i):
    """s[i] 의 여는 괄호와 짝이 되는 자리까지 잘라 냄."""
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


def const(h, name):
    m = re.search(r'const\s+%s\s*=\s*' % re.escape(name), h)
    if not m: raise ValueError('const %s 를 찾지 못했음' % name)
    return json.loads(grab(h, m.end()))


def wr(path, header, rows, gz=False):
    op = gzip.open if gz else open
    with op(path, 'wt', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return os.path.getsize(path)


# ────────────────────────────── 오더 원장 ──────────────────────────────
def build_orders(path, out, man):
    h = open(path, encoding='utf-8', errors='replace').read()
    D = const(h, 'D')
    M = D['meta']
    ep = datetime.date(*map(int, M['epoch'].split('-')))
    NOP = -99999
    d2 = lambda v: (ep + datetime.timedelta(days=v)).isoformat() if v and v > NOP else ''

    REG, CTY, ENT, PT = D['reg'], D['cty'], D.get('ent', ['K']), D['pt']
    ORG, LTY = D.get('org', []), D.get('lty', [])
    CUS, ITM = D['cus'], D['itm']

    # 계열사 판별. 이 원장은 내부거래 표시가 따로 없어 CTR 계열 법인도 고객으로 같이 들어 있음.
    # 2026 오더의 61% 가 계열사분이라 외부 실적을 볼 때는 반드시 걷어내야 함.
    AFF = re.compile(r'^\s*CTR\b|씨티알')
    af = lambda n: 1 if AFF.search(n or '') else 0

    # 고객: [이름, 지역idx, 국가idx, 코드, ?, 법인idx, 전화]
    # cust_code 는 법인(K/V)마다 따로 쓰여 중복됨 — 고유키는 cust_idx 임.
    cus = [[i, c[3], c[0], REG[c[1]] if c[1] is not None and c[1] < len(REG) else '',
            CTY[c[2]] if c[2] is not None and c[2] < len(CTY) else '',
            ENT[c[5]] if len(c) > 5 and c[5] is not None and c[5] < len(ENT) else '',
            af(c[0])]
           for i, c in enumerate(CUS)]
    man['files']['kv_customers.csv'] = dict(rows=len(cus), size=wr(
        os.path.join(out, 'kv_customers.csv'),
        ['cust_idx', 'cust_code', 'cust_name', 'region', 'country', 'entity',
         'is_affiliate'], cus),
        note='is_affiliate=1 은 CTR 계열 법인임. 이 원장에는 내부거래 표시가 없어 '
             '계열사 오더가 외부 오더와 섞여 있음 — 외부 실적을 볼 때는 빼야 함. '
             'cust_code 는 법인마다 재사용되므로 고유키는 cust_idx 임.')

    # 품목: [CTR코드, 품명, 제품구분idx, 원산지idx]
    itm = [[i[0], i[1], PT[i[2]] if i[2] is not None and i[2] < len(PT) else '',
            ORG[i[3]] if len(i) > 3 and i[3] is not None and i[3] < len(ORG) else '']
           for i in ITM]
    man['files']['kv_items.csv'] = dict(rows=len(itm), size=wr(
        os.path.join(out, 'kv_items.csv'), ['item_code', 'item_name', 'product_type', 'origin'], itm))

    # 오더 헤더: [오더번호, 고객idx, 접수일, 납품요청일, 포장일, MRP월, 상태,
    #             수량, 포장수량, USD, 통화, PO, ?, 제상품벡터, 최소납품요청일, 납품수량]
    rows, tot_usd = [], 0.0
    by_year = collections.defaultdict(lambda: [0.0, 0.0])   # [계열사, 외부]
    for r in D['ord']:
        c = CUS[r[1]]
        od = d2(r[2]); a = af(c[0])
        rows.append([r[0], r[1], c[3], c[0],
                     REG[c[1]] if c[1] < len(REG) else '', CTY[c[2]] if c[2] < len(CTY) else '',
                     ENT[c[5]] if len(c) > 5 and c[5] < len(ENT) else '', a,
                     od, d2(r[3]),
                     ('%d-%02d' % (r[5] // 100, r[5] % 100)) if r[5] and r[5] > 0 else '',
                     r[6], r[7], r[8], round(r[9], 2), r[10], r[11] or '', r[15] if len(r) > 15 else ''])
        tot_usd += r[9]
        if od: by_year[od[:4]][a] += r[9]
    man['files']['kv_orders.csv'] = dict(rows=len(rows), size=wr(
        os.path.join(out, 'kv_orders.csv'),
        ['order_no', 'cust_idx', 'cust_code', 'cust_name', 'region', 'country', 'entity',
         'is_affiliate', 'order_date', 'delivery_req_date', 'mrp_month', 'status',
         'qty', 'pack_qty', 'usd', 'currency', 'po_no', 'delivered_qty'], rows),
        note='오더 헤더 단위임 — 품번 칸이 없음. 품번별로 보려면 kv_cust_item_year.csv 로 가야 하고 '
             '거기는 월이 아니라 연도까지만 쪼개짐.')

    # 고객×품번×연도: [고객, 품목, 연도, 건수, 리드타임합, 수량가중합, 최단, 최장, 오더수량, 포장수량]
    li, liq = [], 0.0
    for r in D.get('ltl', []):
        c, it = CUS[r[0]], ITM[r[1]]
        li.append([r[0], c[3], c[0], af(c[0]), it[0], it[1],
                   PT[it[2]] if it[2] < len(PT) else '', r[2], r[3],
                   r[8], r[9], round(r[4] / r[3], 1) if r[3] else ''])
        liq += r[8]
    man['files']['kv_cust_item_year.csv'] = dict(rows=len(li), size=wr(
        os.path.join(out, 'kv_cust_item_year.csv'),
        ['cust_idx', 'cust_code', 'cust_name', 'is_affiliate', 'item_code', 'item_name',
         'product_type', 'year', 'n_lines', 'order_qty', 'pack_qty',
         'avg_pack_leadtime_days'], li),
        note='원래 포장 리드타임을 보려고 만든 표라 포장이 끝난 라인만 들어 있음 — 오더 전량이 아님. '
             '금액 칸이 없어 수량으로만 봄. 품번 단위 오더를 연도로 가를 수 있는 유일한 표임.')

    # 백오더 라인
    bo = []
    for r in D.get('bol', []):
        c, it = CUS[r[0]], ITM[r[1]]
        bo.append([r[0], c[3], c[0], af(c[0]), it[0], it[1],
                   PT[it[2]] if it[2] < len(PT) else '',
                   r[8] or '', r[9] or '', r[2], r[3], round(r[5], 2), round(r[6], 2),
                   1 if len(r) > 10 and r[10] else 0,
                   r[13] if len(r) > 13 else '', r[14] if len(r) > 14 else ''])
    man['files']['kv_backorder_lines.csv'] = dict(rows=len(bo), size=wr(
        os.path.join(out, 'kv_backorder_lines.csv'),
        ['cust_idx', 'cust_code', 'cust_name', 'is_affiliate', 'item_code', 'item_name',
         'product_type', 'order_year', 'mrp_year', 'order_qty', 'open_qty',
         'amount_a', 'amount_b', 'past_due', 'delivered_qty', 'packed_qty'], bo),
        note='past_due=1 은 기준일에 납품요청일이 이미 지난 잔량임.')

    man['orders_meta'] = dict(
        snapshot=M.get('snap'), generated=M.get('gen'),
        source_order=M.get('srcOrder'), source_pack=M.get('srcPack'),
        lines_in_source=M.get('lines'), orders_in_source=M.get('orders'),
        entities=M.get('entStat'), year_from=M.get('yearFrom'),
        order_date_max=max((x[8] for x in rows if x[8]), default=''),
        total_usd=round(tot_usd, 2),
        usd_by_year={k: {'계열사': round(v[1], 2), '외부': round(v[0], 2)}
                     for k, v in sorted(by_year.items())},
        ltl_order_qty=liq,
        affiliate_note='이 원장에는 내부거래 표시가 없음. CTR 계열 법인(CTR RUS·CTR EUROPE·'
                       'CTR America·씨티알 영산공장 등)이 고객으로 같이 들어 있어 '
                       '2026 오더의 61% 가 계열사분임 — is_affiliate 로 걸러야 함.')
    return D


# ────────────────────────────── 매출표 ──────────────────────────────
def build_sales(path, out, man, sku_gzip=True):
    h = open(path, encoding='utf-8', errors='replace').read()
    A = const(h, 'DATA')
    P, BY, CT = A['periods'], A['buyers'], A['cats']
    ym = lambda i: P[i][:4] + '-' + P[i][4:]

    # 고객: [집계법인, 코드, 이름, 국가, 지역, 출처법인, 등록일]
    by = [[b[1], b[2], b[3], b[4], b[0], (b[5] if len(b) > 5 else b[0]) or b[0],
           b[6] if len(b) > 6 else ''] for b in BY]
    man['files']['am_buyers.csv'] = dict(rows=len(by), size=wr(
        os.path.join(out, 'am_buyers.csv'),
        ['buyer_code', 'buyer_name', 'country', 'region', 'plant', 'src_plant', 'registered'], by))

    # 월×고객×품목군: [기간,고객,품목군,내부거래,예상매출,수량,USD,KRW,KG,제품구분,신규판정]
    NIL = {0: '기존', 1: '신규', 2: '판정불가'}
    PTL = {0: 'P(제품)', 1: 'G(상품)', 2: '기타'}
    fr, usd_act, usd_fc = [], 0.0, 0.0
    for r in A['fact']:
        fr.append([ym(r[0]), BY[r[1]][1], BY[r[1]][2], BY[r[1]][4], BY[r[1]][3], BY[r[1]][0],
                   CT[r[2]], int(bool(r[3])), int(bool(r[4])), r[5], round(r[6], 2),
                   r[7], r[8], PTL.get(r[9], ''), NIL.get(r[10] if len(r) > 10 else 2, '')])
        if not r[3]:
            if r[4]: usd_fc += r[6]
            else: usd_act += r[6]
    man['files']['am_sales_cat.csv'] = dict(rows=len(fr), size=wr(
        os.path.join(out, 'am_sales_cat.csv'),
        ['month', 'buyer_code', 'buyer_name', 'region', 'country', 'plant', 'category',
         'is_internal', 'is_forecast', 'qty', 'usd', 'krw_actual', 'krw_std',
         'product_type', 'new_flag'], fr),
        note='is_internal=1 은 내부거래라 대부분의 집계에서 빼는 행임. '
             'is_forecast=1 은 아직 확정 안 된 예상매출임. '
             'krw_actual 은 그 달 실제 환율(중앙값 약 1,366원), krw_std 는 경영환율 1,280원 고정임. '
             '원본은 이 자리를 KG 로 이름 붙여 두었지만 USD 대비 비율이 정확히 1,280 이라 '
             '중량이 아니라 경영환율 환산액임 — 중량으로 읽으면 안 됨.')

    # 사업계획
    mp = [[ym(r[0]), BY[r[1]][1], BY[r[1]][2], CT[r[2]], int(bool(r[3])), r[4], r[5],
           PTL.get(r[6], '') if len(r) > 6 else ''] for r in A.get('mp', [])]
    man['files']['am_plan.csv'] = dict(rows=len(mp), size=wr(
        os.path.join(out, 'am_plan.csv'),
        ['month', 'buyer_code', 'buyer_name', 'category', 'is_internal', 'qty', 'amount',
         'product_type'], mp),
        note='사업계획은 품목군 단위까지만 세워져 CTR 품번으로는 못 쪼갬.')

    # 월×고객×CTR 품번 (압축 해제) — 직거래분만
    sku_rows = 0
    if A.get('factcz'):
        Z = json.loads(gzip.decompress(base64.b64decode(A['factcz'])))
        codes, ratio = Z['codes'], Z['ratio']
        p, b, c, f, t, rr, q, u = (Z[k] for k in ('p', 'b', 'c', 'f', 't', 'r', 'q', 'u'))
        name = os.path.join(out, 'am_sales_sku.csv' + ('.gz' if sku_gzip else ''))
        op = gzip.open if sku_gzip else open
        tot_u = 0.0
        with op(name, 'wt', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['month', 'buyer_code', 'buyer_name', 'region', 'country', 'plant',
                        'item_code', 'is_forecast', 'product_type', 'qty', 'usd', 'krw'])
            for i in range(len(p)):
                bb = BY[b[i]]; rt = ratio[rr[i]] if rr[i] < len(ratio) else [0, 0]
                uu = u[i]; tot_u += uu
                w.writerow([ym(p[i]), bb[1], bb[2], bb[4], bb[3], bb[0],
                            codes[c[i]], int(bool(f[i])), PTL.get(t[i], ''),
                            q[i], round(uu, 2), round(uu * rt[0], 0)])
            sku_rows = len(p)
        man['files'][os.path.basename(name)] = dict(
            rows=sku_rows, size=os.path.getsize(name), distinct_items=len(codes),
            total_usd=round(tot_u, 2),
            note='CTR 품번 단위 매출임. 내부거래를 뺀 am_sales_cat 합계와 연도별로 100.0% 일치 — '
                 '외부 매출 전량이 품번까지 쪼개져 있음. '
                 'krw 는 같은 법인·월의 환산비로 USD 에서 되살린 값이라 원 단위까지 맞음. '
                 '사업계획(am_plan)은 품목군까지만 있어 이 표와 품번 단위로 맞댈 수 없음.')
        man['files']['am_items.csv'] = dict(rows=len(codes), size=wr(
            os.path.join(out, 'am_items.csv'), ['item_code'], [[x] for x in codes]))

    internal = collections.defaultdict(lambda: [0.0, 0.0])   # 연도 → [외부, 내부]
    for r in A['fact']:
        internal[P[r[0]][:4]][1 if r[3] else 0] += r[6]
    man['sales_meta'] = dict(
        usd_by_year={k: {'외부': round(v[0], 2), '내부거래': round(v[1], 2)}
                     for k, v in sorted(internal.items())},
        built=A['meta'].get('built'), last_actual=A['meta'].get('lastActual'),
        rate2026=A['meta'].get('rate2026'), fx_month=A['meta'].get('fxMon'),
        fx_rate=A['meta'].get('fxRate'),
        periods=[P[0], P[-1]], n_buyers=len(BY), n_categories=len(CT),
        usd_actual_excl_internal=round(usd_act, 2),
        usd_forecast_excl_internal=round(usd_fc, 2),
        etc_source=(A.get('etc') or {}).get('src', ''))
    return A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--orders', required=True)
    ap.add_argument('--sales', required=True)
    ap.add_argument('--out', default='data_base')
    ap.add_argument('--no-gzip', action='store_true')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    man = {'built_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
           'source_files': {'orders': os.path.basename(a.orders),
                            'sales': os.path.basename(a.sales)},
           'files': {}}
    build_orders(a.orders, a.out, man)
    build_sales(a.sales, a.out, man, sku_gzip=not a.no_gzip)
    json.dump(man, open(os.path.join(a.out, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('=' * 64)
    for k, v in man['files'].items():
        print(f"  {k:<28}{v['rows']:>10,}행  {v['size']/1048576:>7.1f}MB")
    om, sm = man['orders_meta'], man['sales_meta']
    print(f"\n오더 원장 스냅 {om['snapshot']} · 마지막 오더일 {om['order_date_max']}")
    print(f"  오더 {man['files']['kv_orders.csv']['rows']:,}건 · 합계 ${om['total_usd']:,.0f}")
    print('  연도별 오더 (외부 / 계열사)')
    for k, v in om['usd_by_year'].items():
        print(f"    {k}  외부 ${v['외부']/1e6:>7.2f}M   계열사 ${v['계열사']/1e6:>7.2f}M")
    print(f"\n매출표 작성 {sm['built']} · 확정 마감 {sorted(set(sm['last_actual'].values()))}")
    print('  연도별 매출 (외부 / 내부거래)')
    for k, v in sm['usd_by_year'].items():
        print(f"    {k}  외부 ${v['외부']/1e6:>7.2f}M   내부거래 ${v['내부거래']/1e6:>7.2f}M")
    print(f"  그중 확정 ${sm['usd_actual_excl_internal']/1e6:,.2f}M · 예상 ${sm['usd_forecast_excl_internal']/1e6:,.2f}M")
    print(f"\n{a.out}/manifest.json 에 전체 수치를 적어 둠.")


if __name__ == '__main__':
    main()
