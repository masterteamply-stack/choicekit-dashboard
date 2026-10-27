#!/usr/bin/env python3
"""SteerStar 2026 management.xlsx → promo_dashboard_v10_6.html 의 const SS / const CD.mission 갱신.

  python3 scripts/sync_steerstar.py --xlsx "SteerStar_2026_management.xlsx"
  python3 scripts/sync_steerstar.py --xlsx <파일> --check     # 쓰지 않고 변경 여부만

읽는 시트
  SteerStar Plan  활동·메인미션·BizRewards·메모·채널
  Mission order   파트너별 월별 오더(미션 기간) · 괄호 친 달은 미션 기간 밖(참고)
  Mission lead    파트너별 월별 설문 참여 수
  예산            예산 항목·금액·내용

반영되는 화면
  · SteerStar 탭 — 파트너별 오더 미션, 활동 계획과 진행 메모, 예산 집행, 월별 추이
  · 설문 인사이트 탭 — 파트너별 설문 진행(SS.rows 의 leads/lser)
  · 고객사 요약(전체 권역) — SteerStar 오더 미션 / 설문 리드 열 (const CD 의 mission)

오더 '실적'은 각 미션이 약속한 기준(SERI 는 이벤트 기간 오더, Lordco 는 Sell-out)이라
원장에서 다시 뽑지 않고 이 파일의 값을 그대로 쓴다. 영업 Order Target 과는 무관하다.
"""
import json, os, re, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
LEAD_TGT = 200          # 설문 참여 수 목표 — 전사 공통
MONTHS = [f'{i}월' for i in range(1, 13)]
DROP = '26 SteerStar 제외'


def txt(v):
    if v is None: return ''
    s = unicodedata.normalize('NFC', str(v)).strip()
    return '' if s == '-' else re.sub(r'\s*\n\s*', ' · ', s)


def num(v):
    """숫자면 (값, False), 괄호 친 문자열이면 (값, True) = 미션 기간 밖, 그 외 None."""
    if isinstance(v, (int, float)): return float(v), False
    s = str(v or '').strip().replace(',', '')
    m = re.fullmatch(r'\((\d+(?:\.\d+)?)\)', s)
    if m: return float(m.group(1)), True
    try: return float(s), False
    except ValueError: return None, False


def sheet(wb, name):
    return [list(r) for r in wb[name].iter_rows(values_only=True)]


xl = sys.argv[sys.argv.index('--xlsx') + 1] if '--xlsx' in sys.argv else None
if not xl:
    print('--xlsx <SteerStar management.xlsx> 가 필요합니다.'); sys.exit(1)
import openpyxl
wb = openpyxl.load_workbook(xl, data_only=True)

# ── 1) SteerStar Plan
plan = {}
order_of = []
region = ''
for r in sheet(wb, 'SteerStar Plan')[1:]:
    r = (r + [None] * 22)[:22]
    name = txt(r[2])
    if not name: continue
    region = txt(r[0]) or region
    ch = [txt(r[i]) for i in (3, 4, 5, 6, 7) if txt(r[i])]
    plan[name] = dict(region=region, country=txt(r[1]), name=name,
                      act=txt(r[8]), when=txt(r[9]).replace('Arpil', 'April'),
                      main=txt(r[10]), sub=txt(r[12]),
                      # BizRewards 는 금액만 적힌 칸과 설명이 적힌 칸이 섞여 있다
                      credit=(f'${int(r[19]):,}' if isinstance(r[19], (int, float)) else txt(r[19])),
                      note=txt(r[20]), ch=ch,
                      dropped=(txt(r[12]) == DROP))
    order_of.append(name)

# ── 2) Mission order / Mission lead
orders, leads = {}, {}
for r in sheet(wb, 'Mission order')[1:]:
    r = (r + [None] * 19)[:19]
    name = txt(r[2])
    if not name: continue
    tgt, _ = num(r[4])
    ser, pre = [], []
    for i, m in enumerate(MONTHS):
        v, is_pre = num(r[5 + i])
        if v is None: continue
        (pre if is_pre else ser).append(dict(m=m, v=round(v, 1)))
    orders[name] = dict(tgt=tgt or 0.0, ser=ser, pre=pre,
                        got=round(sum(x['v'] for x in ser), 2),
                        pre_sum=round(sum(x['v'] for x in pre), 2) or None)
for r in sheet(wb, 'Mission lead')[1:]:
    r = (r + [None] * 18)[:18]
    name = txt(r[2])
    if not name or name not in plan: continue
    ser = []
    for i, m in enumerate(MONTHS):
        v, _ = num(r[4 + i])
        if v: ser.append(dict(m=m, v=int(v)))
    leads[name] = dict(ser=ser, n=int(sum(x['v'] for x in ser)))

# ── 3) 현재 블록(전년 대비는 고객사 오더 원장에서 가져온다)
html = open(HTML, encoding='utf-8', newline='').read()
mCD = re.search(r'<script>const CD = (\{.*?\});</script>', html, re.S)
mSS = re.search(r'<script>const SS = (\{.*?\});</script>', html, re.S)
if not (mCD and mSS):
    print('CD 또는 SS 블록을 찾지 못했습니다.'); sys.exit(1)
