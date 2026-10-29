#!/usr/bin/env python3
"""CIS Choice Kit Meta 광고 성과 → cis_ads.json.

  python3 scripts/sync_cis_ads.py --src <PTKOREA_CTR_Choice_Kit_Promotion_*.xlsx>

읽는 곳
  '성과 요약'  [OVERVIEW] — 회차(콘텐츠)별 집행액·노출·클릭·참여
               [META]     — 회차 × 매체(FB/IG)
  '국가별 데이터'           — 회차 × 매체 × 국가
  '세팅 정보'               — 목적·타깃·랜딩

집계 규칙
  합계는 OVERVIEW 를 쓴다. 국가별 시트 합계가 1~3 건 작은 것은 Meta 의
  국가 미식별(Unknown) 유저가 국가 집계에서 빠지기 때문이라 맞추지 않는다.
  CTR·CPC·CPM 은 반올림된 열을 쓰지 않고 원수치에서 다시 계산한다.
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'cis_ads.json')


def sheet(wb, name):
    return [r for r in wb[name].iter_rows(values_only=True)]


def head(rows, key):
    """key 가 들어 있는 머리글 행을 찾아 {열이름: 번호} 로 돌려준다."""
    for i, r in enumerate(rows):
        cells = [str(x).strip() for x in r if x is not None]
        if key in cells:
            h = [str(x).strip() if x is not None else '' for x in r]
            return i, {v: j for j, v in enumerate(h) if v}
    print(f"'{key}' 머리글을 찾지 못했습니다."); sys.exit(1)


def rate(a, b, nd=2):
    return round(a / b * 100, nd) if b else None


def won(a, b, nd=0):
    v = a / b if b else 0
    return round(v, nd) if nd else int(round(v))


def main():
    if '--src' not in sys.argv:
        print(__doc__); sys.exit(1)
    src = sys.argv[sys.argv.index('--src') + 1]
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)

    # ── 회차별(OVERVIEW)
    S = sheet(wb, '성과 요약')
    hi, ix = head(S, '콘텐츠')
    rounds, seen = [], set()
    for r in S[hi + 1:]:
        lab = r[ix['콘텐츠']]
        if not lab or not isinstance(r[ix['노출']], (int, float)): continue
        lab = str(lab).strip()
        if 'TOTAL' in lab.upper() or lab in seen: continue
        m = re.search(r'\(([\d.]+)\s*~\s*([\d.]+)\)', lab)
        if not m: continue                      # 기간이 붙은 OVERVIEW 행만
        seen.add(lab)
        name = re.sub(r'^\d+\'\s*', '', lab[:m.start()]).replace('Choice Kit Promotion ', '').strip()
        cost, imp, clk = r[ix['광고비(GROSS)']], r[ix['노출']], r[ix['클릭']]
        rounds.append(dict(k=name, when=f"{m.group(1)}~{m.group(2)}",
                           grp='Asian' if 'Asian' in name else 'European',
                           cost=int(cost), imp=int(imp), clk=int(clk),
                           eng=int(r[ix['참여']] or 0),
                           ctr=rate(clk, imp), cpc=won(cost, clk)))
    if len(rounds) < 2:
        print('회차 행을 찾지 못했습니다.'); sys.exit(1)
    rounds.sort(key=lambda x: [int(v) for v in re.split(r'[.~]', x['when'])[:2]])

    T = {k: sum(x[k] for x in rounds) for k in ('cost', 'imp', 'clk', 'eng')}
    tot = dict(T, ctr=rate(T['clk'], T['imp']), cpc=won(T['cost'], T['clk']),
               cpm=won(T['cost'] * 1000, T['imp']))

    # ── 국가별 · 매체별(국가별 데이터 시트)
    C = sheet(wb, '국가별 데이터')
    ci, cx = head(C, '국가코드')
    by_c = collections.defaultdict(lambda: dict(cost=0, imp=0, clk=0, k=''))
    by_m = collections.defaultdict(lambda: dict(cost=0, imp=0, clk=0))
    for r in C[ci + 1:]:
        if not r or not r[cx['국가코드']]: continue
        cc = str(r[cx['국가코드']]).strip()
        cost, imp, clk = r[cx['광고비(GROSS)']], r[cx['노출']], r[cx['클릭']]
        a = by_c[cc]; a['k'] = str(r[cx['국가']]).strip()
        b = by_m[str(r[cx['매체']]).strip()]
        for d in (a, b):
            d['cost'] += cost; d['imp'] += imp; d['clk'] += clk
    geo_clk = sum(v['clk'] for v in by_c.values())

    def pack(d, cc=None):
        o = dict(cost=int(d['cost']), imp=int(d['imp']), clk=int(d['clk']),
                 share=rate(d['clk'], geo_clk, 1), ctr=rate(d['clk'], d['imp']),
                 cpc=won(d['cost'], d['clk']), cpm=won(d['cost'] * 1000, d['imp']))
        return dict(cc=cc, k=d['k'], **o) if cc else o

    countries = sorted((pack(v, cc) for cc, v in by_c.items()), key=lambda x: -x['clk'])
    plat = sorted(({'k': ('Instagram' if k == 'IG' else 'Facebook'), **pack(v)}
                   for k, v in by_m.items()), key=lambda x: -x['clk'])

    # ── 세팅
    G = sheet(wb, '세팅 정보')
    gi, gx = head(G, '타깃 국가')
    g = next((r for r in G[gi + 1:] if r and r[gx['타깃 국가']]), None)
    cell = lambda key: (str(g[gx[key]]).strip() if g and gx.get(key) is not None and g[gx[key]] else '')

    best_clk = max(rounds, key=lambda x: x['clk'])
    best_ctr = max(rounds, key=lambda x: x['ctr'])
    d0, d1 = rounds[0]['when'].split('~')[0], rounds[-1]['when'].split('~')[1]

    out = dict(
        _readme='CIS Choice Kit Meta 광고 성과. 원천 리포트에서 매번 다시 뽑는다. '
                '재생성: python3 scripts/sync_cis_ads.py --src <xlsx>',
        src=os.path.basename(src), period=f'{d0}~{d1}', n_round=len(rounds),
        goal=cell('캠페인 목적') or 'Traffic', media='META · Facebook + Instagram',
        countries_txt=cell('타깃 국가'), target=f"{cell('연령')} · {cell('관심사')}",
        landing=cell('랜딩 URL'), tot=tot, rounds=rounds,
        geo=countries, plat=plat,
        best_clk=dict(k=best_clk['k'], v=best_clk['clk']),
        best_ctr=dict(k=best_ctr['k'], v=best_ctr['ctr']),
        ctr_lo=min(x['ctr'] for x in rounds), ctr_hi=max(x['ctr'] for x in rounds),
        note_scope='Meta 클릭과 웹사이트 조회는 측정 주체가 달라 1:1로 잇지 않는다. '
                   '광고는 유입을 만든 쪽, 조회·다운로드는 받은 쪽 수치다.',
        note_geo='국가별 합계는 Meta 의 국가 미식별(Unknown) 유저가 빠져 전체보다 '
                 f"{T['clk'] - geo_clk}건 적다. 맞추지 않고 그대로 둔다.")
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f"{out['src']} · {out['period']} · {len(rounds)}회차")
    print(f"  집행 ₩{tot['cost']:,} · 노출 {tot['imp']:,} · 클릭 {tot['clk']:,} "
          f"· CTR {tot['ctr']}% · CPC ₩{tot['cpc']} · CPM ₩{tot['cpm']:,}")
    print(f"  회차 CTR {out['ctr_lo']}~{out['ctr_hi']}% · 최다 {best_clk['k']} {best_clk['clk']:,}클릭 "
          f"· 최고반응 {best_ctr['k']} {best_ctr['ctr']}%")
    for c in countries:
        print(f"  {c['cc']} {c['k']:<9} 클릭 {c['clk']:>7,} ({c['share']:>4}%) "
              f"CTR {c['ctr']:>5}% CPC ₩{c['cpc']:>3} CPM ₩{c['cpm']:>6,}")
    for p in plat:
        print(f"  {p['k']:<10} 클릭 {p['clk']:>7,} ({p['share']}%) CTR {p['ctr']}% CPC ₩{p['cpc']}")
    print('cis_ads.json 갱신')


if __name__ == '__main__':
    main()
