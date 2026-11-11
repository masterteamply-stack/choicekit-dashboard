#!/usr/bin/env python3
"""중국차 프로모션의 품번 단위 집행 전/후 — 오더라인_2025 가 생겨서 가능해짐.

  python3 scripts/sync_cn_sku.py --src <중국차 오더분석 xlsx>

내보내는 것
  cn_sku_impact.json  — scripts/sync_sku_impact.py 가 읽어 SKU 분석 블록의
                        중국차 줄을 품번 단위까지 채운다.

왜 따로 있나
  중국차는 오더 원장이 orders.csv 밖이다. r8 까지는 오더라인_2026 만 있어
  전년 품번 비교가 안 돼 권역 단위까지만 표기했음. r9 에 오더라인_2025
  (3,488행)가 붙어 품번별 전년이 생겼다.

기준 — cn_promo.json 과 똑같이
  대상    ② 중국전용 = 'Y' (중국 차종 전용 품번만. ① 커버 전체는 공용 부품이
          섞여 ChoiceKit 대상 SKU 와 겹치므로 더하지 않는다.)
  권역    LATAM · MENA · CIS. RUS 제외하고 우크라이나는 EU 로 빼낸다
          (CTY_REGION — sync_cn_promo.py 와 공유하는 규칙).
  기간    2026-04-01 ~ 오더라인_2026 마감일. 전년은 같은 날짜 구간.
  금액    정가(USD).
  ※ 이 기준으로 당해 $19,387.61 / 63종, 전년 $10,238.78 / 43종이 나와야 한다
    (cn_promo.json 과 일치). 어긋나면 멈추고 알려 준다.

품번 분류 — sync_sku_impact.py 와 같은 규칙
  신규 0→>0 · 증가 >0→+2% 초과 · 유지 ±2% · 감소 -2% 미만 · 이탈 >0→0
"""
import argparse, collections, datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'cn_sku_impact.json')
CTY_REGION = {'RU': 'RUS', 'UA': 'EU'}     # sync_cn_promo.py 와 같은 규칙
KEEP = ('LATAM', 'MENA', 'CIS')
FROM_MD = '04-01'                           # 4월 카탈로그 배포
COLS = ('생성일', '매칭 코드', '② 중국전용', 'Cty', '권역',
        '정가(USD)', '판매처(명)', 'Parts', '중국 브랜드(정규화)')


def shift1y(d):
    return '%d%s' % (int(d[:4]) - 1, d[4:])


def read(wb, name):
    if name not in wb.sheetnames: sys.exit('%s 시트가 없음.' % name)
    it = wb[name].iter_rows(values_only=True)
    h = [str(x) for x in next(it)]
    miss = [c for c in COLS if c not in h]
    if miss: sys.exit('%s 에 없는 열: %s' % (name, ' · '.join(miss)))
    I = {c: h.index(c) for c in COLS}
    out = []
    for r in it:
        if not r or r[0] is None: continue
        d = r[I['생성일']]
        d = d.strftime('%Y-%m-%d') if isinstance(d, datetime.datetime) else str(d)[:10]
        rg = str(r[I['권역']] or '').strip()
        rg = CTY_REGION.get(str(r[I['Cty']] or '').strip().upper(), rg)
        out.append({'d': d, 'code': str(r[I['매칭 코드']] or '').strip(),
                    'cn': str(r[I['② 중국전용']] or '').strip().upper(), 'rg': rg,
                    'usd': float(r[I['정가(USD)']] or 0),
                    'cust': str(r[I['판매처(명)']] or '').strip(),
                    'part': str(r[I['Parts']] or '').strip(),
                    'brand': str(r[I['중국 브랜드(정규화)']] or '').strip()})
    return out


