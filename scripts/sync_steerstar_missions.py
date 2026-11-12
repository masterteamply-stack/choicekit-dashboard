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
            if d > olast: olast = d
    if sum(o26.values()) > sum(y26.values()):
        y26, q26, last = o26, oq26, (olast or last)
    return y25, y26, q25, q26, name, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top-kz', help='KZ 미오더 TOP 200 품번 목록 (CTR 코드 1줄 1개)')
    ap.add_argument('--top-az', help='AZ 미오더 TOP 80 품번 목록')
    a = ap.parse_args()

    rows, SS = ss_rows()
    tops = {}
    for key, path in (('bauten', a.top_kz), ('retems', a.top_az)):
        if not path:
            continue
        codes = {ln.strip().upper() for ln in open(path, encoding='utf-8') if ln.strip()}
        tops[key] = codes

    out = {'_readme': 'SteerStar 추가 오더미션 중 SKU 기반인 셋. '
                      '금액·달성률은 SteerStar 공식 관리 파일(효과 분석 const SS)이 원본, '
                      '품번은 원장을 ctr_code 로 이어서 센다. '
                      '재생성: python3 scripts/sync_steerstar_missions.py',
           '_basis': '각 고객사 단독 미션 — ChoiceKit 연관 오더에 더하지 않는다.',
           'lead_target': SS.get('lead_target'), 'missions': []}

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
            y25, y26, q25, q26, name, cut = ledger_sku(M['cust'])
            top = tops.get(M['key'])
            if not y26 and not y25:
                rec['sku'] = {'mode': 'none',
                              'why': '오더 원장에 이 고객사 행이 없음 — 2026 오더가 아직 '
                                     '원장에 반영되지 않았거나 다른 이름으로 들어가 있음'}
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
                    hit = [k for k in keys26 if k in top]
                    rec['sku'].update({'top_n': len(top), 'top_hit': len(hit),
                                       'top_amt': round(sum(y26[k] for k in hit), 2),
                                       'top_pct': round(len(hit) / len(top) * 100, 1) if top else None})
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
        line = '  %-22s %-8s 목표 $%s → $%s (%s%%)' % (
            m['cust'], m['country'], format(round(m['tgt'] or 0), ','),
            format(round(m['got'] or 0), ','), m['rate'])
        print(line)
        if s.get('mode') == 'full':
            print('      품번: 신규 %s종 · 재전환 %s종 · 확장 기여 %s%%'
                  % (s.get('conv'), s.get('recov'), s.get('cover_pct')))
        elif s.get('mode') == 'ledger':
            print('      품번(원장 ~%s): 26년 %s종 $%s · 그중 2025 미오더 %s종 $%s'
                  % (s.get('cut'), s.get('n26'), format(round(s.get('a26') or 0), ','),
                     s.get('new_n'), format(round(s.get('new_amt') or 0), ',')))
            print('      ※ ' + s.get('caveat', ''))
        elif s.get('mode') == 'top':
            print('      TOP %s 중 %s종 전환 (%s%%) · $%s'
                  % (s.get('top_n'), s.get('top_hit'), s.get('top_pct'),
                     format(round(s.get('top_amt') or 0), ',')))
        else:
            print('      품번: ' + (s.get('why') or '데이터 없음'))
    print('steerstar_missions.json ' + ('갱신됨' if changed else '변경 없음'))


if __name__ == '__main__':
    main()
