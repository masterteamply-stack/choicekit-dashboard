#!/usr/bin/env python3
"""ASIA Trade Promotion 원본(xlsx) → asia_sellout.json · asia_sellout_programs.json
   · asia_sellout_raw.json 을 한 번에 다시 만듦.

  python3 scripts/sync_asia_trade.py --src "CTR_Trade_promotion_*.xlsx"
  python3 scripts/sync_asia_trade.py --src <파일> --check     # 쓰지 않고 대조만

읽는 시트
  1.Performance Summary  프로그램 × 고객사 — 기간·예산·목표·실적·적용 환율
  5.Sell-out by Customer 고객사별 월별 sell-out(현지 통화) — 프로그램 중복을 걷어낸 값
  4.Raw Data             영업사원·매장·딜러 단위 원장 — 아래 결과 탭의 상세

쓰고 나서
  python3 scripts/sync_asia_sellout.py      (const AO)
  python3 scripts/sync_asia_programs.py     (const AP)

손대지 않는 것
  고객 코드(code/codes)와 리워드 지급액(rew)은 원본에 없어 기존 json 에서 물려받음.
"""
import argparse, collections, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SO = os.path.join(ROOT, 'asia_sellout.json')
PG = os.path.join(ROOT, 'asia_sellout_programs.json')
RAW = os.path.join(ROOT, 'asia_sellout_raw.json')

KO = {'VN': '베트남', 'PH': '필리핀', 'TH': '태국', 'ID': '인도네시아', 'MY': '말레이시아',
      'Vietnam': '베트남', 'Philippines': '필리핀', 'Thailand': '태국',
      'Indonesia': '인도네시아', 'Malaysia': '말레이시아'}
# 시트마다 이름이 조금씩 달라 화면에서 쓰는 이름으로 모아 줌
ALIAS = {'Densocentra': 'PT Densocentra', 'PT Densocentra': 'PT Densocentra',
         'GP (CTR Thailand)': 'GP', 'Marboro (Malaysia)': 'Marboro',
         'Mast HN': 'Mast', 'Mast HCM': 'Mast',
         'Nam Bac HN': 'Nam Bac', 'Nam Bac HCM': 'Nam Bac'}
name = lambda s: ALIAS.get(str(s or '').strip(), str(s or '').strip())
f = lambda v: float(v) if isinstance(v, (int, float)) else 0.0


