#!/usr/bin/env python3
"""캠페인 참여 고객사의 매출 — 전 품목 · 올해 누계와 전년 같은 구간.

  python3 scripts/sync_campaign_revenue.py --base data_base [--through 2026-10]

무엇을 세나
  캠페인에 들어간 고객사가 올린 매출 전부(전 품목). 대상 SKU 로 좁히지
  않음 — 그 고객사가 캠페인 기간에 무엇을 샀든 다 봄.

구간
  1월부터 --through 달까지. 전년은 같은 달 구간(연도만 -1).
  --through 를 안 주면 전 법인이 결산된 마지막 달까지.

중복
  한 고객사가 여러 캠페인에 걸려도 한 번만 셈.

기준
  매출(출하·청구) · 내부거래 제외. 오더(수주)와 더하지 않음.
"""
import argparse, collections, csv, gzip, json, os, re

HTML = 'promo_dashboard_v10_6.html'
NORM = re.compile(r'[^A-Z0-9]+')
norm = lambda s: NORM.sub('', (s or '').upper().replace('“', '"').replace('”', '"'))
ALIAS = {'GTAVIETNAM': ['551-021']}      # 매출표에는 'CONG TY TNHH THUONG MAI GTA VIET NAM'


def put(html, name, obj):
    m = re.search(r'const %s\s*=\s*(\{.*?\});' % name, html, re.S)
    if m:
        return html[:m.start(1)] + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
    m = re.search(r'const REVW\s*=', html)
    blob = 'const %s=' % name + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + ';\n'
    return html[:m.start()] + blob + html[m.start():]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='data_base')
    ap.add_argument('--html', default=HTML)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--through', help='끝달을 못박음 (예: 2026-10)')
    ap.add_argument('--with-forecast', action='store_true',
                    help='아직 결산 전인 달의 예상매출도 실적으로 같이 셈')
    a = ap.parse_args()

    html = open(a.html, encoding='utf-8', newline='').read()
    D = json.loads(re.search(r'<script>const D = (\{.*?\});</script>', html, re.S).group(1))
    man = json.load(open(os.path.join(a.base, 'manifest.json'), encoding='utf-8'))
    cut = min(man['sales_meta']['last_actual'].values())
    cutm = a.through or ('%s-%s' % (cut[:4], cut[4:]))
    late = sorted(k for k, v in man['sales_meta']['last_actual'].items()
                  if '%s-%s' % (v[:4], v[4:]) < cutm)
    if late and not a.with_forecast:
        raise SystemExit('%s 은(는) %s 까지만 결산됨. --with-forecast 를 같이 줌.'
                         % (' · '.join(late), cut))
    y = int(cutm[:4])
    W26 = ('%d-01' % y, cutm)                     # 올해 1월 ~ 끝달
    W25 = ('%d-01' % (y - 1), '%d%s' % (y - 1, cutm[4:]))   # 전년 같은 구간

    buyers = collections.defaultdict(list)
    for b in csv.DictReader(open(os.path.join(a.base, 'am_buyers.csv'), encoding='utf-8')):
        buyers[norm(b['buyer_name'])].append(b['buyer_code'])

    def cp(x, y):
        i = 0
        while i < min(len(x), len(y)) and x[i] == y[i]: i += 1
        return i

    def find(n):
        """원장과 매출표의 이름 표기가 조금씩 다름. 앞이 길게 겹치면 같은 곳으로 보되,
        'SUPER REPUESTOS' 와 'Super Repuestos Honduras' 처럼 앞이 겹치는 다른 회사가
        있으므로 짧은 쪽 이름의 대부분을 덮을 때만 인정함."""
        if n in ALIAS: return ALIAS[n]
        if n in buyers: return buyers[n]
        best, bn = 0, None
        for k in buyers:
            c = cp(n, k)
            if c < 14 or c < 0.6 * min(len(n), len(k)): continue
            if c > best or (c == best and bn and len(k) > len(bn)): best, bn = c, k
        return buyers[bn] if bn else None

    # 매출코드 → 원장코드(한 고객사가 여러 캠페인에 걸려도 한 번만)
    rules, miss, seenc = {}, [], set()
    for r in D.get('cust_delta', []):
        code = str(r.get('code') or '')
        if not code or code in seenc: continue
        bc = find(norm(r.get('name')))
        if not bc:
            miss.append(r.get('name')); continue
        seenc.add(code)
        for b in bc: rules.setdefault(b, code)

    cur, pre = collections.Counter(), collections.Counter()
    fc = 0.0
    src = os.path.join(a.base, 'am_sales_cat.csv')     # 전 품목이라 품목군 표로 충분함
    for r in csv.DictReader(open(src, encoding='utf-8')):
        if r['is_internal'] == '1': continue
        if r['is_forecast'] == '1' and not a.with_forecast: continue
        code = rules.get(r['buyer_code'])
        if not code: continue
        ym, u = r['month'], float(r['usd'] or 0)
        if not u: continue
        if W26[0] <= ym <= W26[1]:
            cur[code] += u
            if r['is_forecast'] == '1': fc += u
        elif W25[0] <= ym <= W25[1]:
            pre[code] += u

    REVW = {k: round(v, 2) for k, v in cur.items() if v}
    REVP = {k: round(v, 2) for k, v in pre.items() if v}
    meta = {'cut': cutm,
            'note': '참여 고객사의 전 품목 매출 · 1~%d월 · 전년은 같은 구간' % int(cutm[5:])}
    out = put(put(put(html, 'REVW', REVW), 'REVP', REVP), 'REVM', meta)
    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(a.html, 'w', encoding='utf-8', newline='').write(out)

    both = [k for k in REVW if k in REVP]
    b26 = sum(REVW[k] for k in both); b25 = sum(REVP[k] for k in both)
    print(f"캠페인 참여 고객사 매출 (전 품목) · {W25[0]}~{W25[1]} vs {W26[0]}~{W26[1]}"
          + (f"  (그중 결산 전 ${fc:,.0f} — {' · '.join(late)})" if fc else ''))
    print(f"  당해 ${sum(REVW.values()):,.0f} ({len(REVW)}곳)   전년 동기 ${sum(REVP.values()):,.0f} ({len(REVP)}곳)")
    if b25:
        print(f"  양쪽 다 있는 {len(both)}곳  ${b25:,.0f} → ${b26:,.0f}  ({(b26-b25)/b25*100:+.1f}%)")
    if miss: print('  매출표에서 못 찾은 고객사: ' + ' · '.join(sorted(set(miss))))
    print(a.html + (' 갱신됨' if changed else ' 변경 없음'))


if __name__ == '__main__':
    main()
