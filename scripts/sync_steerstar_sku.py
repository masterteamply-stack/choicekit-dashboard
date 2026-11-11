#!/usr/bin/env python3
"""SteerStar 추가 오더미션의 SKU 기반 전환 효과 — Kailos(호주) 일본·한국 차종.

  python3 scripts/sync_steerstar_sku.py <Kailos 원장 xlsx> <일본한국 SKU xlsx>

내보내는 것
  steerstar_sku.json                       — 단일 소스
  promo_dashboard_v10_6.html 의 const KJK  — 효과 분석이 읽음
  (index.html 은 steerstar_sku.json 을 받아 같은 값을 그린다)

차종 국적은 추측하지 않는다
  1순위  공식 파일의 Maker Country(SAP) — 차종 국적. (Maker Country 는 생산국이라
         다르다: CL0060 은 생산국 스웨덴인데 차종은 일본.)
  2순위  그 공식값으로 학습한 Old CTR Code 메이커 코드 맵 (순도 90% 이상만).
         2024·2025 에만 오더된 품번은 공식 파일에 없어서 이걸 쓴다.
  #N/A   SAP 매핑이 빠진 행. 메이커 코드가 전부 일본·한국(KH·KK·KD·HO)이라
         일본·한국으로 세고, 따로 금액을 적어 둔다.
"""
import collections, datetime, json, os, re, sys

KA, OF = sys.argv[1], sys.argv[2]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = ROOT
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
SS_TGT, SS_GOT, SS_B25 = 74282.0, 60110.9, 37141.0      # SteerStar 시트 공식값
JPKR = ('일본', '한국')


def d2s(v):
    return v.strftime('%Y-%m-%d') if isinstance(v, datetime.datetime) else str(v or '')[:10]


def mkcode(old):
    m = re.match(r'^[A-Z]{2}([A-Z]{0,3})-?\d', old or '')
    return m.group(1) if m else ''


