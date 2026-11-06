#!/usr/bin/env python3
"""CIS 캠페인 수치(D.campaigns · D.cust_delta)를 orders.csv · baseline 으로 다시 셈.

  python3 scripts/sync_cis_campaign.py [--check]

왜 필요한가
  orders.csv 의 CIS 행을 원자료로 갈아 끼우면(sync_orders_cis.py) 화면의
  당해 수치가 그만큼 어긋남. 전년도 같은 구간으로 다시 뽑아야 전년 대비가 성립함.

구간을 '월'로 잡는 이유
  baseline_data 의 2025 는 월 단위로 묶여 있음(order_date 가 모두 월초 1일).
  그래서 일자 구간(03-23~10-19)을 전년에 그대로 적용할 수 없음 — 그렇게 하면
  2025-03 이 통째로 빠지고 2025-10 은 통째로 들어가 전년이 제멋대로 깎임.
  원자료(CK_*_Order_0301-1028)가 3/1~10/28 을 담고 있으므로 양쪽 모두
  '3월~10월' 로 맞춤. 당해 첫 오더가 03-23, 마지막이 10-19 인 것은 그 구간에
  실제로 난 오더가 그렇다는 뜻이고, 집계 구간이 좁다는 뜻이 아님.

손대지 않는 것
  o25/o26 과 DiD 묶음(c25·c26·d25·d26·cyoy·dyoy·incr·cf·ctrl_top)은
  이 두 자료에서 나오지 않고 did_end·did_days 로 자기 구간을 따로 달고 있음.
  기준이 섞이므로 여기서 덮지 않음.
"""
import argparse, calendar, collections, csv, datetime, glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
CATS = ('Asian vehicle', 'European vehicle')


def months(a, b):
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while '%d-%02d' % (y, m) <= b:
        out.append('%d-%02d' % (y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    TS = json.load(open(os.path.join(ROOT, 'campaign_target_skus.json'), encoding='utf-8'))
    sk = {c: set(TS[c]['target_skus']) for c in CATS if c in TS}

    # ── 당해: orders.csv (그 캠페인 원장 전체)
    cur = {c: collections.defaultdict(lambda: [0.0, 0.0]) for c in CATS}   # 고객 → [usd, qty]
    cmon = {c: collections.defaultdict(float) for c in CATS}
    csku = {c: set() for c in CATS}
    custs = {c: set() for c in CATS}
    dates = []
    for r in csv.DictReader(open(os.path.join(ROOT, 'orders.csv'), encoding='utf-8')):
        c = r['promotion_category']
        if c not in CATS: continue
        d = r['order date'][:10]
        n = (r['customer'] or '').strip()
        u = float(r['amount'] or 0); q = float(r['qty'] or 0)
        if d: dates.append(d)
        v = cur[c][n]; v[0] += u; v[1] += q
        cmon[c][d[:7]] += u
        if r['sku']: csku[c].add(r['sku'])
        custs[c].add(n)
    if not dates:
        print('orders.csv 에 CIS 행이 없음.'); return
    d0, d1 = min(dates), max(dates)
    M = months(d0[:7], d1[:7])                     # 2026-03 … 2026-10
    P = ['%d%s' % (int(m[:4]) - 1, m[4:]) for m in M]

    # ── 전년: baseline (같은 달 · 같은 대상 SKU · 같은 고객사)
    pre = {c: collections.defaultdict(lambda: [0.0, 0.0]) for c in CATS}
    pmon = {c: collections.defaultdict(float) for c in CATS}
    psku = {c: set() for c in CATS}
    for f in sorted(glob.glob(os.path.join(ROOT, 'baseline_data', 'chunk_*.json'))):
        for r in json.load(open(f, encoding='utf-8')):
            ym = (r.get('order_date') or '')[:7]
            if ym not in P: continue
            n = (r.get('customer') or '').strip()
            s = (r.get('sku') or '').strip()
            for c in CATS:
                if n in custs[c] and s in sk.get(c, ()):
                    v = pre[c][n]
                    v[0] += r.get('amount_usd') or 0
                    v[1] += r.get('qty') or 0
                    pmon[c][ym] += r.get('amount_usd') or 0
                    psku[c].add(s)

    html = open(HTML, encoding='utf-8', newline='').read()
    m = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
    D = json.loads(m.group(1))

    print(f"CIS 캠페인 · 당해 {M[0]}~{M[-1]} (오더 {d0}~{d1}) · 전년 {P[0]}~{P[-1]} (월 단위)")
    for c in CATS:
        camp = next((x for x in D['campaigns'] if x.get('region') == 'CIS'
                     and x.get('program') == c), None)
        if not camp: continue
        a26 = round(sum(v[0] for v in cur[c].values()), 2)
        a25 = round(sum(v[0] for v in pre[c].values()), 2)
        q26 = int(sum(v[1] for v in cur[c].values()))
        q25 = int(sum(v[1] for v in pre[c].values()))
        yoy = (a26 - a25) / a25 * 100 if a25 else None

        # 월별 묶음 — 전년 달들 먼저, 그 다음 당해 달들(기존 모양 그대로)
        ms = []
        for ym in P:
            dd = calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]
            ms.append({'m': ym, 'cur': 0, 'prv': round(pmon[c].get(ym, 0.0), 1),
                       'yoy': -100.0, 'days': 0, 'mdays': dd})
        for ym in M:
            dd = calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]
            lo = max(d0, '%s-01' % ym); hi = min(d1, '%s-%02d' % (ym, dd))
            obs = (datetime.date.fromisoformat(hi) - datetime.date.fromisoformat(lo)).days + 1
            ms.append({'m': ym, 'cur': round(cmon[c].get(ym, 0.0), 1), 'prv': 0,
                       'yoy': None, 'days': max(obs, 0), 'mdays': dd})

        st = datetime.date.fromisoformat(camp['start'])
        en = datetime.date.fromisoformat(camp['end'])
        ob = datetime.date.fromisoformat(d1)
        days = (en - st).days + 1
        obsd = (ob - st).days + 1

        print(f"  {c:<18}a25 {camp.get('a25'):>11,.0f} → {a25:>11,.0f}"
              f"   a26 {camp.get('a26'):>11,.0f} → {a26:>11,.0f}"
              f"   YoY {camp.get('yoy'):>6.1f}% → {yoy:>6.1f}%")
        print(f"  {'':<18}수량 {camp.get('q25'):>11,} → {q25:>11,}"
              f"        {camp.get('q26'):>11,} → {q26:>11,}"
              f"   품목 {camp.get('s25')}→{len(psku[c])} / {camp.get('s26')}→{len(csku[c])}")

        camp.update(a25=a25, a26=a26, all25=a25, all26=a26, yoy=yoy, yoyA=yoy,
                    q25=q25, q26=q26, s25=len(psku[c]), s26=len(csku[c]),
                    ord_sku=len(csku[c]), mser=ms,
                    cut=d1, obs_end=d1, days=days, obs_days=obsd,
                    progress=round(obsd / days * 100, 1),
                    wins=[[d0, d1]], n_cust=len(custs[c]),
                    mo_ord=round(cmon[c].get(M[-1], 0.0)))

        for r in D.get('cust_delta', []):
            if r.get('region') == 'CIS' and r.get('program') == c:
                n = (r.get('name') or '').strip()
                r['a25'] = round(pre[c].get(n, [0.0, 0.0])[0], 2)
                r['a26'] = round(cur[c].get(n, [0.0, 0.0])[0], 2)

    out = html[:m.start(1)] + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)
    print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))


if __name__ == '__main__':
    main()
