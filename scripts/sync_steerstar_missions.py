#!/usr/bin/env python3
"""SteerStar 추가 오더미션 중 **SKU 기반**인 것들을 한 데 모은다.

  python3 scripts/sync_steerstar_missions.py

내보내는 것
  steerstar_missions.json  — 메인(window.CKSSM) · 효과 분석(const SSM) 공용

왜 따로 있나
  추가 오더미션은 원래 금액 목표만 보던 것이었는데, 그중 셋은 '품번을 넓히는'
  미션이라 금액만 봐서는 달성의 내용을 알 수가 없다.

    OCEANIA / 호주  Kailos International   일본·한국 차종 25년 대비 최대 100% 성장
    CIS / 카자흐스탄 Bauten                KZ 3개년 전체 오더 제품 중 당사 미오더
                                           제품 TOP 200 with Pair SKUs
    CIS / 아제르바이잔 Retems Logistics     AZ 3개년 전체 오더 제품 중 당사 미오더
                                           제품 TOP 80 with Pair SKUs

  Kailos 는 공식 차종 SKU 리스트가 있어 품번 단위까지 떨어진다
  (sync_steerstar_sku.py → steerstar_sku.json). 나머지 둘은 미션을 정의하는
  'TOP 200 / TOP 80 미오더 품번 + Pair SKU' 목록 파일이 아직 없어서, 지금은
  원장으로 셀 수 있는 것까지만 센다. 목록이 들어오면 `--top-kz` / `--top-az` 로
  붙이면 그 목록 기준(전환 n/200 식)으로 바뀐다.

기준
  금액·달성률  SteerStar 공식 관리 파일이 원본 (효과 분석 HTML 의 const SS.rows).
               여기서 다시 계산하지 않는다.
  품번          2025 원장과 2026 원장을 **ctr_code 로** 잇는다. 2025 원장의 sku
               칸은 옛 부품번호(CSL0249G-999)고 2026 은 CTR 코드(CE0732L)라
               sku 로 이으면 전부 '신규'로 잡힌다 — 실제로 그렇게 나왔었다.
  합산          이 미션들은 각 고객사 단독 미션이다. ChoiceKit 연관 오더에
               더하지 않는다 (교집합은 이미 한쪽에서 세고 있다).
"""
import argparse, collections, csv, glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'steerstar_missions.json')
PROMO = os.path.join(ROOT, 'promo_dashboard_v10_6.html')

# SteerStar 공식 행 → 이 스크립트가 다루는 미션. (고객사명, 품번 단위 분석 방식)
MISSIONS = [
    {'key': 'kailos', 'cust': 'Kailos International', 'region': 'OCEANIA',
     'country': '호주', 'src': 'steerstar_sku', 'short': '일본·한국 차종'},
    {'key': 'bauten', 'cust': 'Bauten', 'region': 'CIS',
     'country': '카자흐스탄', 'src': 'ledger', 'short': 'KZ 미오더 TOP 200',
     'top_n': 200},
    {'key': 'retems', 'cust': 'Retems Logistics', 'region': 'CIS',
     'country': '아제르바이잔', 'src': 'ledger', 'short': 'AZ 미오더 TOP 80',
     'top_n': 80},
]


def ss_rows():
    """효과 분석 HTML 의 const SS 에서 미션 행을 읽는다 — 금액의 원본."""
    if not os.path.exists(PROMO):
        sys.exit('promo_dashboard_v10_6.html 이 없음.')
    h = open(PROMO, encoding='utf-8').read()
    m = re.search(r'<script>const SS\s*=\s*(\{.*?\});</script>', h, re.S)
    if not m:
        sys.exit('const SS 를 못 찾음 — 효과 분석 HTML 구조가 바뀐 듯함.')
    SS = json.loads(m.group(1))
    out = {}
    for r in (SS.get('rows') or []):
        out[(r.get('name') or '').strip()] = r
    return out, SS