def agg(rows, lo, hi):
    amt = collections.defaultdict(float)
    cust = collections.defaultdict(set)
    rgn = collections.defaultdict(set)
    meta = {}
    for r in rows:
        if r['cn'] != 'Y' or r['rg'] not in KEEP: continue
        if not (lo <= r['d'] <= hi): continue
        amt[r['code']] += r['usd']
        cust[r['code']].add(r['cust'])
        rgn[r['code']].add(r['rg'])
        meta.setdefault(r['code'], (r['part'], r['brand']))
    return amt, cust, rgn, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(a.src, read_only=True, data_only=True)
    R26, R25 = read(wb, '오더라인_2026'), read(wb, '오더라인_2025')
    wb.close()

    cut = max(r['d'] for r in R26)
    f26 = cut[:4] + '-' + FROM_MD
    A, AC, ARG, M1 = agg(R26, f26, cut)
    B, BC, BRG, M0 = agg(R25, shift1y(f26), shift1y(cut))
    meta = {**M0, **M1}

    # cn_promo.json 과 맞는지 — 기준이 어긋나면 여기서 멈춘다
    ta, tb = round(sum(A.values()), 2), round(sum(B.values()), 2)
    cp = os.path.join(ROOT, 'cn_promo.json')
    if os.path.exists(cp):
        P = json.load(open(cp, encoding='utf-8'))
        rs = [r for r in P.get('rows') or [] if r.get('started')]
        e26 = round(sum(r.get('cn26') or 0 for r in rs), 2)
        e25 = round(sum(r.get('cn25') or 0 for r in rs), 2)
        if abs(ta - e26) > 1 or abs(tb - e25) > 1:
            print('cn_promo.json 과 어긋남 — 기준이 다른 파일인 듯함:')
            print(f'  당해 {ta:,.2f} vs {e26:,.2f} · 전년 {tb:,.2f} vs {e25:,.2f}')
            sys.exit(1)

    cls = collections.Counter()
    items = []
    for k in sorted(set(A) | set(B)):
        b, af = round(B.get(k, 0), 2), round(A.get(k, 0), 2)
        kind = ('신규' if b <= 0 else '이탈' if af <= 0 else
                '증가' if af > b * 1.02 else '감소' if af < b * 0.98 else '유지')
        cls[kind] += 1
        items.append({'sku': k, 'part': meta.get(k, ('', ''))[0], 'brand': meta.get(k, ('', ''))[1],
                      'region': sorted(ARG.get(k) or BRG.get(k) or []),
                      'before': b, 'after': af, 'inc': round(af - b, 2),
                      'cust': len(AC.get(k) or BC.get(k) or set()), 'kind': kind})
    byk = collections.defaultdict(list)
    for x in items: byk[x['kind']].append(x)
    for v in byk.values(): v.sort(key=lambda x: -abs(x['inc']))

    # 업로드 임시 파일명이 그대로 화면에 나가지 않게 정리
    _nm = os.path.basename(a.src)
    _m = __import__('re').search(r'(20\d\d)[^0-9]*?r(\d+)', _nm)
    src = ('중국차 오더분석 %s r%s' % (_m.group(1), _m.group(2))) if _m else _nm
    D = {'src': src,
         'basis': '② 중국전용 품번 · 정가(USD) · %s ~ %s · 전년은 같은 날짜 구간' % (f26, cut),
         'rule': 'RUS 제외 · 우크라이나는 EU · LATAM·MENA·CIS 만',
         'cut': cut, 'start': f26, 'regions': list(KEEP),
         'before': tb, 'after': ta, 'inc': round(ta - tb, 2),
         'yoy': round((ta / tb - 1) * 100, 1) if tb > 0 else None,
         'conv': len(A), 'conv_prev': len(B),
         'cust': len({c for k in A for c in AC[k]}),
         'cls': dict(cls),
         'new_amt': round(sum(x['after'] for x in byk['신규'])),
         'up_amt': round(sum(x['inc'] for x in byk['증가'])),
         'dn_amt': round(sum(x['inc'] for x in byk['감소'] + byk['이탈'])),
         'top': {k: byk[k][:10] for k in byk},
         'items': items}

    # 브랜드 · 권역 · 부품군 롤업 — 어디서 열렸는지 보려면 이 축이 필요하다
    def roll(keyf, multi=False):
        g = collections.defaultdict(lambda: {'n': 0, 'new': 0, 'before': 0.0, 'after': 0.0})
        for x in items:
            ks = keyf(x) if multi else [keyf(x)]
            for k in ks or ['(미지정)']:
                v = g[k]; v['n'] += 1
                if x['kind'] == '신규': v['new'] += 1
                v['before'] += x['before']; v['after'] += x['after']
        out = [{'k': k, **{m: (round(v[m], 2) if isinstance(v[m], float) else v[m]) for m in v},
                'yoy': (round((v['after'] / v['before'] - 1) * 100, 1) if v['before'] > 0 else None)}
               for k, v in g.items()]
        return sorted(out, key=lambda x: -x['after'])
    D['by_brand'] = roll(lambda x: x['brand'] or '(미지정)')
    D['by_region'] = roll(lambda x: x['region'], multi=True)
    D['by_part'] = roll(lambda x: x['part'] or '(미지정)')
    json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f"중국차 품번 단위 · 원장 ~{cut} · {f26} 부터")
    print(f"  전환 {D['conv']}종 (전년 {D['conv_prev']}종) · ${tb:,.0f} → ${ta:,.0f} ({D['yoy']}%)")
    print('  ' + ' · '.join('%s %d종' % (k, v) for k, v in cls.items()))
    print(f"  신규 ${D['new_amt']:,.0f} · 증가 ${D['up_amt']:,.0f} · 감소·이탈 ${D['dn_amt']:,.0f}")
    print('cn_sku_impact.json 갱신됨 — 이어서 python3 scripts/sync_sku_impact.py')


if __name__ == '__main__':
    main()
