#!/usr/bin/env python3
"""캠페인 대상 SKU 매출 — 그 캠페인의 대상 고객사 것만.

  python3 scripts/campaign_sku_revenue.py --base data_base [--out campaign_sku_revenue.json]

왜 범위를 거나
  대상 SKU 만 걸고 전 고객을 합치면 그 품번이 전 세계에서 팔린 금액이 나옴 —
  캠페인 실적이 아님. 캠페인은 '그 권역의 그 나라의 그 고객사'가 그 품번을
  얼마나 샀는지임. 그래서 품번 ∩ 고객 ∩ 나라를 모두 걸고 셈.

고객 맞추기
  오더 원장과 매출표는 고객코드 체계가 서로 다름(오더 '280-010' 아닌 '287584').
  이름으로 맞추고 대상 국가로 한 번 더 거름. 못 맞춘 고객사는 결과에 남겨 둠 —
  조용히 빠지면 실적이 작아 보이기 때문임.

기준
  매출은 출하·청구분임. 같은 캠페인의 오더(수주)와 더하지 않음.
  확정 마감 이후 달은 예상매출이라 따로 셈.
"""
import argparse, collections, csv, gzip, json, os, re, sys

HTML = 'promo_dashboard_v10_6.html'
NORM = re.compile(r'[^A-Z0-9]+')
norm = lambda s: NORM.sub('', (s or '').upper().replace('“', '"').replace('”', '"'))