def main():
    import openpyxl

    # ── 공식 파일: CTR Code → 차종 국적 ──
    wb = openpyxl.load_workbook(OF, read_only=True, data_only=True)
    it = wb['Kailos'].iter_rows(values_only=True)
    h = [str(x) if x is not None else '' for x in next(it)]
    I = {k: h.index(k) for k in ('CTR Code', 'Maker Country(SAP)', 'Maker Country',
                                 'Old CTR Code', '생성일', '정가(USD)')}
    off, offrows = {}, []
    for r in it:
        if not r or r[0] is None: continue
        c = str(r[I['CTR Code']]).strip()
        sap = str(r[I['Maker Country(SAP)']] or '').strip()
        old = str(r[I['Old CTR Code']] or '').strip()
        offrows.append({'code': c, 'sap': sap, 'old': old, 'd': d2s(r[I['생성일']]),
                        'usd': float(r[I['정가(USD)']] or 0)})
        if sap and sap != '#N/A': off[c] = sap
    tgtlist = {str(r[0]).strip() for r in wb['품번리스트(SAP기준)'].iter_rows(values_only=True)
               if r and r[0]}
    wb.close()

    # 메이커 코드 맵 — 공식값으로 학습 (순도 90%+)
    learn = collections.defaultdict(collections.Counter)
    for x in offrows:
        if x['sap'] and x['sap'] != '#N/A':
            learn[mkcode(x['old'])][x['sap']] += 1
    code_map = {}
    for k, v in learn.items():
        if not k: continue
        top, n = v.most_common(1)[0]
        if n / sum(v.values()) >= 0.9: code_map[k] = top
    # #N/A 행의 메이커 코드는 전부 일본·한국 계열 — 맵에 없으면 보강
    NA_MK = {'KH': '한국', 'KK': '한국', 'KD': '한국', 'KS': '한국', 'HO': '일본'}
    for k, v in NA_MK.items(): code_map.setdefault(k, v)

    # ── Kailos 원장 2024~2026 ──
    wb = openpyxl.load_workbook(KA, read_only=True, data_only=True)
    it = wb['Sheet1'].iter_rows(values_only=True)
    h = [str(x) if x is not None else '' for x in next(it)]
    I = {k: h.index(k) for k in ('CTR Code', 'Old CTR Code', '생성일', '오더 수량',
                                 '정가(USD)', '자재(명)')}
    R = []
    for r in it:
        if not r or r[0] is None: continue
        R.append({'code': str(r[I['CTR Code']] or '').strip(),
                  'old': str(r[I['Old CTR Code']] or '').strip(),
                  'd': d2s(r[I['생성일']]), 'qty': float(r[I['오더 수량']] or 0),
                  'usd': float(r[I['정가(USD)']] or 0),
                  'name': str(r[I['자재(명)']] or '').strip()})
    wb.close()

    per = collections.defaultdict(lambda: collections.defaultdict(float))
    perq = collections.defaultdict(lambda: collections.defaultdict(float))
    pern = collections.defaultdict(lambda: collections.defaultdict(int))
    first, nm, old = {}, {}, {}
    for x in R:
        y = x['d'][:4]
        per[x['code']][y] += x['usd']; perq[x['code']][y] += x['qty']; pern[x['code']][y] += 1
        if x['code'] not in first or x['d'] < first[x['code']]: first[x['code']] = x['d']
        nm.setdefault(x['code'], x['name']); old.setdefault(x['code'], x['old'])
    codes = sorted(per)
    cut = max(x['d'] for x in R if x['d'][:4] == '2026')
    md = cut[5:]

    def nat(c):
        if c in off: return off[c], '공식 SAP'
        k = mkcode(old.get(c, ''))
        if k in code_map: return code_map[k], '메이커 코드(학습)'
        return '미분류', '–'

    cls = {c: nat(c) for c in codes}
    na_amt26 = sum(x['usd'] for x in offrows if x['sap'] == '#N/A')
    na_23 = sum(x['usd'] for x in offrows if x['sap'] == '#N/A' and x['d'][5:7] in ('02', '03'))

    def amt(c, y, upto=None):
        return sum(x['usd'] for x in R if x['code'] == c and x['d'][:4] == y
                   and (upto is None or x['d'][5:] <= upto))

    def grp(sel, y, upto=None):
        return sum(amt(c, y, upto) for c in codes if cls[c][0] in sel)

    W = 78
    print('=' * W)
    print('Kailos International Pty Ltd · 호주 · SteerStar 추가 오더미션')
    print('「일본 & 한국 차종의 25년 대비 26년 오더 최대 100% 성장」')
    print('원장 %s ~ %s · %d행 · 품번 %d종' % (min(x['d'] for x in R), cut, len(R), len(codes)))
    print('=' * W)
    print('차종 분류 근거: ' + ' · '.join(
        '%s %d종' % (k, v) for k, v in collections.Counter(cls[c][1] for c in codes).most_common()))
    print('공식 품번리스트(일본·한국) %d종 · 공식 파일이 국적을 준 품번 %d종' % (len(tgtlist), len(off)))

    print('\n【①】일본·한국 차종 미션 수치')
    rows3 = []
    for lab, sel in (('일본', ('일본',)), ('한국', ('한국',)), ('일본+한국', JPKR),
                     ('그 외 차종', ('독일', '미국', '프랑스', '영국', '체코', '스웨덴', '스페인')),
                     ('미분류 (26년 무오더)', ('미분류',))):
        a25, a26 = grp(sel, '2025'), grp(sel, '2026')
        a25p = grp(sel, '2025', md)
        g = (a26 / a25p - 1) * 100 if a25p > 0 else None
        rows3.append((lab, a25, a25p, a26, g))
        print('  %-11s 25년 $%9s · 25년 1~%s $%9s · 26년 $%9s · 동기간 %s'
              % (lab, format(round(a25), ','), md[:2], format(round(a25p), ','),
                 format(round(a26), ','), ('%+.1f%%' % g) if g is not None else '–'))
    jk25, jk26 = grp(JPKR, '2025'), grp(JPKR, '2026')
    print('\n  SteerStar 시트 공식: 25년 기준 $%s → 26년 $%s · 목표 $%s · 달성률 %.1f%%'
          % (format(round(SS_B25), ','), format(round(SS_GOT), ','), format(round(SS_TGT), ','),
             SS_GOT / SS_TGT * 100))
    print('  이 분석:             25년 기준 $%s → 26년 $%s · 목표 $%s · 달성률 %.1f%%'
          % (format(round(jk25), ','), format(round(jk26), ','), format(round(SS_TGT), ','),
             jk26 / SS_TGT * 100))
    print('  차이 +$%s — SAP 매핑이 빠진 #N/A 17행 중 2·3월 $%s 만 공식 시트가 셌고'
          % (format(round(jk26 - SS_GOT), ','), format(round(na_23), ',')))
    print('                 9·10월 $%s 는 빠졌음. 메이커 코드가 전부 KH·KK·KD·HO 라'
          % format(round(na_amt26 - na_23), ','))
    print('                 일본·한국 차종이 맞음 → 달성률 %.1f%% 가 아니라 %.1f%%.'
          % (SS_GOT / SS_TGT * 100, jk26 / SS_TGT * 100))

    print('\n【②】신규 전환 SKU — 2026 에 처음 오더된 품번')
    new26 = [c for c in codes if first[c][:4] == '2026']
    print('  전체 %d종 · $%s' % (len(new26), format(round(sum(per[c]['2026'] for c in new26)), ',')))
    bn = collections.Counter(cls[c][0] for c in new26)
    ba = collections.defaultdict(float)
    for c in new26: ba[cls[c][0]] += per[c]['2026']
    for k, v in bn.most_common():
        print('     %-8s %3d종 · $%s' % (k, v, format(round(ba[k]), ',')))
    jknew = [c for c in new26 if cls[c][0] in JPKR]
    print('  → 일본·한국 신규 %d종 · $%s (미션 기여 %.1f%%)'
          % (len(jknew), format(round(sum(per[c]['2026'] for c in jknew)), ','),
             sum(per[c]['2026'] for c in jknew) / jk26 * 100))
    print('  상위:')
    for c in sorted(jknew, key=lambda x: -per[x]['2026'])[:10]:
        print('     %-9s %-4s %-24s $%8s · %s개 · %d건'
              % (c, cls[c][0], nm.get(c, '')[:24], format(round(per[c]['2026']), ','),
                 format(int(perq[c]['2026']), ','), pern[c]['2026']))

    print('\n【③】재전환 SKU — 2025 에 오더 없다가 2026 에 다시 오더')
    re26 = [c for c in codes if per[c]['2026'] > 0 and per[c]['2025'] == 0 and first[c][:4] != '2026']
    print('  전체 %d종 · $%s' % (len(re26), format(round(sum(per[c]['2026'] for c in re26)), ',')))
    bn2 = collections.Counter(cls[c][0] for c in re26)
    ba2 = collections.defaultdict(float)
    for c in re26: ba2[cls[c][0]] += per[c]['2026']
    for k, v in bn2.most_common():
        print('     %-8s %3d종 · $%s' % (k, v, format(round(ba2[k]), ',')))
    jkre = [c for c in re26 if cls[c][0] in JPKR]
    print('  → 일본·한국 재전환 %d종 · $%s (미션 기여 %.1f%%)'
          % (len(jkre), format(round(sum(per[c]['2026'] for c in jkre)), ','),
             sum(per[c]['2026'] for c in jkre) / jk26 * 100))
    print('  상위:')
    for c in sorted(jkre, key=lambda x: -per[x]['2026'])[:10]:
        print('     %-9s %-4s %-24s 2024 $%6s → 2025 $0 → 2026 $%8s  ×%.1f배'
              % (c, cls[c][0], nm.get(c, '')[:24], format(round(per[c]['2024']), ','),
                 format(round(per[c]['2026']), ','),
                 per[c]['2026'] / per[c]['2024'] if per[c]['2024'] else 0))

    print('\n【④】미션 증가액 $%s 의 출처' % format(round(jk26 - jk25), ','))
    cont = [('신규 전환 (26년 첫 오더)', sum(per[c]['2026'] for c in jknew)),
            ('재전환 (25년 끊김 → 26년 복귀)', sum(per[c]['2026'] for c in jkre))]
    _jk = [c for c in codes if cls[c][0] in JPKR]
    keep = [c for c in _jk if per[c]['2025'] > 0 and per[c]['2026'] > 0]
    lost = [c for c in _jk if per[c]['2025'] > 0 and per[c]['2026'] == 0]
    cont.append(('연속 품번(25·26 모두)의 증감', sum(per[c]['2026'] - per[c]['2025'] for c in keep)))
    cont.append(('이탈 (25년 있다 26년 0)', -sum(per[c]['2025'] for c in lost)))
    for lab, v in cont:
        print('  %-26s %+10s' % (lab, '$' + format(round(v), ',')))
    print('  %-26s %+10s  (= 26년 $%s − 25년 $%s)'
          % ('합', '$' + format(round(sum(v for _, v in cont)), ','),
             format(round(jk26), ','), format(round(jk25), ',')))

    # ── xlsx ──
    os.makedirs(OUT, exist_ok=True)
    import openpyxl as op
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wbo = op.Workbook(); s0 = wbo.active; s0.title = '요약'
    HD = Font(bold=True, color='FFFFFF'); FL = PatternFill('solid', fgColor='1F4E79')
    MONEY = ('2024', '2025', '2025 (1~%s)' % md[:2], '2026', '증감 (26−25 동기간)')

    def mkrow(c):
        n, srcf = cls[c]
        y24, y25, y26 = per[c]['2024'], per[c]['2025'], per[c]['2026']
        f = first[c]
        kind = ('신규 (26년 첫 오더)' if f[:4] == '2026'
                else '재전환 (25년 끊김 → 26년 복귀)' if (y26 > 0 and y25 == 0)
                else '연속 (25·26 모두)' if (y26 > 0 and y25 > 0)
                else '이탈 (26년 오더 없음)')
        return {'CTR Code': c, 'Old CTR Code': old.get(c, ''), '품명': nm.get(c, ''),
                '차종 국적': n, '분류 근거': srcf,
                '공식 일본·한국 리스트': 'Y' if c in tgtlist else '',
                '구분': kind, '첫 오더일': f,
                '2024': round(y24, 2), '2025': round(y25, 2),
                '2025 (1~%s)' % md[:2]: round(amt(c, '2025', md), 2),
                '2026': round(y26, 2),
                '증감 (26−25 동기간)': round(y26 - amt(c, '2025', md), 2),
                '2026 수량': int(perq[c]['2026']), '2026 오더건': pern[c]['2026']}

    allrows = [mkrow(c) for c in codes]
    COLS = list(allrows[0].keys())

    def sheet(name, data):
        w = wbo.create_sheet(name); w.append(COLS)
        for i in range(1, len(COLS) + 1):
            w.cell(1, i).font = HD; w.cell(1, i).fill = FL
            w.cell(1, i).alignment = Alignment(horizontal='center')
        for d in data: w.append([d.get(k) for k in COLS])
        for i, k in enumerate(COLS, 1):
            w.column_dimensions[get_column_letter(i)].width = max(11, min(28, len(str(k)) + 8))
            if k in MONEY:
                for r in range(2, w.max_row + 1): w.cell(r, i).number_format = '#,##0'
        w.freeze_panes = 'A2'; w.auto_filter.ref = w.dimensions
        return w

    jkset = [r for r in allrows if r['차종 국적'] in JPKR]
    sheet('일본한국_전체', sorted(jkset, key=lambda x: -x['2026']))
    sheet('①신규전환_일본한국', sorted([r for r in jkset if r['구분'].startswith('신규')],
                                key=lambda x: -x['2026']))
    sheet('②재전환_일본한국', sorted([r for r in jkset if r['구분'].startswith('재전환')],
                               key=lambda x: -x['2026']))
    sheet('이탈_일본한국', sorted([r for r in jkset if r['구분'].startswith('이탈')],
                             key=lambda x: -x['2025']))
    sheet('전체_품번', sorted(allrows, key=lambda x: -x['2026']))
    sheet('미분류', sorted([r for r in allrows if r['차종 국적'] == '미분류'],
                        key=lambda x: -(x['2025'] + x['2026'])))

    def put(rows_, bold_first=True):
        for r in rows_:
            s0.append(r)
            if bold_first and r and isinstance(r[0], str) and r[0] and len(r) == 1:
                s0.cell(s0.max_row, 1).font = Font(bold=True)

    s0.append(['Kailos International Pty Ltd · 호주 · SteerStar 추가 오더미션'])
    s0['A1'].font = Font(bold=True, size=13)
    put([['미션', '일본 & 한국 차종의 25년 대비 26년 오더 최대 100% 성장'],
         ['원장', '%s ~ %s (%d행 · 품번 %d종)' % (min(x['d'] for x in R), cut, len(R), len(codes))],
         ['차종 국적 출처', '공식 파일 Maker Country(SAP) · 없으면 그 값으로 학습한 Old CTR Code 맵'],
         [], ['① 미션 수치']])
    s0.append(['구분', '25년 연간', '25년 1~%s' % md[:2], '26년 (~%s)' % md, '동기간 증감'])
    for lab, a25, a25p, a26, g in rows3:
        s0.append([lab, round(a25), round(a25p), round(a26),
                   ('%+.1f%%' % g) if g is not None else '–'])
    put([[], ['② SteerStar 시트 공식값과 대조']])
    s0.append(['', '25년 기준', '26년 실적', '목표', '달성률'])
    s0.append(['SteerStar 시트', round(SS_B25), round(SS_GOT), round(SS_TGT),
               '%.1f%%' % (SS_GOT / SS_TGT * 100)])
    s0.append(['이 분석', round(jk25), round(jk26), round(SS_TGT), '%.1f%%' % (jk26 / SS_TGT * 100)])
    s0.append(['차이', round(jk25 - SS_B25), round(jk26 - SS_GOT), 0, ''])
    s0.append(['차이 원인', 'SAP 매핑이 빠진 #N/A 17행 중 2·3월 $%d 만 공식 시트가 셌고 '
               '9·10월 $%d 는 누락. 메이커 코드가 전부 KH·KK·KD·HO 라 일본·한국 차종이 맞음.'
               % (round(na_23), round(na_amt26 - na_23))])
    put([[], ['③ 신규 전환 SKU (2026 첫 오더)']])
    s0.append(['차종 국적', '품번', '2026 금액'])
    for k, v in bn.most_common(): s0.append([k, v, round(ba[k])])
    put([[], ['④ 재전환 SKU (25년 끊김 → 26년 복귀)']])
    s0.append(['차종 국적', '품번', '2026 금액'])
    for k, v in bn2.most_common(): s0.append([k, v, round(ba2[k])])
    put([[], ['⑤ 미션 증가액의 출처 (일본·한국)']])
    s0.append(['구분', '금액'])
    for lab, v in cont: s0.append([lab, round(v)])
    s0.append(['합', round(sum(v for _, v in cont))])
    put([[], ['주의', '2026 은 원장이 %s 까지라 2025 연간과 직접 비교하면 안 됨 — 동기간 열을 쓸 것' % cut]])
    s0.column_dimensions['A'].width = 34
    for c in 'BCDE': s0.column_dimensions[c].width = 17
    for r in range(1, s0.max_row + 1):
        for c in range(2, 6):
            v = s0.cell(r, c).value
            if isinstance(v, (int, float)): s0.cell(r, c).number_format = '#,##0'

    p = os.path.join('/mnt/user-data/outputs', 'Kailos_일본한국_SKU전환_261111.xlsx')
    os.makedirs('/mnt/user-data/outputs', exist_ok=True)
    wbo.save(p); print('\n→ ' + p)

    def top(sel, key, n=8):
        return [{'sku': c, 'nat': cls[c][0], 'name': nm.get(c, ''),
                 'y24': round(per[c]['2024'], 2), 'y25': round(per[c]['2025'], 2),
                 'y26': round(per[c]['2026'], 2), 'qty': int(perq[c]['2026']),
                 'ord': pern[c]['2026']}
                for c in sorted(sel, key=key)[:n]]

    K = {
        'src': [os.path.basename(KA), os.path.basename(OF)],
        'cust': 'Kailos International', 'country': '호주', 'region': 'OCEANIA',
        'mission': '일본 & 한국 차종의 25년 대비 26년 오더 최대 100% 성장',
        'cut': cut, 'basis': '차종 국적 = 공식 파일 Maker Country(SAP) · 없으면 그 값으로 학습한 Old CTR Code 맵',
        'tgt': SS_TGT, 'b25': round(jk25, 2), 'a26': round(jk26, 2),
        'yoy': round((jk26 / jk25 - 1) * 100, 1) if jk25 else None,
        'rate': round(jk26 / SS_TGT * 100, 1),
        'ss_got': SS_GOT, 'ss_rate': round(SS_GOT / SS_TGT * 100, 1),
        'na_total': round(na_amt26, 2), 'na_feb_mar': round(na_23, 2),
        'na_late': round(na_amt26 - na_23, 2),
        'tot26': round(sum(per[c]['2026'] for c in codes), 2),
        'by_nat': [{'k': lab, 'b25': round(a25p, 2), 'a26': round(a26, 2),
                    'yoy': round(g, 1) if g is not None else None}
                   for lab, a25, a25p, a26, g in rows3],
        'new': {'n': len(jknew), 'amt': round(sum(per[c]['2026'] for c in jknew), 2),
                'n_all': len(new26), 'amt_all': round(sum(per[c]['2026'] for c in new26), 2),
                'by_nat': [{'k': k, 'n': v, 'amt': round(ba[k], 2)} for k, v in bn.most_common()],
                'top': top(jknew, lambda c: -per[c]['2026'])},
        'recov': {'n': len(jkre), 'amt': round(sum(per[c]['2026'] for c in jkre), 2),
                  'n_all': len(re26), 'amt_all': round(sum(per[c]['2026'] for c in re26), 2),
                  'by_nat': [{'k': k, 'n': v, 'amt': round(ba2[k], 2)} for k, v in bn2.most_common()],
                  'top': top(jkre, lambda c: -per[c]['2026'])},
        'keep': {'n': len(keep), 'inc': round(sum(per[c]['2026'] - per[c]['2025'] for c in keep), 2)},
        'lost': {'n': len(lost), 'amt': round(sum(per[c]['2025'] for c in lost), 2),
                 'top': top(lost, lambda c: -per[c]['2025'])},
        'decomp': [{'k': lab, 'v': round(v, 2)} for lab, v in cont],
    }
    K['cover_n'] = K['new']['n'] + K['recov']['n']
    K['cover_amt'] = round(K['new']['amt'] + K['recov']['amt'], 2)
    K['cover_pct'] = round(K['cover_amt'] / jk26 * 100, 1) if jk26 else None

    jp = os.path.join(OUT, 'steerstar_sku.json')
    json.dump(K, open(jp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    html = open(HTML, encoding='utf-8', newline='').read()
    blk = '<script>const KJK = ' + json.dumps(K, ensure_ascii=False, separators=(',', ':')) + ';</script>'
    pat = re.compile(r'<script>const KJK = \{.*?\};</script>', re.S)
    if pat.search(html):
        new = pat.sub(lambda m: blk, html, count=1)
    else:
        anchor = '<script>const SKUI = '
        if anchor not in html: sys.exit('const KJK 자리를 만들 기준(const SKUI)을 찾지 못했음.')
        new = html.replace(anchor, blk + '\n' + anchor, 1)
    if new != html: open(HTML, 'w', encoding='utf-8', newline='').write(new)
    print('steerstar_sku.json · promo_dashboard_v10_6.html(const KJK) 갱신됨')


if __name__ == '__main__':
    main()
