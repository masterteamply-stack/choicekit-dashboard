#!/usr/bin/env python3
"""SKU 기반 오더 전환 캠페인의 품번 단위 효과를 한 군데서 집계.

  python3 scripts/sync_sku_impact.py [--check]

내보내는 것
  sku_impact.json                       — 단일 소스
  promo_dashboard_v10_6.html 의 const SKUI — 효과 분석 대시보드가 읽음
  (index.html 은 sku_impact.json 을 받아 같은 값을 그린다)

무엇을 세나 — index.html renderSkuAggregate 와 같은 잣대
  대상    SKU 기반 캠페인(match_by != customer)의 target_skus 합집합.
          품번별 허용 권역은 캠페인별로 따로 — Asian/European=CIS,
          Portfolio=MENA, MarketFit=LATAM.
  권역    SKU 대상 프로모션을 실제 집행한 권역만. orders.csv 의 SKU 캠페인
          행에서 뽑으므로 NA·KR·ASIA(전 품목·고객 기반 캠페인만 있는 곳)는
          자동으로 빠진다.
  기간    캠페인 시작일(marketing.csv kpi_metric=STARTED, 2026-01-02 하한)
          ~ 오더 원장 마감일. 전년은 같은 날짜 구간.
  고객    전년도 '그 캠페인의 고객사' 만. 캠페인 밖 고객사의 전년 오더는
          빼고, 뺀 금액을 따로 적어 둔다(예전엔 이게 전년을 81% 부풀렸음).

품번 분류 (전년 → 당해)
  신규 전환   0  → >0     오더가 없던 품번이 열린 것
  증가       >0 → 더 큼
  유지       >0 → 거의 같음(±2%)
  감소       >0 → 더 작음(0 아님)
  이탈       >0 → 0
  미전환      0  → 0       대상이지만 두 해 모두 오더 없음
"""
import argparse, collections, csv, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'sku_impact.json')
FLOOR = '2026-01-02'
# Algeria · EURL TASSRIAA 오더 제외 (사용자 지정 · 두 대시보드 공통)
EXCL_CUST = {'EURL TASSRIAA'}
# index.html normalizeRegion 의 ALIAS 와 같게 — 레거시 키(MIDDLE_EAST·AFRICA·
# N_AMERICA·ASIA_PACIFIC)를 접지 않으면 MENA baseline 을 통째로 버린다.
RGN = {'MENA': 'MENA', 'MIDDLE_EAST': 'MENA', 'MIDDLEEAST': 'MENA', 'ME': 'MENA',
       'AFRICA': 'MENA', 'AFR': 'MENA', 'EMEA': 'MENA',
       'EUROPE': 'EUROPE', 'EU': 'EUROPE',
       'CIS': 'CIS', 'RUS': 'RUS', 'RUSSIA': 'CIS', 'RUSSIAN_FEDERATION': 'RUS',
       'LATAM': 'LATAM', 'LATIN_AMERICA': 'LATAM',
       'NA': 'NA', 'N_AMERICA': 'NA', 'NORTH_AMERICA': 'NA', 'NAMERICA': 'NA',
       'ASIA': 'ASIA', 'ASIA_PACIFIC': 'ASIA', 'APAC': 'ASIA', 'AP': 'ASIA',
       'PACIFIC': 'ASIA', 'SEA': 'ASIA', 'SOUTH_EAST_ASIA': 'ASIA', 'SOUTHEAST_ASIA': 'ASIA',
       'DOMESTIC': 'KOREA', 'KOREA': 'KOREA', 'KR': 'KOREA', '한국': 'KOREA',
       'OCEANIA': 'OCEANIA'}


def nrg(s):
    s = str(s or '').strip()
    if not s: return ''
    s = re.sub(r'_+', '_', re.sub(r'[\s\-/]+', '_', s.upper().replace('&', 'AND').replace('.', '')))
    return RGN.get(s, s)


def num(x):
    try: return float(str(x).replace(',', '').strip() or 0)
    except Exception: return 0.0