def ck_scope():
    """orders.csv 가 담는 범위 = ChoiceKit 캠페인의 대상 SKU.

    CIS 원장은 캠페인 대상 품번만 추출한 것이라, 미션 목록 중 ChoiceKit 대상이
    아닌 품번은 **오더가 있어도 이 원장에 안 나온다**. 전환율 분모를 목록 전체로
    잡으면 '안 샀다'가 아니라 '안 보인다'를 안 샀다고 세게 된다 —
    Bauten 은 목록 203종 중 59종만 보이고, 그 59종 중 52종이 전환됐다.
    """
    p = os.path.join(ROOT, 'campaign_target_skus.json')
    if not os.path.exists(p):
        return set()
    cfg = json.load(open(p, encoding='utf-8'))
    out = set()
    for k, c in cfg.items():
        if (c.get('match_by') or 'sku').lower() != 'sku':
            continue
        for x in (c.get('target_skus') or []):
            out.add(str(x).strip().upper())
    return out


def read_mission_list(path):
    """미션을 정의하는 품번 목록. 시트당 열 Code(본 품번) + PAIR(짝 품번).

    '미오더 제품 TOP 200 with Pair SKUs' 의 Pair 는 좌/우 같은 짝 품번이다.
    Bauten 은 Code 200 + Pair 51 인데 대부분 이미 200 안에 있어 합집합 203,
    Retems 는 Code 80 + Pair 20 이 전부 80 안에 들어 합집합도 80 이다.
    전환율 분모는 합집합을 쓴다 — 짝까지 열어야 미션을 다 한 것이므로.
    """
    import openpyxl
    SHEETS = {'Bauten_Mission SKUs': 'bauten', 'Retems_Mission SKUs': 'retems'}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for sn, key in SHEETS.items():
        if sn not in wb.sheetnames:
            print('  ! 시트가 없음:', sn); continue
        it = wb[sn].iter_rows(values_only=True)
        h = [str(x) for x in next(it)]
        if 'Code' not in h:
            sys.exit('%s 에 Code 열이 없음.' % sn)
        ic = h.index('Code'); ip = h.index('PAIR') if 'PAIR' in h else None
        codes, pairs = set(), set()
        for r in it:
            if not r or r[ic] is None:
                continue
            codes.add(str(r[ic]).strip().upper())
            if ip is not None and r[ip]:
                pairs.add(str(r[ip]).strip().upper())
        out[key] = {'codes': codes, 'pairs': pairs}
    wb.close()
    # 업로드 임시 파일명이 그대로 화면에 나가지 않게 정리
    nm = re.sub(r'^[0-9a-f]{6,}-', '', os.path.basename(path))
    return out, nm


