#!/usr/bin/env python3
"""캠페인 참여 고객사의 '캠페인 기간' 매출 — 당해와 전년 동기를 같은 구간으로.

  python3 scripts/sync_campaign_revenue.py --base data_base

왜 필요한가
  화면의 REVW 는 캠페인 기간 매출인데, 옆에 두던 REV 는 연간 기준이라
  구간이 서로 다름. 그대로 전년 대비를 붙이면 7개월치를 12개월치와
  맞대게 됨. 그래서 전년도 '같은 달 구간'으로 다시 뽑음.

구간
  캠페인 시작월 ~ 종료월. 단 확정 매출 마감월에서 자름 — 안 자르면
  전년은 11월까지, 올해는 9월까지가 되어 전년 대비가 깎임.
  전년은 같은 월 구간(연도만 -1)을 씀.

기준
  매출(출하·청구) · 내부거래와 예상매출 제외 · 그 고객사의 전 품목.
  대상 SKU 만의 매출이 아니고, 오더(수주)와도 더하지 않음.
"""
import argparse, collections, csv, json, os, re, sys

HTML = 'promo_dashboard_v10_6.html'
NORM = re.compile(r'[^A-Z0-9]+')
norm = lambda s: NORM.sub('', (s or '').upper().replace('“', '"').replace('”', '"'))


def put(html, name, obj):
    m = re.search(r'const %s\s*=\s*(\{.*?\});' % name, html, re.S)
    if not m: raise SystemExit('const %s 를 찾지 못했음.' % name)
    return html[:m.start(1)] + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='data_base')
    ap.add_argument('--html', default=HTML)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    html = open(a.html, encoding='utf-8', newline='').read()
    D = json.loads(re.search(r'<script>const D = (\{.*?\});</script>', html, re.S).group(1))
    man = json.load(open(os.path.join(a.base, 'manifest.json'), encoding='utf-8'))
    # 전 법인이 확정된 마지막 달까지만 봄 — 법인마다 마감이 다르면 가장 이른 달
    cut = min(man['sales_meta']['last_actual'].values())
    cutm = '%s-%s' % (cut[:4], cut[4:])

    win = {}
    for c in D.get('campaigns', []):
        if c.get('program') and c.get('start'):
            s, e = c['start'][:7], (c.get('end') or '2026-12')[:7]
            win[(c.get('region'), c['program'])] = (s, min(e, cutm))

    buyers = collections.defaultdict(list)
    for b in csv.DictReader(open(os.path.join(a.base, 'am_buyers.csv'), encoding='utf-8')):
        buyers[norm(b['buyer_name'])].append(b['buyer_code'])

    def cp(x, y):
        i = 0
        while i < min(len(x), len(y)) and x[i] == y[i]: i += 1
        return i

    # 이름이 아예 다르게 적힌 곳만 손으로 이어 줌 (매출표 Buyer code)
    ALIAS = {'GTAVIETNAM': ['551-021']}   # 매출표에는 'CONG TY TNHH THUONG MAI GTA VIET NAM'

    def find(nm_):
        if nm_ in ALIAS: return ALIAS[nm_]
        """이름이 정확히 같지 않은 경우가 있음 — 'Auto Business Corporation Ltd.'(원장) vs
        'Auto Business Corporation Compan'(매출표). 앞부분이 길게 겹치면 같은 곳으로 봄.
        단 'SUPER REPUESTOS' 와 'Super Repuestos Honduras' 처럼 앞이 겹치는 다른 회사가
        있으므로, 겹친 길이가 짧은 쪽 이름의 대부분을 덮을 때만 인정하고
        후보가 여럿이면 가장 길게 겹치는(=가장 구체적인) 쪽을 고름."""
        if nm_ in buyers: return buyers[nm_]
        best, bn = 0, None
        for k in buyers:
            n = cp(nm_, k)
            if n < 14 or n < 0.6 * min(len(nm_), len(k)): continue
            if n > best or (n == best and bn and len(k) > len(bn)):
                best, bn = n, k
        return buyers[bn] if bn else None

    # 고객(원장코드) → (구간, 매출코드들)
    tgt, miss = {}, []
    for r in D.get('cust_delta', []):
        code = str(r.get('code') or '')
        w = win.get((r.get('region'), r.get('program')))
        if not code or not w: continue
        bc = find(norm(r.get('name')))
        if not bc:
            miss.append(r.get('name')); continue
        # 한 고객사가 여러 캠페인에 걸리면 구간은 바깥쪽으로 넓힘
        if code in tgt:
            s, e, bs = tgt[code]
            tgt[code] = (min(s, w[0]), max(e, w[1]), bs | set(bc))
        else:
            tgt[code] = (w[0], w[1], set(bc))

    bymap = collections.defaultdict(list)
    for code, (s, e, bcs) in tgt.items():
        for bc in bcs: bymap[bc].append(code)

    cur = collections.Counter(); pre = collections.Counter()
    src = os.path.join(a.base, 'am_sales_cat.csv')
    for r in csv.DictReader(open(src, encoding='utf-8')):
        if r['is_internal'] == '1' or r['is_forecast'] == '1': continue
        for code in bymap.get(r['buyer_code'], ()):
            s, e, _ = tgt[code]
            ym, u = r['month'], float(r['usd'] or 0)
            if s <= ym <= e: cur[code] += u
            elif ('%d%s' % (int(ym[:4]) + 1, ym[4:])) >= s and \
                 ('%d%s' % (int(ym[:4]) + 1, ym[4:])) <= e: pre[code] += u

    REVW = {k: round(v, 2) for k, v in cur.items() if v}
    REVP = {k: round(v, 2) for k, v in pre.items() if v}
    out = put(html, 'REVW', REVW)
    if re.search(r'const REVP\s*=', out):
        out = put(out, 'REVP', REVP)
    else:
        # REVW 선언 바로 앞에 REVP 를 새로 끼움 (공백 유무와 무관하게 찾음)
        m = re.search(r'const REVW\s*=', out)
        blob = 'const REVP=' + json.dumps(REVP, ensure_ascii=False, separators=(',', ':')) + ';\n'
        out = out[:m.start()] + blob + out[m.start():]
    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(a.html, 'w', encoding='utf-8', newline='').write(out)

    c26, c25 = sum(REVW.values()), sum(REVP.values())
    both = [k for k in REVW if k in REVP]
    b26 = sum(REVW[k] for k in both); b25 = sum(REVP[k] for k in both)
    print(f"캠페인 기간 매출 · 확정 ~{cutm} 에서 자름")
    print(f"  당해 ${c26:,.0f} ({len(REVW)}곳)   전년 동기 ${c25:,.0f} ({len(REVP)}곳)")
    print(f"  양쪽 다 있는 {len(both)}곳 기준  ${b25:,.0f} → ${b26:,.0f}  "
          f"({(b26-b25)/b25*100:+.1f}%)" if b25 else '')
    if miss: print('  매출표에서 못 찾은 고객사: ' + ' · '.join(sorted(set(miss))))
    print(a.html + (' 갱신됨' if changed else ' 변경 없음'))


if __name__ == '__main__':
    main()
