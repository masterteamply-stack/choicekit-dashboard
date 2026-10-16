#!/usr/bin/env python3
"""lordco_data.json(단일 소스) → index.html · promo_dashboard_v10_6.html 동시 반영.
사용: 1) lordco_data.json의 order_usd/sales_usd/qty/prod/last_order_month 수정  2) python3 scripts/sync_lordco.py
 · 메인: _LORDCO_FILE (연관 오더 전년→당해 덮어쓰기)
 · 효과: SEPTEMBER_ACTIVITY.latam.steerstar.lordco, D.campaigns[NA], D.cust_delta, SS Lordco yoy
(--check 로 실행하면 파일을 쓰지 않고 변경 여부만 출력)"""
import json, re, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = json.load(open(os.path.join(ROOT, 'lordco_data.json'), encoding='utf-8'))
L = src['last_order_month']; SL = src['last_sales_month']
o25, o26 = src['order_usd']['y25'], src['order_usd']['y26']
s25, s26 = src['sales_usd']['y25'], src['sales_usd']['y26']
q25, q26 = src['qty']['y25'], src['qty']['y26']
pad = lambda a: (list(a) + [0] * 12)[:12]
o25, o26, s25, s26, q25, q26 = map(pad, (o25, o26, s25, s26, q25, q26))
cum25, cum26 = sum(o25[:L]), sum(o26[:L])
yoy = (cum26 - cum25) / cum25 * 100
write = '--check' not in sys.argv
log = []

# ── 메인 ──
p = os.path.join(ROOT, 'index.html'); s = open(p, encoding='utf-8', newline='').read()
new = "const _LORDCO_FILE = { cust:'%s', last:%d, y25:%s, y26:%s };" % (src['customer'], L, json.dumps(o25[:L], separators=(',', ':')), json.dumps(o26[:L], separators=(',', ':')))
s2, n = re.subn(r"const _LORDCO_FILE = \{.*?\};", lambda _: new, s, count=1, flags=re.S); assert n == 1
if s2 != s: log.append('index.html 변경')
if write: open(p, 'w', encoding='utf-8', newline='').write(s2)

# ── 효과 ──
p = os.path.join(ROOT, 'promo_dashboard_v10_6.html'); s = open(p, encoding='utf-8', newline='').read(); t = s
lo = {'y25': o25, 'y26': o26, 's25': s25, 's26': s26, 'q25': q25, 'q26': q26, 'last26': L,
      'cum25': cum25, 'cum26': cum26, 'slast26': SL, 'scum25': sum(s25[:SL]), 'scum26': sum(s26[:SL]),
      'qcum25': sum(q25[:SL]), 'qcum26': sum(q26[:SL]), 'annual25': sum(o25), 'sannual25': sum(s25), 'ytd26': sum(o26), 'prod': src['prod']}
t, n = re.subn(r'lordco:\{"y25".*?"prod":\[.*?\]\}', lambda _: 'lordco:' + json.dumps(lo, ensure_ascii=False, separators=(',', ':')), t, count=1, flags=re.S); assert n == 1

def edit_json(t, name, fn):
    m = re.search(r'<script>const %s = (\{.*?\});?</script>' % name, t, re.S); obj = json.loads(m.group(1)); fn(obj)
    return t[:m.start(1)] + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + t[m.end(1):]

def fix_D(D):
    na = next(c for c in D['campaigns'] if c['region'] == 'NA')
    na['a25'] = na['all25'] = float(cum25); na['a26'] = na['all26'] = float(cum26); na['yoy'] = na['yoyA'] = yoy
    for x in na['mser']:
        if x['m'].startswith('2026'): x['cur'] = float(o26[int(x['m'][5:]) - 1])
    na['d26'] = float(sum(o26)); na['mo_ord'] = float(o26[L - 1])
    for r in D['cust_delta']:
        if r['name'].strip() == src['customer']: r['a25'] = float(cum25); r['a26'] = float(cum26)
t = edit_json(t, 'D', fix_D)
def fix_SS(SS):
    for r in SS['rows']:
        if r['name'].strip() == src['customer']: r['yoy'] = round(yoy, 1)
t = edit_json(t, 'SS', fix_SS)
if t != s: log.append('promo_dashboard_v10_6.html 변경')
if write: open(p, 'w', encoding='utf-8', newline='').write(t)
print(f'Lordco 오더 동기간 {cum25:,} → {cum26:,} ({yoy:+.1f}%) | 연간 2025 {sum(o25):,} | 2026 누적 {sum(o26):,}')
print('; '.join(log) or '변경 없음', '(check only)' if not write else '')
