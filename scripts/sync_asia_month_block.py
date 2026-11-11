#!/usr/bin/env python3
"""월간 리포트 ASIA 블록(SEPTEMBER_ACTIVITY.sea)의 수치를 AO·AP 에 맞춤.

  python3 scripts/sync_asia_month_block.py [--check]

왜 필요한가
  Sell-out 결과 탭은 const AO(고객사별) · const AP(프로그램별) 를 읽지만,
  월간 리포트의 ASIA 블록은 손으로 박아 둔 SEPTEMBER_ACTIVITY.sea 를 읽음.
  그래서 고객사 묶음 목표를 바로잡아도 월간 리포트에는 옛 값이 남아 있었음
  (GP 목표 $38,863 · 실적 $100,832 / ATC 목표 $22,117 · 실적 0 /
   종합 목표 $835,539 · 실적 $864,046 · 103.4%).

무엇을 옮기나 — 수치만
  종합 목표·실적·달성률 ← AO.tot          (고객사 묶음 = C 표 Total)
  프로그램별 목표·실적·달성률 ← AP.groups  (프로그램 단위, 중복 포함)
  고객사별 목표·실적·달성률 ← AO.rows
  고객사 × 프로그램 달성률 ← AP.rows
  사람이 쓴 문장(note · sep_reflect · pending_badges)은 그대로 둠.

기준이 섞이지 않게
  종합은 고객사 묶음, 프로그램 표는 프로그램 단위 — 둘이 다른 게 정상임.
  같은 줄에 섞어 쓰지 않도록 라벨도 함께 박아 둠.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, 'promo_dashboard_v10_6.html')

CTRY = {'베트남': 'Vietnam', '태국': 'Thailand', '인도네시아': 'Indonesia',
        '말레이시아': 'Malaysia', '필리핀': 'Philippines'}
CODE = {'Vietnam': 'VN', 'Thailand': 'TH', 'Indonesia': 'ID',
        'Malaysia': 'MY', 'Philippines': 'PH'}
SHORT = {'Sales Champion Award': 'Sales Champion', 'Order to Earn POSM': 'POSM',
         'Long-Term Loyalty': 'Loyalty', 'New Product Sell-Out': 'New Product'}
# 화면에 그대로 쓰는 이름 (AO.rows 의 k 는 원장 표기라 조금 다름)
DISP = {'PT Densocentra': 'Densocentra', 'SERI': 'SERI (Seri Wathana)'}


def const(html, name):
    m = re.search(r'const %s\s*=\s*(\{.*?\});' % name, html, re.S)
    if not m: sys.exit('const %s 를 찾지 못했음.' % name)
    return json.loads(m.group(1))


def status(tgt, act, rate):
    if not tgt: return '대상 아님 (Display 프로그램)'
    if not act: return 'Data Pending'
    if rate >= 100: return 'Achieved'
    if rate >= 80: return 'Near Target'
    return 'Behind'


def js(v, nd=0):
    """숫자를 자리수 맞춰 JS 리터럴로."""
    if v is None: return 'null'
    return str(int(round(v))) if nd == 0 else ('%.*f' % (nd, v)).rstrip('0').rstrip('.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    html = open(H, encoding='utf-8', newline='').read()
    AO, AP = const(html, 'AO'), const(html, 'AP')

    m = re.search(r'(  sea: \{)(.*?)(\n    pending_badges:)', html, re.S)
    if not m: sys.exit('SEPTEMBER_ACTIVITY.sea 블록을 찾지 못했음.')
    old = m.group(2)

    # 사람이 쓴 note 는 프로그램 이름으로 물려서 보존
    notes = dict(re.findall(r'\{program:"([^"]+)".*?note:"([^"]*)"\}', old))
    # 옛 블록은 'Display & Visibility', AP 는 'CTR Display & Visibility'
    for k, v in list(notes.items()):
        notes.setdefault('CTR ' + k, v); notes.setdefault(k.replace('CTR ', ''), v)
    reflect = re.search(r'sep_reflect:"((?:[^"\\]|\\.)*)"', old)

    # 고객사 × 프로그램 달성률
    per = {}
    for r in AP['rows']:
        lab = SHORT.get(r['p'])
        if not lab or not r.get('tgt'): continue
        per.setdefault(r['k'], {})[lab] = round((r.get('att') or 0) / 100.0, 2)

    T = AO['tot']
    L = ['  sea: { programs_count:%d, countries:%d, customers:%d, period:"2026년 5~11월",'
         % (len(AP['groups']), len({r['country'] for r in AO['rows']}), AO['n'])]
    L.append('    basis:"종합은 고객사 묶음(5.Sell-out by Customer · C 표 Total) · '
             '프로그램 표는 프로그램 단위라 합계가 더 큼 — 섞어 쓰지 않음",')
    L.append('    sellout_target:%s, sellout_actual:%s, achievement_rate:%s,'
             % (js(T['tgt']), js(T['usd']), js(T['att'] / 100.0, 4)))

    L.append('    programs:[')
    pr = []
    for g in AP['groups']:
        att = g.get('att')
        pr.append('      {program:"%s", customers:%d, target:%s, actual:%s, achievement:%s, note:"%s"}'
                  % (g['p'], g['n'], js(g['tgt']) if g['tgt'] else 'null',
                     js(g['act']) if g['tgt'] else 'null',
                     js(att / 100.0, 4) if att is not None else 'null',
                     notes.get(g['p'], '')))
    L.append(',\n'.join(pr) + '],')

    L.append('    cust_perf:[')
    cp = []
    for r in sorted(AO['rows'], key=lambda r: -(r.get('usd') or 0)):
        ct = CTRY.get(r['country'], r['country']); n = DISP.get(r['k'], r['k'])
        tgt, act = r.get('tgt') or 0, r.get('usd') or 0
        rate = round(act / tgt * 100, 1) if tgt else None
        cp.append('      {c:"%s", n:"%s", t:%s, r:%s, rate:%s, st:"%s"}'
                  % (ct, n, js(tgt) if tgt else 'null', js(act) if tgt else 'null',
                     js(rate, 1) if rate is not None else 'null', status(tgt, act, rate or 0)))
    L.append(',\n'.join(cp) + '],')

    if reflect: L.append('    sep_reflect:"%s",' % reflect.group(1))

    L.append('    customer_ach:[')
    ca = []
    for r in sorted(AO['rows'], key=lambda r: -(r.get('usd') or 0)):
        n = DISP.get(r['k'], r['k']).split(' (')[0]
        ct = CODE.get(CTRY.get(r['country'], ''), '')
        d = per.get(r['k'])
        if d: ca.append('      {name:"%s", country:"%s", ach:%s}'
                        % (n, ct, json.dumps(d, ensure_ascii=False).replace(': ', ':')))
        elif r.get('tgt'): ca.append('      {name:"%s", country:"%s", pending:true}' % (n, ct))
    L.append(',\n'.join(ca) + '],')

    new = '\n'.join(L)
    out = html[:m.start(1)] + new + html[m.end(2):]

    print('월간 리포트 ASIA 블록 (SEPTEMBER_ACTIVITY.sea)')
    o = {k: v for k, v in re.findall(r'sellout_(target|actual):([\d.]+)', old)}
    print('  종합 목표   %s → %s' % (o.get('target', '?'), js(T['tgt'])))
    print('  종합 실적   %s → %s' % (o.get('actual', '?'), js(T['usd'])))
    print('  달성률      %s%%' % js(T['att'], 1))
    for nm in ('GP', 'ATC', 'CSH'):
        ob = re.search(r'n:"%s", t:(\d+), r:(\d+)' % nm, old)
        nb = next((r for r in AO['rows'] if r['k'] == nm), None)
        if ob and nb: print('  %-4s 목표 %s → %s · 실적 %s → %s'
                            % (nm, ob.group(1), js(nb.get('tgt')), ob.group(2), js(nb.get('usd'))))
    if a.check:
        print('변경 있음' if out != html else '변경 없음'); return
    if out != html: open(H, 'w', encoding='utf-8', newline='').write(out)
    print('promo_dashboard_v10_6.html ' + ('갱신됨' if out != html else '변경 없음'))


if __name__ == '__main__':
    main()