CD, SSold = json.loads(mCD.group(1)), json.loads(mSS.group(1))
yoy_of = {}
for c in CD['custs']:
    p, q = c.get('cum25') or 0, c.get('cum26') or 0
    yoy_of[c.get('ss_name') or c['name']] = round((q - p) / p * 100, 1) if p else None

# ── 4) SS.rows
rows = []
for name in order_of:
    p = plan[name]
    o = orders.get(name, dict(tgt=0.0, ser=[], pre=[], got=0.0, pre_sum=None))
    l = leads.get(name, dict(ser=[], n=0))
    drop = p['dropped']
    tgt, got = (0.0, 0.0) if drop else (o['tgt'], o['got'])
    rows.append(dict(
        region=p['region'], file_region='', country=p['country'], name=name,
        act=p['act'], when=p['when'], main=p['main'], sub=p['sub'],
        tgt=tgt, got=got, rate=(round(got / tgt * 100, 1) if tgt else None),
        leads=l['n'], lead_tgt=(0 if drop else LEAD_TGT),
        lead_rate=(None if drop else round(l['n'] / LEAD_TGT * 100, 1)),
        oser=o['ser'], opre=o['pre'], lser=l['ser'], pre_sum=o['pre_sum'],
        credit=p['credit'], note=p['note'], dropped=drop, ch=p['ch'],
        yoy=yoy_of.get(name)))

live = [r for r in rows if not r['dropped']]
scored = [r for r in live if r['tgt']]
S = lambda a, k: round(sum(r[k] or 0 for r in a), 2)
tot_tgt, tot_got = S(scored, 'tgt'), S(scored, 'got')
lead, ltgt = int(S(live, 'leads')), int(S(live, 'lead_tgt'))

budget = [dict(k=txt(r[0]), v=float(r[1] or 0), d=txt(r[2]).replace(' · ', '\n'))
          for r in sheet(wb, '예산')[1:] if txt(r[0])]
btot = next((b['v'] for b in budget if b['k'] == '총 예산'), SSold.get('btot'))

# 업로드 경로의 해시 접두사(8ea25dd8-...)는 떼고 원래 파일 이름만 남긴다
src_name = re.sub(r'^[0-9a-f]{8,}-', '', os.path.basename(xl)).replace('_', ' ')
SS = dict(src=src_name, lead_target=LEAD_TGT,
          n=len(live), n_live=len(live), n_drop=len(rows) - len(live),
          tot_tgt=tot_tgt, tot_got=tot_got,
          tot_rate=(round(tot_got / tot_tgt * 100, 1) if tot_tgt else None),
          leads=lead, lead_tgt=ltgt,
          lead_rate=(round(lead / ltgt * 100, 1) if ltgt else None),
          hit=sum(1 for r in scored if (r['rate'] or 0) >= 100),
          lead_hit=sum(1 for r in live if (r['lead_rate'] or 0) >= 100),
          n_scored=len(scored), months=MONTHS,
          mser=SSold.get('mser', []), budget=budget, btot=btot, rows=rows)

# ── 5) CD.custs 의 mission
by_name = {r['name']: r for r in rows}
touched = []
for c in CD['custs']:
    r = by_name.get(c.get('ss_name') or c['name'])
    if not r: continue
    m = c.setdefault('mission', {})
    m.update(act=r['act'], when=r['when'], main=r['main'], sub=r['sub'],
             tgt=r['tgt'], got=r['got'], rate=r['rate'],
             leads=r['leads'], lead_tgt=r['lead_tgt'], lead_rate=r['lead_rate'],
             pre_sum=r['pre_sum'], credit=r['credit'], note=r['note'],
             dropped=r['dropped'], ch=r['ch'], yoy=r['yoy'])
    touched.append(c['id'])

J = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
out = html[:mSS.start()] + '<script>const SS = ' + J(SS) + ';</script>' + html[mSS.end():]
m2 = re.search(r'<script>const CD = \{.*?\};</script>', out, re.S)
out = out[:m2.start()] + '<script>const CD = ' + J(CD) + ';</script>' + out[m2.end():]
changed = out != html

if '--check' in sys.argv:
    print('변경 있음' if changed else '변경 없음'); sys.exit(0)
if changed:
    open(HTML, 'w', encoding='utf-8', newline='').write(out)

print(f"SteerStar {len(rows)}곳 (진행 {len(live)} · 제외 {SS['n_drop']}) · 자료 {SS['src']}")
print(f"오더 미션 {tot_got:,.0f} / {tot_tgt:,.0f} = {SS['tot_rate']}% · 넘긴 곳 {SS['hit']}/{len(scored)}")
print(f"설문 {lead:,} / {ltgt:,} = {SS['lead_rate']}% · 목표 달성 {SS['lead_hit']}곳")
print(f"{'파트너':34}{'목표':>11}{'실적':>12}{'달성률':>8}{'리드':>7}  메모")
for r in rows:
    print(f"  {r['name'][:30]:32}{r['tgt']:>11,.0f}{r['got']:>12,.0f}"
          f"{(f'{r['rate']:.0f}%' if r['rate'] is not None else '–'):>8}{r['leads']:>7}  {r['note'][:40]}")
print(f"\nCD.mission 갱신: {', '.join(touched)}")
print('promo_dashboard_v10_6.html ' + ('갱신됨' if changed else '변경 없음'))