def kv_totals(path):
    """전사 오더 원장(KV_Orders_*.html, ORD_Progress_*.csv 기반)에서 고객사별
    연도별 전체 오더를 꺼낸다.

    왜 이걸 보나 — 대시보드의 CIS 원장(cis_data·orders.csv)은 ChoiceKit 캠페인
    고객사만 담고 있어서 아제르바이잔이 통째로 없다. '당사 미오더 제품' 미션은
    캠페인 밖 고객사에도 걸려 있으므로 전사 원장을 봐야 한다.

    D.ord 행 = [오더번호, 고객idx, 접수일오프셋, 납기오프셋, …, 금액(USD), …]
    오프셋 기준일은 D.meta.epoch.
    """
    import datetime
    h = open(path, encoding='utf-8', errors='replace').read()
    m = re.search(r'<script[^>]*>\s*(?:const|var|let)\s+D\s*=\s*(\{.*?\})\s*;?\s*</script>', h, re.S)
    if not m:
        sys.exit('KV_Orders HTML 에서 const D 를 못 찾음.')
    D = json.loads(m.group(1))
    ep = D.get('meta', {}).get('epoch') or '2024-01-01'
    ep = datetime.date(*[int(x) for x in ep.split('-')])
    CUS, REG, CTY = D['cus'], D.get('reg') or [], D.get('cty') or []
    ITM = D.get('itm') or []
    out = {}
    for i, c in enumerate(CUS):
        by, n = collections.Counter(), collections.Counter()
        for r in D['ord']:
            if r[1] != i:
                continue
            off = r[2]
            if off is None or off < -90000:
                continue
            y = (ep + datetime.timedelta(days=off)).year
            by[y] += float(r[9] or 0); n[y] += 1
        if not by:
            continue
        # 오더를 '건' 이 아니라 '접수일' 로 묶는다 — 한 번 보낸 오더가 문서 2~3개로
        # 쪼개져 들어오기 때문이다(280BA26G1B/1C/1S 는 같은 날 한 묶음).
        batch = collections.defaultdict(lambda: {'amt': 0.0, 'qty': 0, 'docs': 0})
        for r in D['ord']:
            if r[1] != i:
                continue
            off = r[2]
            if off is None or off < -90000:
                continue
            d = (ep + datetime.timedelta(days=off)).isoformat()
            e = batch[d]; e['amt'] += float(r[9] or 0); e['qty'] += int(r[7] or 0); e['docs'] += 1
        tl = [{'d': d, 'amt': round(v['amt'], 2), 'qty': v['qty'], 'docs': v['docs']}
              for d, v in sorted(batch.items())]
        # 전사 원장에서 품번이 붙어 있는 유일한 자리 = 백오더 라인(bol).
        # BOL 행 = [고객, 품목, 주문, ?, 잔량, 잔량금액, …, 접수일오프셋, 접수연, MRP연, …]
        lines = []
        for r in (D.get('bol') or []):
            if r[0] != i:
                continue
            it = ITM[r[1]] if r[1] < len(ITM) else ['', '']
            lines.append({'sku': it[0], 'name': it[1] if len(it) > 1 else '',
                          'qty': r[2], 'open_qty': r[4],
                          'amt': round(float(r[5] or 0), 2),
                          'd': (ep + datetime.timedelta(days=r[7])).isoformat()
                               if isinstance(r[7], int) and r[7] > -90000 else ''})
        out[str(c[0]).strip().upper()] = {
            'name': c[0],
            'region': REG[c[1]] if c[1] < len(REG) else '',
            'country': CTY[c[2]] if c[2] < len(CTY) else '',
            'code': c[3],
            'by_year': [{'y': y, 'amt': round(by[y], 2), 'n': n[y]} for y in sorted(by)],
            'timeline': tl,
            'lines': lines,            # 품번이 붙은 줄 (백오더만 — 전량이 아님)
            'first': tl[0]['d'] if tl else '',
            'batches': len(tl),
        }
    return out, (D.get('meta', {}).get('srcOrder') or os.path.basename(path)), \
        (D.get('meta', {}).get('snap') or '')


def kv_find(tot, cust):
    """이름이 조금씩 다르다 — 'Kailos International' vs 'Kailos International Pty Ltd'."""
    k = cust.strip().upper()
    if k in tot:
        return tot[k]
    for kk, v in tot.items():
        if kk.startswith(k) or k.startswith(kk):
            return v
    return None


