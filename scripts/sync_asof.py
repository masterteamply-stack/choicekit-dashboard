#!/usr/bin/env python3
"""대시보드 상단 기준일(D.today)을 실제 자료 날짜에 맞춤.

  python3 scripts/sync_asof.py [--check]

왜 필요한가
  D.today 는 파이프라인이 D 를 만든 날짜라 손으로 자료를 덧댈 때마다 뒤처짐.
  실제로 캠페인 원장은 2026-10-26 까지, 10월 리포트는 2026-10-30 기준인데
  상단에는 2026-09-26 이 떠 있었음.

무엇에 맞추나
  (1) 월간 리포트들의 데이터 기준일(generated_at) 과
  (2) 캠페인별 원장 마감일(cut) 중 가장 늦은 날.
  둘 다 화면에 이미 적혀 있는 날짜라 상단과 본문이 따로 놀지 않음.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    html = open(HTML, encoding='utf-8', newline='').read()
    m = re.search(r'<script>const D = (\{.*?\});</script>', html, re.S)
    D = json.loads(m.group(1))

    # 월간 리포트들의 데이터 기준일 — const <달>_ACTIVITY = { ... generated_at: '...' }
    gens = re.findall(r"_ACTIVITY\s*=\s*\{[^{}]*?generated_at:\s*'(\d{4}-\d{2}-\d{2})'", html)
    cuts = [str(c.get('cut')) for c in D.get('campaigns', []) if DATE.match(str(c.get('cut') or ''))]
    cand = sorted(set(gens) | set(cuts))
    if not cand:
        sys.exit('기준이 될 날짜를 찾지 못했음.')
    new = cand[-1]
    old = D.get('today')

    print(f"기준일 {old} → {new}")
    print(f"  월간 리포트 기준일 {' · '.join(sorted(set(gens))) or '없음'}")
    print(f"  캠페인 원장 마감 {' · '.join(sorted(set(cuts))) or '없음'}")
    if old == new:
        print('변경 없음'); return

    D['today'] = new
    out = html[:m.start(1)] + json.dumps(D, ensure_ascii=False, separators=(',', ':')) + html[m.end(1):]
    if a.check:
        print('변경 있음'); return
    open(HTML, 'w', encoding='utf-8', newline='').write(out)
    print('promo_dashboard_v10_6.html 갱신됨')


if __name__ == '__main__':
    main()