def rows_of(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def header(G, key, limit=6):
    """머리글 행을 찾음 — 시트마다 제목 줄이 한두 개 있어 고정 위치로 보지 않음."""
    for i, r in enumerate(G[:limit]):
        cells = [str(x or '').strip() for x in (r or [])]
        if key in cells:
            return i, cells
    sys.exit('머리글(%s)을 찾지 못했음.' % key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    import openpyxl
    wb = openpyxl.load_workbook(a.src, data_only=True)

    # ── 1) 프로그램 × 고객사
    G = rows_of(wb['1.Performance Summary'])
    hi, h = header(G, 'Program')
    I = {k: h.index(k) for k in h if k}
    col = lambda r, *cands: next((r[I[c]] for c in cands if c in I and I[c] < len(r)), None)
    progs, fx_of, prog_of = [], {}, collections.defaultdict(list)
    for r in G[hi + 1:]:
        # 이 시트에도 아래에 표가 더 붙어 있음 — 합계 줄에서 끊음
        if not r: break
        p = str(r[I['Program']] or '').strip()
        if not p or p.lower().startswith(('subtotal', 'total')): break
        k = name(col(r, 'Customer'))
        if not k: continue
        tgt = f(col(r, 'Sell-out Target for Comparison (USD)', 'Sell-out Target  (USD)'))
        act = f(col(r, 'Sell-out Actual  (USD)', 'Sell-out Actual (USD)'))
        if not tgt or not act:   # 열 이름이 길어 조금씩 다름 — 접두사로 한 번 더 찾음
            for c in I:
                if c.startswith('Sell-out Target') and 'USD' in c and not tgt: tgt = f(r[I[c]])
                if c.startswith('Sell-out Actual') and 'USD' in c and not act: act = f(r[I[c]])
        rate = next((f(r[I[c]]) for c in I if c.startswith('FX Rate')), 0.0)
        if rate: fx_of[k] = rate
        prog_of[k].append(p)
        progs.append({'p': p, 'c': str(col(r, 'Country') or '').strip(), 'k': k,
                      'period': str(col(r, 'Program Period') or '').strip(),
                      'tgt': round(tgt, 2), 'act': round(act, 2),
                      'bud': round(f(col(r, 'Marketing Budget  (USD)', 'Marketing Budget (USD)')))})

    # ── 2) 고객사별 월별 (중복 걷어낸 값)
    # 이 시트에는 표가 여럿 있음(A 현지통화 · B USD · C 고객사 요약).
    # 이미 USD 로 환산된 B 표를 씀 — 환율을 우리가 다시 적용하지 않음.
    G5 = rows_of(wb['5.Sell-out by Customer'])
    hi5 = next((i for i, r in enumerate(G5)
                if r and any(str(x or '').strip() == 'Total (USD)' for x in r)), -1)
    if hi5 < 0: sys.exit("5.Sell-out by Customer 에서 'Total (USD)' 표를 찾지 못했음.")
    h5 = [str(x or '').strip() for x in G5[hi5]]
    J = {c: i for i, c in enumerate(h5) if c}
    MN = sorted(c for c in J if re.fullmatch(r'\d{4}-\d{2}', c))
    jlast = next((i for c, i in J.items() if c.startswith('Latest month with data')), None)
    jfx = next((i for c, i in J.items() if c.startswith('FX rate')), None)
    cur_of = {}                       # 현지 통화는 A 표에 있음
    for r in G5[:hi5]:
        if r and len(r) > 2 and str(r[1] or '').strip() and str(r[2] or '').strip().isalpha():
            cur_of[name(r[1])] = str(r[2]).strip()
    cust = []
    for r in G5[hi5 + 1:]:
        # B 표 아래에 C·D 표가 더 붙어 있음 — 합계 줄이나 빈 줄에서 끊음
        if not r: break
        co = str(r[J['Country']] or '').strip()
        if not co or co.lower() in ('total', 'subtotal') or co.startswith(('A.', 'B.', 'C.', 'D.')):
            break
        if not str(r[J['Customer']] or '').strip(): break
        k = name(r[J['Customer']])
        m = [round(f(r[J[c]])) for c in MN]
        last = str(r[jlast] or '').strip() if jlast is not None else ''
        rate = f(r[jfx]) if jfx is not None else fx_of.get(k, 0)
        cust.append({'k': k, 'country': KO.get(str(r[J['Country']] or '').strip(), str(r[J['Country']] or '')),
                     'cur': cur_of.get(k, ''), 'fx': rate or fx_of.get(k, 0),
                     'programs': sorted(set(prog_of.get(k, []))),
                     'm': m, 'usd': sum(m),
                     'last': '' if last.lower().startswith('no data') else last})

    # ── 2b) 고객사 요약(C 표) — 한 고객사가 여러 프로그램에 걸릴 때의 '묶음 목표'
    # 프로그램 행 목표를 그냥 더하면 안 됨. 원본이 고객사별로 따로 적어 둔 값이 있고
    # (GP 는 SCA+LTL 만 묶어 $32,543, New Product Sell-Out 은 빼 둠) 그게 정본임.
    hic = next((i for i, r in enumerate(G5)
                if r and any(str(x or '').strip().startswith('Sell-out Target') for x in r)), -1)
    csum, ctot = {}, None
    if hic >= 0:
        hc = [re.sub(r'\s+', ' ', str(x or '')).strip() for x in G5[hic]]
        Jc = {c: i for i, c in enumerate(hc) if c}
        gi = lambda *n: next((Jc[c] for c in Jc for x in n if c.startswith(x)), None)
        i_t = next((i for c, i in Jc.items() if c.startswith('Sell-out Target')), None)
        i_a = next((i for c, i in Jc.items() if c.startswith('Sell-out Actual')), None)
        i_st = next((i for c, i in Jc.items() if c.startswith('Sell-in Target')), None)
        i_sa = next((i for c, i in Jc.items() if c.startswith('Sell-in Actual')), None)
        for r in G5[hic + 1:]:
            if not r or not str(r[0] or '').strip(): break
            k = name(r[0])
            row = {'tgt': round(f(r[i_t]), 2), 'act': round(f(r[i_a]), 2),
                   'si_tgt': round(f(r[i_st]), 2) if i_st is not None else None,
                   'si_act': round(f(r[i_sa]), 2) if i_sa is not None else None,
                   'period': str(r[2] or '').strip(),
                   'progs': [x.strip() for x in re.split(r'[\n;]', str(r[1] or '')) if x.strip()]}
            if k.lower() in ('total', 'subtotal'): ctot = row; break
            csum[k] = row
    if not csum:
        sys.exit("5.Sell-out by Customer 의 고객사 요약(C) 표를 찾지 못했음.")

    # ── 3) 원장(Raw Data) — 결과 탭의 상세
    GR = rows_of(wb['4.Raw Data'])
    hir, hr = header(GR, 'Customer', 8)
    K = {c: i for i, c in enumerate(hr) if c}
    need = ('Country', 'Customer', 'Program', 'Period', 'Level', 'Sales (USD)')
    miss = [c for c in need if c not in K]
    if miss: sys.exit('Raw Data 에 없는 열: ' + ' · '.join(miss))
    bym = collections.defaultdict(float)
    byp = collections.defaultdict(lambda: [0.0, 0])
    byl = collections.defaultdict(lambda: [0.0, 0])
    byc = collections.defaultdict(lambda: [0.0, 0, set()])
    ent = collections.defaultdict(float)
    n = 0
    for r in GR[hir + 1:]:
        if not r or not str(r[K['Customer']] or '').strip(): continue
        u = f(r[K['Sales (USD)']]); n += 1
        mo = str(r[K['Period']] or '')[:7]
        p = str(r[K['Program']] or '').strip()
        lv = str(r[K['Level']] or '').strip()
        k = name(r[K['Customer']])
        bym[mo] += u
        v = byp[p]; v[0] += u; v[1] += 1
        v = byl[lv]; v[0] += u; v[1] += 1
        v = byc[k]; v[0] += u; v[1] += 1; v[2].add(lv)
        e = str(r[K['Entity name']] or '').strip() if 'Entity name' in K else ''
        if e: ent[(k, p, lv, e)] += u
    wb.close()

    top = sorted(ent.items(), key=lambda x: -x[1])[:20]
    raw = {'_readme': 'ASIA Sell-out 원장(영업사원·매장·딜러 단위) 요약. '
                      '재생성: python3 scripts/sync_asia_trade.py --src <xlsx>',
           '_basis': '프로그램 단위 원장이라 한 고객사가 두 프로그램에 걸리면 같은 판매가 두 번 잡힘. '
                     '고객사 단위 합계(중복 제거)는 asia_sellout.json 을 봐야 함.',
           'src': re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(a.src)),
           'lines': n, 'usd': round(sum(bym.values()), 2),
           'months': {k: round(v, 2) for k, v in sorted(bym.items())},
           'programs': [{'k': k, 'usd': round(v[0], 2), 'n': v[1]}
                        for k, v in sorted(byp.items(), key=lambda x: -x[1][0])],
           'levels': [{'k': k, 'usd': round(v[0], 2), 'n': v[1]}
                      for k, v in sorted(byl.items(), key=lambda x: -x[1][0])],
           'customers': [{'k': k, 'usd': round(v[0], 2), 'n': v[1], 'levels': sorted(v[2])}
                         for k, v in sorted(byc.items(), key=lambda x: -x[1][0])],
           'top_entities': [{'k': k[0], 'p': k[1], 'level': k[2], 'name': k[3], 'usd': round(v, 2)}
                            for k, v in top]}

    # ── 기존 json 에서 코드·리워드 물려받기
    old_so = json.load(open(SO, encoding='utf-8'))
    old_pg = json.load(open(PG, encoding='utf-8'))
    code_of = {r['k']: (r.get('code'), r.get('codes')) for r in old_so['rows']}
    rew_of = {(r['p'], r['k']): r.get('rew', 0) for r in old_pg['rows']}
    for c in cust:
        g = csum.get(c['k'])
        if g:
            c['tgt'] = g['tgt']; c['si_tgt'] = g['si_tgt']; c['si_act'] = g['si_act']
            c['period'] = g['period']
            if abs(g['act'] - c['usd']) > 2:
                print(f"  ※ {c['k']} 월별 합계 ${c['usd']:,.0f} ↔ 요약표 ${g['act']:,.0f} 가 다름")
        cd, cds = code_of.get(c['k'], ('', None))
        c['code'] = cd or ''
        if cds: c['codes'] = cds
        c['status'] = (' · '.join(c['programs']) or '프로그램 미지정') + \
                      (' · 자료 %s까지' % c['last'] if c['last'] else ' · 자료 미수령')
    for p in progs:
        p['rew'] = rew_of.get((p['p'], p['k']), 0)

    cut = max([c['last'] for c in cust if c['last']] or [''])
    so = dict(old_so)
    # 목표도 고객사 요약표의 합계를 씀 — 프로그램 행을 더하면 한 고객사가 여러
    # 프로그램에 걸릴 때 목표가 겹쳐 올라감(지금은 New Product Sell-Out $12,638 만큼).
    so.update(source_file=raw['src'], asof=cut or old_so.get('asof'), months=MN,
              target=round(ctot['tgt'] if ctot else sum(g['tgt'] for g in csum.values())),
              target_src='5.Sell-out by Customer · 고객사 요약(C) 표의 목표 합계',
              rows=sorted(cust, key=lambda r: -r['usd']))
    pg = dict(old_pg)
    pg.update(source_file=raw['src'], asof=cut or old_pg.get('asof'), cut=cut,
              rows=progs, dedup_total=round(sum(c['usd'] for c in cust)))
    pt = sum(p['act'] for p in progs)
    pg['note_dup'] = ('프로그램 단위 합계 $%s ↔ 고객사 단위(중복 제거) $%s. 차이 $%s 가 두 프로그램에 겹쳐 잡힌 몫임.'
                      % (f'{pt:,.0f}', f"{pg['dedup_total']:,.0f}", f"{pt - pg['dedup_total']:,.0f}"))

    print(f"자료 {raw['src']} · 자료가 들어온 마지막 달 {cut}")
    print(f"  고객사 단위(중복 제거)  ${old_so and sum(r['usd'] for r in old_so['rows']):>10,.0f}"
          f" → ${sum(c['usd'] for c in cust):>10,.0f}   목표 ${so['target']:,.0f}"
          f" · 달성 {sum(c['usd'] for c in cust)/so['target']*100:.1f}%")
    print(f"  프로그램 단위 합계      ${sum(r.get('act') or 0 for r in old_pg['rows']):>10,.0f} → ${pt:>10,.0f}  ({len(progs)}건)")
    print(f"  원장 {n:,}줄 · ${raw['usd']:,.0f} · 월 {min(raw['months'])}~{max(raw['months'])}")
    print('   ' + ' · '.join(f"{x['k']} ${x['usd']:,.0f}" for x in raw['levels']))
    for c in sorted(cust, key=lambda r: -r['usd']):
        o = next((r['usd'] for r in old_so['rows'] if r['k'] == c['k']), 0)
        if o != c['usd']:
            print(f"   {c['k']:<16}${o:>9,.0f} → ${c['usd']:>9,.0f}   {c['last'] or '자료 없음'}")
    if a.check:
        print('(--check: 쓰지 않음)'); return
    json.dump(so, open(SO, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(pg, open(PG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(raw, open(RAW, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # 원장 요약은 전용 싱크가 없어 여기서 바로 넣음
    H = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
    html = open(H, encoding='utf-8', newline='').read()
    blk = '<script>const AORAW = ' + json.dumps(
        {k: v for k, v in raw.items() if not k.startswith('_')},
        ensure_ascii=False, separators=(',', ':')) + ';</script>'
    pat = re.compile(r'<script>const AORAW = \{.*?\};</script>', re.S)
    if pat.search(html):
        out = pat.sub(lambda _: blk, html, count=1)
    else:
        anchor = '<script>const AP = '
        if anchor not in html: sys.exit('AORAW 자리를 만들 기준(const AP)을 찾지 못했음.')
        out = html.replace(anchor, blk + '\n' + anchor, 1)
    if out != html: open(H, 'w', encoding='utf-8', newline='').write(out)
    print('asia_sellout.json · asia_sellout_programs.json · asia_sellout_raw.json 갱신됨 (const AORAW 포함)')
    print('다음: python3 scripts/sync_asia_sellout.py && python3 scripts/sync_asia_programs.py')


if __name__ == '__main__':
    main()