def chunk_rows(dirn):
    for f in sorted(glob.glob(os.path.join(ROOT, dirn, 'chunk_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        if isinstance(d, dict):
            d = d.get('rows') or d.get('data') or []
        for r in d:
            yield r


def ledger_sku(cust):
    """고객사의 연도별 품번 합계. 키는 ctr_code (양쪽 원장을 잇는 유일한 키)."""
    cu = cust.upper()
    y25, y26 = collections.Counter(), collections.Counter()
    q25, q26 = collections.Counter(), collections.Counter()
    name, last = {}, ''
    d25, d26, od26 = [], [], []
    for dirn in ('data', 'new_data'):
        for r in chunk_rows(dirn):
            if (r.get('customer') or '').upper() != cu:
                continue
            k = str(r.get('ctr_code') or '').strip().upper()
            if not k:
                continue
            d = str(r.get('order_date') or '')[:10]
            amt = float(r.get('amount_usd') or 0)
            if d[:4] == '2025':
                y25[k] += amt; q25[k] += int(r.get('qty') or 0)
                if d: d25.append(d)
            name.setdefault(k, (r.get('product') or '').strip())
    for r in chunk_rows('cis_data'):
        if (r.get('customer') or '').upper() != cu:
            continue
        k = str(r.get('ctr_code') or '').strip().upper()
        if not k:
            continue
        y26[k] += float(r.get('amount_usd') or 0); q26[k] += int(r.get('qty') or 0)
        name.setdefault(k, (r.get('product') or '').strip())
        d = str(r.get('order_date') or '')[:10]
        if d: d26.append(d)
        if d > last: last = d
    # orders.csv 가 2026 의 더 넓은 원장일 수 있다 — 큰 쪽을 쓴다
    o26, oq26 = collections.Counter(), collections.Counter()
    olast = ''
    op = os.path.join(ROOT, 'orders.csv')
    if os.path.exists(op):
        for r in csv.DictReader(open(op, encoding='utf-8-sig')):
            if (r.get('customer') or '').upper() != cu:
                continue
            k = (r.get('CTR Code') or r.get('sku') or '').strip().upper()
            if not k:
                continue
            o26[k] += float(r.get('amount') or 0); oq26[k] += int(float(r.get('qty') or 0))
            name.setdefault(k, (r.get('product') or '').strip())
            d = (r.get('order date') or '')[:10]
            if d: od26.append(d)
            if d > olast: olast = d
    if sum(o26.values()) > sum(y26.values()):
        y26, q26, last = o26, oq26, (olast or last)
        d26 = od26
    return y25, y26, q25, q26, name, last, (min(d25), max(d25)) if d25 else ('', ''), \
        (min(d26), max(d26)) if d26 else ('', '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mission-xlsx', help='SteerStar_Order_Mission_for_Bauten_Retems.xlsx — '
                                           '미션을 정의하는 TOP 200 / TOP 80 품번 목록. '
                                           '시트 Bauten_Mission SKUs · Retems_Mission SKUs, '
                                           '열 Code + PAIR')
    ap.add_argument('--kv', help='전사 오더 원장 대시보드 (KV_Orders_*.html) — '
                                 '고객사별 연도별 전체 오더를 여기서 꺼낸다')
    a = ap.parse_args()

    kvtot, kvsrc, kvsnap = ({}, '', '')
    if a.kv:
        kvtot, kvsrc, kvsnap = kv_totals(a.kv)
    else:  # 이전에 뽑아 둔 값이 있으면 들고 간다 — 원장 HTML 은 리포에 없다
        if os.path.exists(OUT):
            prev = json.load(open(OUT, encoding='utf-8'))
            kvsrc, kvsnap = prev.get('ledger_src', ''), prev.get('ledger_snap', '')
            for m0 in (prev.get('missions') or []):
                if m0.get('total'):
                    kvtot[(m0.get('total', {}).get('name') or m0['cust']).strip().upper()] = m0['total']

    rows, SS = ss_rows()
    tops, tops_src = {}, ''
    if a.mission_xlsx:
        tops, tops_src = read_mission_list(a.mission_xlsx)
    elif os.path.exists(OUT):   # 목록 xlsx 는 리포에 없다 — 앞서 읽어 둔 걸 들고 간다
        prev0 = json.load(open(OUT, encoding='utf-8'))
        tops_src = prev0.get('mission_list_src', '')
        for m0 in (prev0.get('missions') or []):
            L = (m0.get('sku') or {}).get('list')
            if L:
                tops[m0['key']] = {'codes': set(L.get('codes') or []),
                                   'pairs': set(L.get('pairs') or [])}

    out = {'_readme': 'SteerStar 추가 오더미션 중 SKU 기반인 셋. '
                      '금액·달성률은 SteerStar 공식 관리 파일(효과 분석 const SS)이 원본, '
                      '품번은 원장을 ctr_code 로 이어서 센다. '
                      '재생성: python3 scripts/sync_steerstar_missions.py',
           '_basis': '각 고객사 단독 미션 — ChoiceKit 연관 오더에 더하지 않는다.',
           'lead_target': SS.get('lead_target'),
           'ledger_src': kvsrc, 'ledger_snap': kvsnap,
           'mission_list_src': tops_src, 'missions': []}

    for M in MISSIONS:
        r = rows.get(M['cust'])
        if not r:
            print('  ! SteerStar 행을 못 찾음:', M['cust'])
            continue
        rec = {'key': M['key'], 'cust': M['cust'], 'region': M['region'],
               'country': M['country'], 'short': M['short'],
               'mission': (r.get('sub') or '').strip(),
               'act': (r.get('act') or '').strip(), 'when': (r.get('when') or '').strip(),
               'note': (r.get('main') or '').strip(),
               'tgt': r.get('tgt'), 'got': r.get('got'), 'rate': r.get('rate'),
               'leads': r.get('leads'), 'lead_tgt': r.get('lead_tgt')}

        # 전사 오더 원장의 이 고객사 전체 오더 — 미션 대상이 그중 얼마인지 보려면 필요
        t = kv_find(kvtot, M['cust'])
        if t:
            rec['total'] = t
            cur = [x for x in t['by_year'] if x['y'] == 2026]
            prv = [x for x in t['by_year'] if x['y'] == 2025]
            rec['tot26'] = cur[0]['amt'] if cur else 0
            rec['tot25'] = prv[0]['amt'] if prv else 0
            rec['new_cust'] = not any(x['y'] < 2026 for x in t['by_year'])
            # 첫 오더가 2025 하반기 이후면 '램프업 중' — 전년 동기 비교가 성립하지 않는다.
            # 전년에 오더 묶음이 한 번뿐이어도 마찬가지(계절 비교가 아니라 거래 시작이다).
            first = t.get('first') or ''
            prior = [x for x in (t.get('timeline') or []) if x['d'] < '2026-01-01']
            rec['first_order'] = first
            rec['prior_batches'] = len(prior)
            rec['ramp'] = bool(rec['new_cust'] or first >= '2025-07-01' or len(prior) <= 1)
            if rec['tot26'] and r.get('got'):
                rec['share'] = round(r['got'] / rec['tot26'] * 100, 1)

        m_got = float(r.get('got') or 0)
        if M['src'] == 'steerstar_sku':
            p = os.path.join(ROOT, 'steerstar_sku.json')
            if os.path.exists(p):
                K = json.load(open(p, encoding='utf-8'))
                rec['sku'] = {'mode': 'full', 'cut': K.get('cut'),
                              'conv': (K.get('new') or {}).get('n'),
                              'conv_amt': (K.get('new') or {}).get('amt'),
                              'recov': (K.get('recov') or {}).get('n'),
                              'recov_amt': (K.get('recov') or {}).get('amt'),
                              'lost': (K.get('lost') or {}).get('n'),
                              'cover_pct': K.get('cover_pct'),
                              'b25': K.get('b25'), 'a26': K.get('a26'),
                              'detail': 'steerstar_sku.json'}
        else:
            y25, y26, q25, q26, name, cut, sp25, sp26 = ledger_sku(M['cust'])
            top = tops.get(M['key'])
            if not y26 and not y25:
                why = ('대시보드가 쓰는 CIS 원장은 ChoiceKit 캠페인 고객사만 담고 있어 '
                       '이 고객사의 품번 줄이 없음 — 전사 오더 원장에는 있다')
                if rec.get('new_cust'):
                    why += ('. 2026 첫 거래 고객이라 전년 비교 자체가 없다 — '
                            '전 품목이 「당사 미오더」였던 셈이고, 전체 오더 '
                            '$%s 중 미션 대상은 $%s(%s%%)' % (
                                format(round(rec.get('tot26') or 0), ','),
                                format(round(m_got), ','), rec.get('share')))
                rec['sku'] = {'mode': 'none', 'why': why}
                if top:   # 목록은 있으니 미션의 분모라도 적어 둔다
                    L = top['codes'] | top['pairs']
                    kn = [x for x in ((t or {}).get('lines') or []) if x.get('sku')]
                    rec['sku'].update({'top_n': len(top['codes']),
                                       'top_full_n': len(L),
                                       'known_lines': kn,
                                       'known_hit': [x['sku'] for x in kn
                                                     if x['sku'].strip().upper() in L],
                                       'list': {'codes': sorted(top['codes']),
                                                'pairs': sorted(top['pairs'])}})
            else:
                keys26 = [k for k in y26 if y26[k]]
                new = [k for k in keys26 if not y25.get(k)]
                rep = [k for k in keys26 if y25.get(k)]
                items = sorted(({'sku': k, 'name': name.get(k, ''),
                                 'y25': round(y25.get(k, 0), 2), 'y26': round(y26[k], 2),
                                 'qty': q26.get(k, 0),
                                 'kind': '신규' if not y25.get(k) else
                                         ('증가' if y26[k] > y25[k] * 1.02 else
                                          '감소' if y26[k] < y25[k] * 0.98 else '유지')}
                                for k in keys26), key=lambda x: -x['y26'])
                rec['sku'] = {
                    'mode': 'top' if top else 'ledger',
                    'cut': cut,
                    'base_label': '2025 원장' if not top else 'TOP %d 미오더 목록' % M['top_n'],
                    'n25': len([k for k in y25 if y25[k]]), 'a25': round(sum(y25.values()), 2),
                    'n26': len(keys26), 'a26': round(sum(y26.values()), 2),
                    'new_n': len(new), 'new_amt': round(sum(y26[k] for k in new), 2),
                    'rep_n': len(rep), 'rep_amt': round(sum(y26[k] for k in rep), 2),
                    'top': items[:12],
                    'top_new': [x for x in items if x['kind'] == '신규'][:12],
                }
                if top:
                    codes, pairs = top['codes'], top['pairs']
                    full = codes | pairs
                    # 원장이 담는 범위로 좁힌다 — 밖은 '안 샀다' 가 아니라 '안 보인다'
                    scope = ck_scope()
                    seen = (full & scope) if scope else set(full)
                    unseen = full - seen
                    # 목록은 '미오더' 만이 아니라 **저오더 품번**도 함께 담고 있다.
                    # 그래서 전년 오더가 있는 게 정상이고, 미션 효과는 두 갈래로 본다:
                    #   ① 안 사던 걸 열었나 (신규)   ② 사던 걸 더 사게 했나 (증가)
                    # 분류는 sync_sku_impact.py 와 같은 규칙 — ±2% 는 유지.
                    def cls_of(b0, a0):
                        if b0 <= 0:
                            return '신규' if a0 > 0 else '미개척'
                        if a0 <= 0:
                            return '이탈'
                        if a0 > b0 * 1.02: return '증가'
                        if a0 < b0 * 0.98: return '감소'
                        return '유지'
                    items = []
                    for k in sorted(seen):
                        b0, a0 = round(y25.get(k, 0), 2), round(y26.get(k, 0), 2)
                        if b0 <= 0 and a0 <= 0:
                            items.append({'sku': k, 'name': name.get(k, ''), 'y25': 0, 'y26': 0,
                                          'inc': 0, 'qty': 0, 'kind': '미개척',
                                          'pair': k in pairs and k not in codes})
                            continue
                        items.append({'sku': k, 'name': name.get(k, ''), 'y25': b0, 'y26': a0,
                                      'inc': round(a0 - b0, 2), 'qty': q26.get(k, 0),
                                      'kind': cls_of(b0, a0),
                                      'pair': k in pairs and k not in codes})
                    cls = collections.Counter(x['kind'] for x in items)
                    amt = collections.defaultdict(float)
                    for x in items:
                        amt[x['kind']] += x['inc']
                    byk = collections.defaultdict(list)
                    for x in items:
                        byk[x['kind']].append(x)
                    for v in byk.values():
                        v.sort(key=lambda x: -abs(x['inc']))
                    hit = [x for x in items if x['y26'] > 0]
                    off = [k for k in keys26 if k not in full]
                    l25 = round(sum(x['y25'] for x in items), 2)
                    l26 = round(sum(x['y26'] for x in items), 2)
                    l25_all = round(sum(y25.values()), 2)   # 목록 밖까지 포함한 원장 합
                    l26_all = round(sum(y26.values()), 2)
                    rec['sku'].update({
                        'top_n': len(codes), 'top_full_n': len(full),
                        'top_seen_n': len(seen), 'top_unseen_n': len(unseen),
                        'top_hit': len(hit),
                        'top_amt': round(sum(x['y26'] for x in hit), 2),
                        # 분모는 '원장에 보이는 품번' — 목록 전체로 잡으면 안 보이는 걸
                        # 안 샀다고 세게 된다
                        'top_pct': round(len(hit) / len(seen) * 100, 1) if seen else None,
                        'top_pct_all': round(len(hit) / len(full) * 100, 1) if full else None,
                        'off_n': len(off), 'off_amt': round(sum(y26[k] for k in off), 2),
                        # 목록 전체의 전년 → 당해. 미션 효과는 이 성장으로 읽는다.
                        'l25': l25, 'l26': l26,
                        'l_inc': round(l26 - l25, 2),
                        'l_yoy': round((l26 / l25 - 1) * 100, 1) if l25 > 0 else None,
                        'cls': dict(cls),
                        'cls_amt': {k: round(v, 2) for k, v in amt.items()},
                        # 증가액 분해 — 어디서 왔는지
                        'decomp': [{'k': '신규 전환 (전년 오더 없던 품번)', 'v': round(amt['신규'], 2)},
                                   {'k': '증가 (전년에도 사던 품번이 더 커짐)', 'v': round(amt['증가'], 2)},
                                   {'k': '감소', 'v': round(amt['감소'], 2)},
                                   {'k': '이탈 (전년 있다 올해 0)', 'v': round(amt['이탈'], 2)}],
                        # 이 원장이 그 고객사 오더를 얼마나 담고 있나 —
                        # 전사 원장(KV) 대비 비율. 적게 담고 있으면 '없음'을
                        # 근거로 하는 숫자(이탈·감소·YoY)는 못 믿는다.
                        'cov25': (round(l25_all / rec['tot25'] * 100, 1)
                                  if rec.get('tot25') else None),
                        'cov26': (round(l26_all / rec['tot26'] * 100, 1)
                                  if rec.get('tot26') else None),
                        'top_new': byk['신규'][:12],
                        'top_up': byk['증가'][:12],
                        'top_dn': (byk['감소'] + byk['이탈'])[:10],
                        'list': {'codes': sorted(codes), 'pairs': sorted(pairs)},
                    })
                    # 원장이 반쪽이면 '없음'을 근거로 한 수치는 내보내되 못 믿는다고 표시
                    cv25, cv26 = rec['sku'].get('cov25'), rec['sku'].get('cov26')
                    rec['sku']['partial'] = bool(
                        (cv25 is not None and cv25 < 90) or (cv26 is not None and cv26 < 90))
                    # 램프업 중인 거래처는 전년이 '시즌'이 아니라 '첫 거래'다.
                    # 이탈·감소·YoY 는 뜻이 없으므로 내보내지 않는다.
                    if rec.get('ramp'):
                        # 램프업 거래처에서는 '전년' 이 시즌이 아니라 **첫 오더**다.
                        # 그래서 말을 바꾼다 — 줄었다/끊겼다가 아니라 '아직 재오더 안 됨'.
                        rec['sku']['ramp'] = True
                        rec['sku']['base_label'] = '첫 오더(%s) 기준' % (rec.get('first_order') or '')
                        rec['sku']['ramp_cls'] = {
                            '첫 오더에 없던 품번을 새로 담음': cls.get('신규', 0),
                            '첫 오더에도 있었고 더 담음': cls.get('증가', 0),
                            '첫 오더만큼 담음': cls.get('유지', 0),
                            '아직 재오더 안 됨': cls.get('이탈', 0) + cls.get('감소', 0),
                            '한 번도 오더 없음': cls.get('미개척', 0),
                        }
                        rec['sku']['ramp_amt'] = {
                            'new': round(amt['신규'], 2), 'up': round(amt['증가'], 2),
                            'grow': round(amt['신규'] + amt['증가'], 2),
                        }
                        rec['sku']['pending_n'] = cls.get('이탈', 0) + cls.get('감소', 0)
                        for k0 in ('l_yoy', 'decomp', 'top_dn'):
                            rec['sku'].pop(k0, None)
                    rec['sku']['span25'] = sp25
                    rec['sku']['span26'] = sp26
                else:
                    rec['sku']['caveat'] = (
                        '미션을 정의하는 TOP %d 미오더 품번 목록이 아직 없어서, '
                        '원장으로 셀 수 있는 2025 대비 신규 품번만 센 값이다. '
                        '미션의 분모(TOP %d 중 몇 종 전환)가 아니다.' % (M['top_n'], M['top_n']))
        out['missions'].append(rec)

    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else None
    changed = old != out
    if changed:
        json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # 효과 분석 HTML 의 const SSM 도 같이 깐다 — 메인은 이 JSON 을 fetch 하지만
    # 효과 분석은 단일 파일이라 HTML 안에 박혀 있어야 한다.
    h = open(PROMO, encoding='utf-8').read()
    blk = '<script>const SSM = %s;</script>' % json.dumps(out, ensure_ascii=False,
                                                          separators=(',', ':'))
    if re.search(r'<script>const SSM = .*?</script>', h, re.S):
        h2 = re.sub(r'<script>const SSM = .*?</script>', lambda _: blk, h, count=1, flags=re.S)
    else:
        m = re.search(r'<script>const KJK = .*?</script>\n', h, re.S)
        if not m:
            sys.exit('const KJK 블록을 못 찾음 — const SSM 을 넣을 자리가 없음.')
        h2 = h[:m.end()] + blk + '\n' + h[m.end():]
    if h2 != h:
        open(PROMO, 'w', encoding='utf-8').write(h2)
        print('promo_dashboard_v10_6.html 의 const SSM 갱신됨')

    print('SteerStar SKU 기반 추가 오더미션 %d건' % len(out['missions']))
    for m in out['missions']:
        s = m.get('sku') or {}
        if m.get('tot26'):
            pass
        line = '  %-22s %-8s 목표 $%s → $%s (%s%%)' % (
            m['cust'], m['country'], format(round(m['tgt'] or 0), ','),
            format(round(m['got'] or 0), ','), m['rate'])
        print(line)
        if m.get('tot26'):
            print('      전사 원장 전체 오더 25년 $%s → 26년 $%s · 미션이 그중 %s%%%s'
                  % (format(round(m.get('tot25') or 0), ','), format(round(m['tot26']), ','),
                     m.get('share'), ' · 26년 첫 거래 고객' if m.get('new_cust') else ''))
        if s.get('mode') == 'full':
            print('      품번: 신규 %s종 · 재전환 %s종 · 확장 기여 %s%%'
                  % (s.get('conv'), s.get('recov'), s.get('cover_pct')))
        elif s.get('mode') == 'ledger':
            print('      품번(원장 ~%s): 26년 %s종 $%s · 그중 2025 미오더 %s종 $%s'
                  % (s.get('cut'), s.get('n26'), format(round(s.get('a26') or 0), ','),
                     s.get('new_n'), format(round(s.get('new_amt') or 0), ',')))
            print('      ※ ' + s.get('caveat', ''))
        elif s.get('mode') == 'top':
            print('      미션 목록 %s종(TOP %s + Pair) 중 원장에 보이는 건 %s종 — '
                  '그중 %s종 전환 (%s%%) $%s'
                  % (s.get('top_full_n'), s.get('top_n'), s.get('top_seen_n'),
                     s.get('top_hit'), s.get('top_pct'),
                     format(round(s.get('top_amt') or 0), ',')))
            print('      나머지 %s종은 ChoiceKit 대상 SKU 가 아니라 이 원장에 아예 안 나옴 '
                  '— 전환 여부 확인 불가' % s.get('top_unseen_n'))
            if s.get('ramp'):
                print('      ※ 램프업 거래처(첫 오더 %s) — 전년 동기 비교가 성립하지 않아 '
                      '이탈·감소·YoY 는 내보내지 않음' % (m.get('first_order') or '?'))
            if s.get('ramp'):
                ra = s.get('ramp_amt') or {}
                print('      첫 오더 $%s → 2026 $%s · 오더가 커진 몫 +$%s'
                      % (format(round(s.get('l25') or 0), ','),
                         format(round(s.get('l26') or 0), ','),
                         format(round(ra.get('grow') or 0), ',')))
                for k0, v0 in (s.get('ramp_cls') or {}).items():
                    if v0: print('        %-28s %3d종' % (k0, v0))
            else:
                print('      목록 전체 전년 $%s → 당해 $%s (%s%%) · %s'
                      % (format(round(s.get('l25') or 0), ','),
                         format(round(s.get('l26') or 0), ','), s.get('l_yoy'),
                         ' · '.join('%s %d종' % (k, v) for k, v in (s.get('cls') or {}).items())))
            for d0 in (s.get('decomp') or []):   # 램프업이면 비어 있다
                if d0['v']:
                    print('        %-34s %s$%s' % (d0['k'], '+' if d0['v'] > 0 else '-',
                                                    format(round(abs(d0['v'])), ',')))
        else:
            print('      품번: ' + (s.get('why') or '데이터 없음'))
    print('steerstar_missions.json ' + ('갱신됨' if changed else '변경 없음'))


if __name__ == '__main__':
    main()
