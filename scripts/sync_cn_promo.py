#!/usr/bin/env python3
"""중국차 프로모션을 캠페인 한 줄로 만들어 ChoiceKit 합계에 넣음.

  python3 scripts/sync_cn_promo.py --src <중국차 오더분석 xlsx>
  python3 scripts/sync_cn_promo.py                 # cn_promo.json 으로 반영만
  python3 scripts/sync_cn_promo.py ... --check

기산일
  카탈로그가 2026-04 에 전 권역으로 나갔으므로 LATAM·MENA·CIS 모두 4월부터 셈.
  전년은 같은 달 구간(연도만 -1). 목표는 다른 캠페인과 같은 식 —
  전년 동기 ×1.2 (sellinGoal 이 a25 로 계산함).
  권역별로 다른 것은 콘텐츠를 돌린 시점임 — 10월 MENA·LATAM 프로모션 콘텐츠,
  11월 CIS 이메일(론칭 인포그래픽·카탈로그) 예정.

합산은 '② 중국전용' 만
  ① 커버 전체(237품번)는 공용 부품이 섞여 있어 ChoiceKit 대상 SKU 21종·
  orders.csv 26종과 겹침 — 더하면 같은 오더를 두 번 셈. ② 중국전용은
  ChoiceKit 대상 SKU 와 겹치는 것이 0건이라 그대로 더해도 안전함.
  그래서 a25/a26(연관 오더) = 중국전용, all25/all26(전 품목 기준) = 커버 전체
  로 넣음 — 화면이 이 둘을 원래 따로 보여 주고 서로 더하지 않음.

아직 오더가 없는 권역
  started=false 로 두어 합계·목표에 들어가지 않고 '시작 예정' 쪽에 나옴.
"""
import argparse, collections, datetime, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'cn_promo.json')
PROGRAM = '중국차 프로모션'    # 화면 표기 — 다른 캠페인과 달리 한글로 둠(권역 표에서 바로 눈에 띄게)

# 권역 → (카탈로그 배포월, 집계 시작월, 화면에 적을 말)
# 카탈로그는 2026-04 에 전 권역으로 나갔음. 그래서 집계 기산은 세 권역 모두 4월로
# 같게 두고, 권역마다 다른 것은 '콘텐츠를 언제 본격적으로 돌렸는가' 로만 적음.
PLAN = {
    'LATAM': {'pub': '2026-04', 'from': '2026-04',
              'why': '4월 카탈로그 배포 · 10월 프로모션 콘텐츠 본격 배포'},
    'MENA':  {'pub': '2026-04', 'from': '2026-04',
              'why': '4월 카탈로그 배포 · 10월 프로모션 콘텐츠 본격 배포'},
    'CIS':   {'pub': '2026-04', 'from': '2026-04',
              'why': '4월 카탈로그 배포 · 11월 이메일 인포그래픽·카탈로그 예정'},
}
COUNTRY = {'LATAM': [], 'MENA': []}     # 아래에서 자료로 채움


