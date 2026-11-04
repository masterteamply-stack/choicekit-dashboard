#!/usr/bin/env python3
"""캠페인 매출 — 캠페인마다 자기 스코프대로만 셈.

  python3 scripts/sync_campaign_revenue.py --base data_base

무엇을 세나
  캠페인이 대상 SKU 를 지정했으면  그 SKU 의 매출만
  전 품목 캠페인이면              그 고객사의 전 품목 매출
  둘 다 캠페인 기간 안의 달만 봄. '그 고객사의 전 품목'을 한꺼번에
  더하면 캠페인과 무관한 매출이 섞임.

구간
  캠페인 시작월 ~ 종료월을, 품번까지 온전한 마지막 달에서 자름.
  결산 전인 달은 예상매출에 품번이 없어(item_code='') 대상 SKU 로
  잡히지 않음 — 그 달을 넣으면 올해만 0 이 되어 전년 대비가 깎임.
  전년은 같은 월 구간(연도만 -1)을 씀.

중복
  한 고객사가 여러 캠페인에 걸릴 수 있음. (고객·품번·월) 한 줄은
  한 번만 셈 — 캠페인별로 더하면 겹친 몫이 두 번 들어감.

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
    a = ap.parse_args()

    html = open(a.html, encoding='utf-8', newline='').read()
    D = json.loads(re.search(r'<script>const D = (\{.*?\});</script>', html, re.S).group(1))
    man = json.load(open(os.path.join(a.base, 'manifest.json'), encoding='utf-8'))
    # 품번까지 온전한 마지막 달 = 법인 중 가장 이른 마감월
    cut = min(man['sales_meta']['last_actual'].values())
    cutm = '%s-%s' % (cut[:4], cut[4:])

    TS = json.load(open('campaign_target_skus.json', encoding='utf-8'))
    skus = {k: set(v['target_skus']) for k, v in TS.items()
            if v.get('match_by') == 'sku' and v.get('target_skus')}

    win = {}
    for c in D.get('campaigns', []):
        if c.get('program') and c.get('start'):
            win[(c.get('region'), c['program'])] = (c['start'][:7],
                                                    min((c.get('end') or '2026-12')[:7], cutm))

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

    # 매출코드 → [(원장코드, 시작월, 끝월, 대상SKU 또는 None)]
    rules = collections.defaultdict(list)
    miss, scoped, allitem = [], set(), set()
    for r in D.get('cust_delta', []):
        code = str(r.get('code') or '')
        prog = r.get('program')
        w = win.get((r.get('region'), prog))
        if not code or not w: continue
        bc = find(norm(r.get('name')))
        if not bc:
            miss.append(r.get('name')); continue
        sk = skus.get(prog)
        (scoped if sk else allitem).add(prog)
        for b in bc: rules[b].append((code, w[0], w[1], sk))

    cur, pre = collections.Counter(), collections.Counter()
    seen_c, seen_p = set(), set()      # (매출코드, 품번, 월) 중복 방지
    src = os.path.join(a.base, 'am_sales_sku.csv.gz')
    with gzip.open(src, 'rt', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rs = rules.get(r['buyer_code'])
            if not rs: continue
            ym, it, u = r['month'], r['item_code'], float(r['usd'] or 0)
            if not u: continue
            nxt = '%d%s' % (int(ym[:4]) + 1, ym[4:])
            key = (r['buyer_code'], it, ym)
            for code, s, e, sk in rs:
                if sk is not None and it not in sk: continue
                if s <= ym <= e:
                    if key in seen_c: break
                    seen_c.add(key); cur[code] += u; break
                if s <= nxt <= e:
                    if key in seen_p: break
                    seen_p.add(key); pre[code] += u; break

    REVW = {k: round(v, 2) for k, v in cur.items() if v}
    REVP = {k: round(v, 2) for k, v in pre.items() if v}
    meta = {'cut': cutm,
            'note': '대상 SKU 캠페인은 그 SKU 만 · 전 품목 캠페인은 전 품목 · ~%s' % cutm}
    out = put(put(put(html, 'REVW', REVW), 'REVP', REVP), 'REVM', meta)
    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(a.html, 'w', encoding='utf-8', newline='').write(out)

    both = [k for k in REVW if k in REVP]
    b26 = sum(REVW[k] for k in both); b25 = sum(REVP[k] for k in both)
    print(f"캠페인 매출 · 스코프별 · ~{cutm} 에서 자름")
    print(f"  대상 SKU 캠페인 {len(scoped)}개 · 전 품목 캠페인 {len(allitem)}개")
    print(f"  당해 ${sum(REVW.values()):,.0f} ({len(REVW)}곳)   전년 동기 ${sum(REVP.values()):,.0f} ({len(REVP)}곳)")
    if b25:
        print(f"  양쪽 다 있는 {len(both)}곳  ${b25:,.0f} → ${b26:,.0f}  ({(b26-b25)/b25*100:+.1f}%)")
    if miss: print('  매출표에서 못 찾은 고객사: ' + ' · '.join(sorted(set(miss))))
    print(a.html + (' 갱신됨' if changed else ' 변경 없음'))


if __name__ == '__main__':
    main()