def shift1y(d):
    return '%d%s' % (int(d[:4]) - 1, d[4:]) if d else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--dump', help='품번별 집행 전/후를 JSON 으로 — 메인 대시보드와 맞춰 볼 때')
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(ROOT, 'campaign_target_skus.json'), encoding='utf-8'))
    sku_camps = {p: c for p, c in cfg.items()
                 if str(c.get('match_by') or 'sku').lower() != 'customer'}
    if not sku_camps: sys.exit('SKU 기반 캠페인이 없음.')

    # index.html renderSkuAggregate 와 같은 carve-out — CTR MarketFit 태그가 붙었지만
    # 실제로는 Mexico Awakening·로컬 SELL-OUT 몫인 구간
    CARVE = {'REFATRIX': ('2026-02-11', '2026-11-30'),
             'PLUSCAR S.A': ('2026-08-01', '2026-10-31'),
             'SUPER REPUESTOS': ('2026-08-01', '2026-10-31')}

    # 품번 → 캠페인 / 허용 권역
    sku_promo, sku_rgn, tgt = {}, {}, set()
    sku_rgn_promo = {}          # (품번, 권역) → 캠페인
    own = {p: {str(s).strip().upper() for s in (c.get('target_skus') or [])}
           for p, c in sku_camps.items()}
    for p, c in sku_camps.items():
        rs = c.get('region') or []
        rs = [nrg(x) for x in (rs if isinstance(rs, list) else [rs]) if x]
        for s in (c.get('target_skus') or []):
            k = str(s).strip().upper()
            if not k: continue
            # index.html skuToPromo 와 같게 — 두 캠페인에 걸친 품번은 나중 캠페인 귀속
            tgt.add(k); sku_promo[k] = p
            if rs:
                sku_rgn.setdefault(k, set()).update(rs)
                # promoKeyOfOrder 의 ctrMapR 과 같게 — 품번×권역으로 먼저 찾는다.
                # 한 품번이 CIS(Asian vehicle)와 LATAM(MarketFit)에 같이 걸리면
                # 행의 권역에 맞는 캠페인으로 귀속돼야 전년 고객 명부가 맞는다.
                for r1 in rs: sku_rgn_promo[(k, r1)] = p
            else:
                sku_rgn_promo.setdefault(('*', k), p)

    # 캠페인 시작일 — marketing.csv. index.html 과 같은 알고리즘:
    #   kpi_metric=STARTED 가 보이면 그 뒤의 비-STARTED 행은 무시하고 STARTED 최소값을 쓴다.
    #   STARTED 보다 앞서 나온 비-STARTED 행이 더 이르면 그 값이 남는다(파일 순서 의존 — 원본과 동일).
    #   열 이름은 'Start.date' (index.html 이 date 로 매핑해 읽는 그 열).
    byp, has = {}, set()
    with open(os.path.join(ROOT, 'marketing.csv'), encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            d = (r.get('Start.date') or r.get('date') or r.get('execution_date') or '').strip()[:10]
            p = (r.get('promotion_category') or '').strip()
            if not d or not p: continue
            if (r.get('kpi_metric') or '').strip().upper() == 'STARTED':
                if p not in byp or d < byp[p]: byp[p] = d
                has.add(p)
            elif p not in has:
                if p not in byp or d < byp[p]: byp[p] = d
    start = {p: max(byp[p], FLOOR) for p in sku_camps if byp.get(p)}

    # orders.csv — 당해 (캠페인 태그가 붙은 SKU 캠페인 행만)
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'orders.csv'), encoding='utf-8-sig')))
    cut = max((r.get('order date') or '')[:10] for r in rows if r.get('order date'))
    exec_rgn, roster = set(), collections.defaultdict(set)
    cur = collections.defaultdict(float)     # sku → 당해 금액
    cur_q = collections.defaultdict(float)
    cur_cust = collections.defaultdict(set)
    n_ord = 0
    for r in rows:
        p = (r.get('promotion_category') or '').strip()
        if p not in sku_camps: continue
        if (r.get('customer') or '').strip().upper() in EXCL_CUST: continue
        s = (r.get('sku') or '').strip().upper()
        if not s: continue
        rg = nrg(r.get('region'))
        exec_rgn.add(rg)
        roster[p].add((r.get('customer') or '').strip().upper())
        d = (r.get('order date') or '')[:10]
        if not d or d < start.get(p, '9999') or d > cut: continue
        # 태그가 SKU 캠페인인데 그 캠페인의 target_skus 에 없으면 미귀속(OTHER)
        if own.get(p) and s not in own[p]: continue
        if p == 'CTR MarketFit Campaign':
            co = CARVE.get((r.get('customer') or '').strip())
            if co and co[0] <= d <= co[1]: continue
        if s in sku_rgn and rg not in sku_rgn[s]: continue
        cur[s] += num(r.get('amount')); cur_q[s] += num(r.get('qty'))
        cur_cust[s].add((r.get('customer') or '').strip()); n_ord += 1
    for p, c in sku_camps.items():
        for x in (c.get('target_customers') or []):
            roster[p].add(str(x).strip().upper())

    # baseline — 전년
    man = os.path.join(ROOT, 'baseline_data')
    pre = []
    for f in sorted(glob.glob(os.path.join(man, 'chunk_*.json'))):
        pre += json.load(open(f, encoding='utf-8'))
    prv = collections.defaultdict(float)
    prv_q = collections.defaultdict(float)
    prv_cust = collections.defaultdict(set)
    drop_amt, drop_n = 0.0, 0
    out_rgn = collections.defaultdict(float)     # 제외된 권역별 금액
    for o in pre:
        s = str(o.get('sku') or '').strip().upper()
        if not s or s not in tgt: continue
        if (o.get('customer') or '').strip().upper() in EXCL_CUST: continue
        rg = nrg(o.get('region'))
        if rg not in exec_rgn:
            out_rgn[rg] += o.get('amount_usd') or 0; continue
        if s in sku_rgn and rg not in sku_rgn[s]: continue
        p = sku_rgn_promo.get((s, rg)) or sku_promo.get(s)
        d = (o.get('order_date') or '')[:10]
        if not p or not d: continue
        f0, f1 = shift1y(start.get(p, '')), shift1y(cut)
        if not f0 or d < f0 or d > f1: continue
        amt = o.get('amount_usd') or 0
        if roster[p] and (o.get('customer') or '').strip().upper() not in roster[p]:
            drop_amt += amt; drop_n += 1; continue
        prv[s] += amt; prv_q[s] += o.get('qty') or 0
        prv_cust[s].add((o.get('customer') or '').strip())

    # 품번 분류
    cls = collections.Counter()
    buckets = {k: [] for k in ('신규', '증가', '유지', '감소', '이탈')}
    for s in sorted(tgt):
        b, af = round(prv.get(s, 0), 2), round(cur.get(s, 0), 2)
        if b <= 0 and af <= 0: cls['미전환'] += 1; continue
        if b <= 0: k = '신규'
        elif af <= 0: k = '이탈'
        elif af > b * 1.02: k = '증가'
        elif af < b * 0.98: k = '감소'
        else: k = '유지'
        cls[k] += 1
        buckets[k].append({'sku': s, 'promo': sku_promo.get(s), 'before': b, 'after': af,
                           'inc': round(af - b, 2),
                           'cust': len(cur_cust.get(s) or prv_cust.get(s) or [])})
    for k in buckets:
        buckets[k].sort(key=lambda x: -abs(x['inc']))

    tb, ta = round(sum(prv.values()), 2), round(sum(cur.values()), 2)
    conv = sum(1 for s in tgt if cur.get(s, 0) > 0)
    D = {
        'src': 'orders.csv + baseline_data · campaign_target_skus.json · marketing.csv',
        'cut': cut, 'floor': FLOOR,
        'camps': sorted(sku_camps.keys()),
        'camp_start': {p: start[p] for p in sorted(start)},
        'regions': sorted(exec_rgn),
        'regions_out': {k: round(v) for k, v in sorted(out_rgn.items(), key=lambda x: -x[1])},
        'tgt_sku': len(tgt), 'conv_sku': conv,
        'conv_rate': round(conv / len(tgt) * 100, 1) if tgt else None,
        'before': tb, 'after': ta,
        'delta': round(ta - tb, 2),
        'yoy': round((ta / tb - 1) * 100, 1) if tb > 0 else None,
        'orders': n_ord,
        'drop_amt': round(drop_amt), 'drop_ords': drop_n,
        'cls': dict(cls),
        'new_amt': round(sum(x['after'] for x in buckets['신규'])),
        'up_amt': round(sum(x['inc'] for x in buckets['증가'])),
        'dn_amt': round(sum(x['inc'] for x in buckets['감소'] + buckets['이탈'])),
        'top': {k: buckets[k][:10] for k in buckets},
        'by_camp': [],
        'extra': [],        # orders.csv 밖 원장을 쓰는 SKU 캠페인 (중국차)
    }

    # ── 중국차 프로모션 — orders.csv 에 태그가 없고 원장이 따로임 ──────────────
    #   금액·품번 수는 cn_promo.json(② 중국전용 품번) 을 그대로 가져온다.
    #   기준이 다름: 월 단위 · 기준일 2026-10-26 · 2026-04 부터. 섞지 않게 따로 둠.
    cnf = os.path.join(ROOT, 'cn_promo.json')
    if os.path.exists(cnf):
        CN = json.load(open(cnf, encoding='utf-8'))
        rs = [r for r in CN.get('rows') or [] if r.get('started')]
        if rs:
            b = round(sum(r.get('cn25') or 0 for r in rs), 2)
            af = round(sum(r.get('cn26') or 0 for r in rs), 2)
            D['extra'].append({
                'p': '중국차 프로모션', 'start': min(r.get('from') or '' for r in rs),
                'cut': CN.get('cut'), 'n': CN.get('tgt_sku'),
                'conv': CN.get('union26'), 'conv_prev': CN.get('union25'),
                'new': None,
                'before': b, 'after': af, 'inc': round(af - b, 2),
                'yoy': round((af / b - 1) * 100, 1) if b > 0 else None,
                'cust': sum(r.get('cn26_cust') or 0 for r in rs),
                'region': [r['region'] for r in rs],
                'basis': '② 중국전용 품번 · 월 단위 · 원장 ~%s · 2026-04부터' % CN.get('cut'),
                'note': '품번별 전년 비교는 중국차 원장에 전년 품번 행이 없어 권역 단위까지만 가능'})
            D['tgt_all'] = D['tgt_sku'] + (CN.get('tgt_sku') or 0)
            D['conv_all'] = D['conv_sku'] + (CN.get('union26') or 0)
            D['before_all'] = round(tb + b, 2)
            D['after_all'] = round(ta + af, 2)
            D['delta_all'] = round(D['after_all'] - D['before_all'], 2)
            D['yoy_all'] = round((D['after_all'] / D['before_all'] - 1) * 100, 1) if D['before_all'] > 0 else None

    for p in sorted(sku_camps):
        ss = [s for s in tgt if sku_promo.get(s) == p]
        b = round(sum(prv.get(s, 0) for s in ss), 2); af = round(sum(cur.get(s, 0) for s in ss), 2)
        nnew = sum(1 for s in ss if prv.get(s, 0) <= 0 < cur.get(s, 0))
        D['by_camp'].append({
            'p': p, 'start': start.get(p), 'n': len(ss),
            'conv': sum(1 for s in ss if cur.get(s, 0) > 0), 'new': nnew,
            'before': b, 'after': af, 'inc': round(af - b, 2),
            'yoy': round((af / b - 1) * 100, 1) if b > 0 else None,
            # 집행 권역은 그 캠페인 설정값 — 품번 쪽 합집합을 쓰면 두 캠페인에
            # 걸친 품번 때문에 남의 권역이 섞여 보임
            'region': [nrg(x) for x in ((sku_camps[p].get('region') or [])
                       if isinstance(sku_camps[p].get('region'), list)
                       else ([sku_camps[p]['region']] if sku_camps[p].get('region') else []))]
                      or sorted(exec_rgn)})

    if a.dump:
        json.dump({s: {'b': round(prv.get(s, 0), 2), 'a': round(cur.get(s, 0), 2),
                       'p': sku_promo.get(s)} for s in sorted(tgt)
                   if prv.get(s, 0) or cur.get(s, 0)},
                  open(a.dump, 'w', encoding='utf-8'), ensure_ascii=False)
        print('품번별 덤프 → ' + a.dump)

    json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    html = open(H, encoding='utf-8', newline='').read()
    blk = '<script>const SKUI = ' + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + ';</script>'
    pat = re.compile(r'<script>const SKUI = \{.*?\};</script>', re.S)
    if pat.search(html):
        new = pat.sub(lambda m: blk, html, count=1)
    else:
        anchor = '<script>const AP = '
        if anchor not in html: sys.exit('const SKUI 자리를 만들 기준(const AP)을 찾지 못했음.')
        new = html.replace(anchor, blk + '\n' + anchor, 1)

    print(f"대상 {D['tgt_sku']:,}종 · 오더 전환 {D['conv_sku']:,}종 ({D['conv_rate']}%)")
    print(f"집행 전 ${tb:,.0f} → 집행 후 ${ta:,.0f} ({'+' if D['delta']>=0 else ''}{D['delta']:,.0f} · {D['yoy']}%)")
    print(f"기간 캠페인 시작 ~ {cut} · 권역 {' · '.join(D['regions'])}")
    print(f"제외 — 캠페인 밖 고객사 ${D['drop_amt']:,.0f}({D['drop_ords']:,}건) · "
          f"비집행 권역 {' · '.join('%s $%s' % (k, format(v, ',')) for k, v in D['regions_out'].items()) or '없음'}")
    print('분류 ' + ' · '.join('%s %d종' % (k, v) for k, v in D['cls'].items()))
    for e in D['extra']:
        print(f"+ {e['p']} — 대상 {e['n']}종 · 전환 {e['conv']}종 · "
              f"${e['before']:,.0f} → ${e['after']:,.0f} ({e['yoy']}%) · {e['basis']}")
    if D.get('tgt_all'):
        print(f"합산 대상 {D['tgt_all']:,}종 · 전환 {D['conv_all']:,}종 · "
              f"${D['before_all']:,.0f} → ${D['after_all']:,.0f} ({D['yoy_all']}%)")
    if a.check:
        print('변경 있음' if new != html else '변경 없음'); return
    if new != html: open(H, 'w', encoding='utf-8', newline='').write(new)
    print('sku_impact.json · promo_dashboard_v10_6.html(const SKUI) 갱신됨')


if __name__ == '__main__':
    main()