# 대상 국가 표기가 두 자료에서 다름
CTY = {'KAZAKHSTAN': 'KAZAKHSTAN', 'KYRGYZSTAN': 'KYRGYZREPUBLIC',
       'TURKMENISTAN': 'TURKMENISTAN', 'TAJIKISTAN': 'TAJIKISTAN'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='data_base')
    ap.add_argument('--out', default='campaign_sku_revenue.json')
    ap.add_argument('--html', default=HTML)
    a = ap.parse_args()

    T = json.load(open('campaign_target_skus.json', encoding='utf-8'))
    h = open(a.html, encoding='utf-8').read()
    D = json.loads(re.search(r'<script>const D = (\{.*?\});</script>', h, re.S).group(1))

    # 캠페인별 참여 고객사 — 대시보드가 오더에 쓰는 바로 그 명단
    part = collections.defaultdict(list)
    for r in D.get('cust_delta', []):
        part[r.get('program')].append((r.get('name') or '').strip())

    buyers = {}
    for b in csv.DictReader(open(os.path.join(a.base, 'am_buyers.csv'), encoding='utf-8')):
        buyers.setdefault(norm(b['buyer_name']), []).append(b)

    # 캠페인 구간 — 연도 전체가 아니라 이 달들만 봐야 오더 쪽과 기간이 맞음
    win = {}
    for c in D.get('campaigns', []):
        if c.get('program') and c.get('start'):
            win[c['program']] = (c['start'][:7], (c.get('end') or '9999-12')[:7])

    jobs = {}
    for name, v in T.items():
        if v.get('match_by') != 'sku' or not v.get('target_skus'): continue
        want = {norm(CTY.get(c, c)) for c in (v.get('target_countries') or [])}
        names = part.get(name) or v.get('target_customers') or []
        codes, matched, missing = set(), [], []
        for n in names:
            cands = buyers.get(norm(n)) or []
            if want:
                cands = [b for b in cands if norm(b['country']) in want]
            if cands:
                for b in cands: codes.add(b['buyer_code'])
                matched.append(n)
            else:
                missing.append(n)
        jobs[name] = dict(region=v.get('region'), skus=set(v['target_skus']),
                          codes=codes, n_cust=len(names),
                          matched=matched, missing=missing,
                          countries=v.get('target_countries') or [],
                          win=win.get(name))

    if not jobs:
        print('대상 SKU 가 지정된 캠페인이 없음.'); return

    # 확정 매출이 어디까지 있나 — 캠페인 구간을 여기서 자름.
    # 자르지 않으면 전년은 11월까지, 올해는 9월까지가 되어 전년 대비가 왜곡됨.
    cut = max(json.load(open(os.path.join(a.base, 'manifest.json'),
                             encoding='utf-8'))['sales_meta']['last_actual'].values())
    cutm = cut[4:]
    for j in jobs.values():
        if j['win']: j['win'] = (j['win'][0], min(j['win'][1], j['win'][1][:5] + cutm))

    allc = set().union(*(j['codes'] for j in jobs.values()))
    alls = set().union(*(j['skus'] for j in jobs.values()))
    agg = {k: collections.defaultdict(lambda: [0.0, 0.0, set()]) for k in jobs}
    wag = {k: collections.defaultdict(lambda: [0.0, 0.0, set()]) for k in jobs}
    cag = {k: collections.Counter() for k in jobs}
    maxm = {k: '' for k in jobs}
    src = os.path.join(a.base, 'am_sales_sku.csv.gz')
    op = gzip.open if src.endswith('.gz') else open
    with op(src, 'rt', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['buyer_code'] not in allc or r['item_code'] not in alls: continue
            u = float(r['usd'] or 0); q = float(r['qty'] or 0); mo = r['month']
            for k, j in jobs.items():
                if r['buyer_code'] not in j['codes'] or r['item_code'] not in j['skus']:
                    continue
                g = agg[k][(mo[:4], r['is_forecast'])]
                g[0] += u; g[1] += q; g[2].add(r['item_code'])
                # 캠페인 구간 · 확정분만. 전년 같은 달과 1:1 로 비교할 수 있게 전년도 같은 구간도 셈
                w = j['win']
                if w and r['is_forecast'] == '0' and w[0][5:] <= mo[5:] <= w[1][5:]:
                    if mo[:4] >= '2024':
                        v = wag[k][mo[:4]]
                        v[0] += u; v[1] += q; v[2].add(r['item_code'])
                    if mo[:4] == w[0][:4]:
                        cag[k][r['buyer_name']] += u
                        if mo > maxm[k]: maxm[k] = mo

    out = {}
    for k, j in jobs.items():
        yrs = {}
        for (y, fc), g in sorted(agg[k].items()):
            d = yrs.setdefault(y, {})
            d['예상' if fc == '1' else '확정'] = dict(
                usd=round(g[0], 2), qty=int(g[1]), n_sku=len(g[2]))
        wy = {y: dict(usd=round(g[0], 2), qty=int(g[1]), n_sku=len(g[2]))
              for y, g in sorted(wag[k].items())}
        cy = cag[k].most_common()
        out[k] = dict(region=j['region'], target_countries=j['countries'],
                      n_target_sku=len(j['skus']),
                      n_cust_total=j['n_cust'], n_cust_matched=len(j['matched']),
                      unmatched_customers=j['missing'],
                      window=(f"{j['win'][0][5:]}~{j['win'][1][5:]}월" if j['win'] else ''),
                      window_cut=maxm[k], by_year_full=yrs, by_year_window=wy,
                      by_customer_window={n: round(v, 2) for n, v in cy},
                      basis='매출(출하·청구) · 대상 SKU ∩ 대상 고객사 ∩ 대상 국가. '
                            '같은 캠페인의 오더(수주)와 더하지 않음.')
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    for k, v in out.items():
        print(f"\n{k} ({v['region']}) · 대상 {v['n_target_sku']}종 · "
              f"고객 {v['n_cust_matched']}/{v['n_cust_total']}곳")
        if v['unmatched_customers']:
            print('   매출표에 없는 고객사: ' + ', '.join(v['unmatched_customers']))
        if v['by_year_window']:
            print(f"   캠페인 구간 {v['window']} (확정 ~{v['window_cut']})")
            for y, o in v['by_year_window'].items():
                print(f"     {y}  ${o['usd']:>11,.0f}  {o['qty']:>9,}개  {o['n_sku']:>4}종")
            ys = sorted(v['by_year_window'])
            if len(ys) >= 2:
                p, c = v['by_year_window'][ys[-2]]['usd'], v['by_year_window'][ys[-1]]['usd']
                if p: print(f"     전년 대비 {(c-p)/p*100:+.1f}%")
        print('   연간 전체: ' + ' · '.join(
            f"{y} " + '/'.join(f"{t} ${o['usd']:,.0f}" for t, o in d.items())
            for y, d in sorted(v['by_year_full'].items())))
    print(f"\n{a.out} 에 적어 둠.")


if __name__ == '__main__':
    main()