def months(a, b):
    y, m = int(a[:4]), int(a[5:7]); out = []
    while '%d-%02d' % (y, m) <= b:
        out.append('%d-%02d' % (y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def read(src):
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    # key = (year, region, is_cn_only, 'YYYY-MM') → [usd, qty, {sku}, {cust}, {country}]
    agg = collections.defaultdict(lambda: [0.0, 0, set(), set(), set()])
    mx = ''
    for sh in ('오더라인_2025', '오더라인_2026'):
        if sh not in wb.sheetnames: continue
        rs = wb[sh].iter_rows(values_only=True)
        h = [str(x) for x in next(rs)]
        need = ('생성일', '월', 'CTR Code', '② 중국전용', '권역',
                '정가(USD)', '오더수량(순)', '판매처', '국가(명)')
        miss = [k for k in need if k not in h]
        if miss: sys.exit('%s 에 없는 열: %s' % (sh, ' · '.join(miss)))
        I = {k: h.index(k) for k in need}
        for r in rs:
            if not r or r[0] is None: continue
            d = str(r[I['생성일']])[:10]
            if d > mx: mx = d
            reg = str(r[I['권역']] or '').strip()
            if reg not in PLAN: continue
            cn = str(r[I['② 중국전용']] or '').strip().upper() == 'Y'
            v = agg[(reg, cn, d[:7])]
            v[0] += float(r[I['정가(USD)']] or 0)
            v[1] += int(float(r[I['오더수량(순)']] or 0))
            v[2].add(str(r[I['CTR Code']] or '').strip())
            v[3].add(str(r[I['판매처']] or '').strip())
            v[4].add(str(r[I['국가(명)']] or '').strip())
    # 카탈로그 대상 품번 수 (중국전용)
    tgt = 0
    if '품번별_월별' in wb.sheetnames:
        rs = wb['품번별_월별'].iter_rows(values_only=True)
        h = [str(x) for x in next(rs)]
        if '② 중국전용' in h:
            i = h.index('② 중국전용')
            tgt = sum(1 for r in rs if r and str(r[i] or '').strip().upper() == 'Y')
    wb.close()
    return agg, mx, tgt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    if a.src:
        agg, mx, tgt = read(a.src)
        rows = []
        for reg, p in PLAN.items():
            cur = months(p['from'], mx[:7])
            pre = ['%d%s' % (int(m[:4]) - 1, m[4:]) for m in cur]
            d = {'region': reg, 'program': PROGRAM, 'publish': p['pub'],
                 'from': p['from'], 'why': p['why'], 'cut': mx,
                 'months': cur, 'months_prev': pre,
                 'started': bool(cur)}
            for tag, flag in (('cn', True), ('all', False)):
                for yr, ms in (('26', cur), ('25', pre)):
                    u = q = 0.0; sk = set(); cu = set(); co = set()
                    for m in ms:
                        v = agg.get((reg, flag, m))
                        if not v: continue
                        u += v[0]; q += v[1]; sk |= v[2]; cu |= v[3]; co |= v[4]
                    d[f'{tag}{yr}'] = round(u, 2)
                    d[f'{tag}{yr}_q'] = int(q)
                    d[f'{tag}{yr}_sku'] = len(sk)
                    d[f'{tag}{yr}_cust'] = len(cu)
                    if tag == 'cn' and yr == '26':
                        d['countries'] = sorted(x for x in co if x)
            # 월별(화면 차트용) — 중국전용
            def _cell(k):
                v = agg.get(k)
                return (round(v[0], 2), len(v[2])) if v else (0.0, 0)
            d['mser'] = []
            for m in cur:
                cu, cs = _cell((reg, True, m))
                pv, ps = _cell((reg, True, '%d%s' % (int(m[:4]) - 1, m[4:])))
                d['mser'].append({'m': m, 'cur': cu, 'sku': cs, 'prv': pv, 'sku_prv': ps})
            rows.append(d)
        # 권역이 같은 카탈로그를 쓰므로 전환 품번은 합집합으로 셈
        u26, u25 = set(), set()
        for d in rows:
            for m in d['months']:
                v = agg.get((d['region'], True, m))
                if v: u26 |= v[2]
            for m in d['months_prev']:
                v = agg.get((d['region'], True, m))
                if v: u25 |= v[2]
        agg2 = {'union26': len(u26), 'union25': len(u25),
                '_readme': '중국차 프로모션 — 카탈로그 배포 다음 달부터의 오더. '
                           'a25/a26(합산 대상)는 ② 중국전용, all25/all26 은 ① 커버 전체(참고). '
                           '재생성: python3 scripts/sync_cn_promo.py --src <xlsx>',
                '_basis': '① 커버 전체는 공용 부품이 섞여 ChoiceKit 대상 SKU 와 겹치므로 연관 오더에 더하지 않음.',
                'src': os.path.basename(a.src), 'cut': mx,
                'tgt_sku': tgt, 'rows': rows}
        json.dump(agg2, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    else:
        agg2 = json.load(open(OUT, encoding='utf-8'))

    # 세 권역이 같은 카탈로그를 쓰므로 전환 종수는 합집합으로 셈.
    # 대표 권역(MAIN)은 당해 금액이 가장 큰 곳 — 거기에만 대상 품번을 달아 둠.
    _run = [r for r in agg2['rows'] if r['cn26'] > 0]
    MAIN = max(_run, key=lambda r: r['cn26'])['region'] if _run else None

    html = open(HTML, encoding='utf-8', newline='').read()
    m = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
    D = json.loads(m.group(1))
    D['campaigns'] = [c for c in D['campaigns']
                      if c.get('program') not in (PROGRAM, 'Chinese Vehicle Promotion')]
    # 권역 표의 '집계 대상'·'스코프 규칙' 칸이 비지 않게 scope 설명도 같이 넣음
    D.setdefault('scope_meta', {})['CN'] = {
        'label': '② 중국전용 품번 (중국차)',
        'rule': '중국차 카탈로그 %d품번 중 중국 차종 전용만. ① 커버 전체(공용 포함)는 '
                'ChoiceKit 대상 SKU 와 겹쳐 연관 오더에 더하지 않음.' % agg2['tgt_sku'],
        'src': '카탈로그', 'n_list': agg2['tgt_sku'],
        'n_sku': max([r['cn26_sku'] for r in agg2['rows']] or [0]), 'share': None}

    print(f"중국차 프로모션 · 원장 ~{agg2['cut']} · 카탈로그 대상 품번 {agg2['tgt_sku']}종")
    for r in agg2['rows']:
        has = bool(r['months']) and r['cn26'] + r['cn25'] > 0
        started = bool(r['months']) and r['cn26'] > 0
        c = {
            'code': '', 'customer': '', 'region': r['region'], 'program': PROGRAM,
            'scope': 'CN', 'sell': '', 'streams': ['SELL_IN'],
            'note': r['why'], 'titles': ['Catalog'], 'subs': ['CONTENT'],
            'acts': 0, 'acts_run': 0, 'spans': [],
            'start': r['from'] + '-01', 'end': '2026-12-31',
            'obs_end': r['cut'], 'cut': r['cut'], 'started': started,
            'a25': r['cn25'], 'a26': r['cn26'],
            'all25': r['all25'], 'all26': r['all26'],
            'q25': r['cn25_q'], 'q26': r['cn26_q'],
            's25': agg2['union25'] if r['region'] == MAIN else 0,
            's26': agg2['union26'] if r['region'] == MAIN else 0,
            # 카탈로그는 183품번 하나를 세 권역이 같이 씀. 권역마다 달아 두면
            # '대상 SKU' 합계가 3배로 부풀어, 대표 권역 한 곳에만 달고 나머지는 0.
            # 합계에 들어가는 전환 종수도 권역 합이 아니라 합집합을 씀.
            # 칸에 보이는 글은 sku_disp 로 권역별 숫자를 그대로 적음.
            'tgt_sku': agg2['tgt_sku'] if (started and r['region'] == MAIN) else 0,
            'ord_sku': (agg2['union26'] if r['region'] == MAIN else 0) if started else 0,
            # 대상 품번을 대표 권역에만 달아 둔 탓에 다른 권역이 '전품목' 으로 보이지
            # 않게, 표에 적을 글은 따로 넘김
            'tgt_disp': ('대상 %d종' % agg2['tgt_sku']) if started and agg2['tgt_sku'] else None,
            'sku_disp': ('%d / %d종 · %d%% 전환' % (r['cn26_sku'], agg2['tgt_sku'],
                         round(r['cn26_sku'] / agg2['tgt_sku'] * 100))) if started and agg2['tgt_sku'] else None,
            'yoy': round((r['cn26'] - r['cn25']) / r['cn25'] * 100, 1) if r['cn25'] else None,
            'yoyA': round((r['all26'] - r['all25']) / r['all25'] * 100, 1) if r['all25'] else None,
            'cost': 0.0, 'exp': 0.0, 'so_t': 0.0, 'so_r': 0.0,
            'countries': r.get('countries') or [], 'custs': [],
            'n_cust': r['cn26_cust'], 'excl_ck': [], 'cust_scoped': False,
            'wins': [[r['from'] + '-01', r['cut']]] if r['months'] else [],
            # 전 품목 오더(COCT) 는 ChoiceKit 참여 고객사 기준이라 이 캠페인엔 없음 → '–'
            'oct_all': None, 'oct_all_q': None, 'oct_all_n': None,
            'ytd_all': None, 'ytd_all_q': None,
            'mser': [{'m': x['m'], 'cur': x['cur'], 'prv': x['prv'],
                      'yoy': round((x['cur'] - x['prv']) / x['prv'] * 100, 1) if x['prv'] else None,
                      'days': 0, 'mdays': 30} for x in r['mser']],
        }
        st = datetime.date.fromisoformat(c['start'])
        en = datetime.date.fromisoformat(c['end'])
        ob = datetime.date.fromisoformat(min(c['cut'], c['end']))
        c['days'] = (en - st).days + 1
        c['obs_days'] = max((ob - st).days + 1, 0)
        c['progress'] = round(c['obs_days'] / c['days'] * 100, 1)
        D['campaigns'].append(c)
        tagline = '집행' if started else '시작 예정 (오더 집계 전)'
        print(f"  {r['region']:<6}{r['why']:<34}{tagline}")
        print(f"         중국전용  전년 ${r['cn25']:>10,.0f} → 당해 ${r['cn26']:>10,.0f}"
              + (f"  ({c['yoy']:+.1f}%)" if c['yoy'] is not None else '  (전년 0 — 비율 없음)')
              + (f"  목표 ${r['cn25']*1.2:,.0f}" if r['cn25'] else ''))
        print(f"         커버 전체  전년 ${r['all25']:>10,.0f} → 당해 ${r['all26']:>10,.0f}"
              + (f"  ({c['yoyA']:+.1f}%)" if c['yoyA'] is not None else '') + '   — 합산 안 함')

    out = html[:m.start(1)] + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
    blk = '<script>const CNP = ' + json.dumps(
        {k: v for k, v in agg2.items() if not k.startswith('_')},
        ensure_ascii=False, separators=(',', ':')) + ';</script>'
    pat = re.compile(r'<script>const CNP = \{.*?\};</script>', re.S)
    if pat.search(out):
        out = pat.sub(lambda _: blk, out, count=1)
    else:
        anchor = '<script>const CNSUM = '
        if anchor not in out: sys.exit('CNP 자리를 만들 기준(const CNSUM)을 찾지 못했음.')
        out = out.replace(anchor, blk + '\n' + anchor, 1)

    changed = out != html
    if a.check:
        print('변경 있음' if changed else '변경 없음'); return
    if changed: open(HTML, 'w', encoding='utf-8', newline='').write(out)
    print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))


if __name__ == '__main__':
    main()
