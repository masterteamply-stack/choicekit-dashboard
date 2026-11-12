#!/usr/bin/env python3
"""효과 분석 대시보드의 캠페인 KPI 를 메인 대시보드가 읽을 한 장으로 내보냄.

  python3 scripts/sync_kpi_bridge.py            # campaign_kpi.json 다시 만듦
  python3 scripts/sync_kpi_bridge.py --check    # 쓰지 않고 바뀌는지만 봄

왜 필요한가
  두 화면이 같은 수치를 각자 계산하면 반드시 어긋남. 실제로 달성률이
  57.2% 와 87% 로 달랐음 — 메인은 (연관 오더+셀아웃) ÷ (오더 타깃+셀아웃 타깃)
  이고, 효과 분석은 연관 오더 ÷ (전년 동기 ×1.2) 임. 마케팅 KPI 는 뒤쪽이
  맞으므로(전년 대비 20% 증진 목표), 효과 분석을 원본으로 두고 메인은
  이 파일을 읽어 그대로 보여 주게 함.

무엇이 들어가나
  효과 분석의 const D 에서 집행된 캠페인만 추려 전년·당해·목표·달성률,
  캠페인 수, 대상 고객 수, 대상 SKU 와 전환 종수를 계산해 담음.
  환율(KRW/USD 1,280 · 2026 경영환율)도 같이 넣음 — 메인이 매달 외부 API 환율을
  쓰는 바람에
  집행비용이 $57K / $53K 로 갈렸음.
"""
import argparse, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
OUT = os.path.join(ROOT, 'campaign_kpi.json')
MULT = 1.2          # 전년 동기 대비 20% 증진이 마케팅 목표임
KRW = 1280          # 2026 경영환율 — 2027 광고선전비 예산서(환율표 2026-09-30) 기준


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    html = open(SRC, encoding='utf-8').read()
    D = json.loads(re.search(r'<script>const D = (\{.*?\});</script>', html, re.S).group(1))
    cs = [c for c in D['campaigns'] if c.get('started')]
    tg = [c for c in cs if c.get('tgt_sku')]          # 대상 SKU 가 지정된 캠페인만

    # 목표는 캠페인마다 '전년 동기 ×1.2' 이되 따로 정정한 곳이 있음(효과 분석의
    # SELLIN_FIX — 지금은 MENA 가 전쟁 이슈로 $30,000 고정). 여기서 다시 적으면
    # 둘이 갈리므로 효과 분석 쪽 값을 그대로 읽어 씀.
    mult = float(re.search(r'const SELLIN_GROWTH\s*=\s*([\d.]+)', html).group(1))
    fixsrc = re.search(r'const SELLIN_FIX\s*=\s*\{(.*?)\};', html, re.S).group(1)
    fix = {k: float(v) for k, v in re.findall(r"'([^']+)'\s*:\s*\{\s*v\s*:\s*([\d.]+)", fixsrc)}

    def goal(c):
        k = '%s|%s' % (c.get('region') or '', c.get('program') or '')
        if k in fix: return fix[k]
        return (c.get('a25') or 0) * mult if (c.get('a25') or 0) > 0 else 0.0

    a25 = round(sum(c.get('a25') or 0 for c in cs), 2)
    a26 = round(sum(c.get('a26') or 0 for c in cs), 2)
    tgt = round(sum(goal(c) for c in cs), 2)
    cuts = sorted(str(c.get('cut')) for c in cs if c.get('cut'))

    _m = re.search(r'const AO\s*=\s*(\{.*?\});', html, re.S)
    _ao = None
    if _m:
        _t = (json.loads(_m.group(1)).get('tot') or {})
        if _t.get('usd') is not None:
            _ao = {'region': 'ASIA', 'program': 'SELL-OUT Promotion',
                   'tgt': _t.get('tgt'), 'act': _t.get('usd'), 'att': _t.get('att'),
                   'basis': '고객사 묶음 · 5.Sell-out by Customer 의 C 표'}

    # ── 원장(orders.csv)으로 못 세는 캠페인의 월별 시계열 ──────────────────────
    # 메인 대시보드의 월간 Overview 는 orders.csv 를 월별로 쌓는다. 아래 두 캠페인은
    # 그 원장 밖이라 월 합계가 비고, TOTAL 이 상단 카드와 어긋났다. 여기서 월별
    # 원본을 그대로 내려보내면 메인은 '원장 행 대신 이 시계열'을 쓰면 된다
    # (더하는 게 아니라 대체 — 겹치면 두 번 세니까).
    #   중국차 프로모션  오더 원장이 아예 다른 파일 → CNP.rows[].mser 가 원본
    #   NA Lordco       orders.csv 에 2026-01 · 2025 여러 달이 통째로 없음
    #                   → lordco_data.json 의 order_usd 가 원본 (전 품목 · 연간)
    mser = {}
    _c = re.search(r'const CNP\s*=\s*(\{.*?\});', html, re.S)
    if _c:
        for r in (json.loads(_c.group(1)).get('rows') or []):
            if not r.get('started'):
                continue
            k = '%s|%s' % (r.get('region'), r.get('program'))
            cur, prv = {}, {}
            for s in (r.get('mser') or []):
                m = s.get('m')
                if not m:
                    continue
                if s.get('cur'):
                    cur[m] = round(s['cur'], 2)
                if s.get('prv'):
                    prv['%d%s' % (int(m[:4]) - 1, m[4:])] = round(s['prv'], 2)
            if cur or prv:
                mser[k] = {'a26': cur, 'a25': prv,
                           'sku26': r.get('cn26_sku'), 'sku25': r.get('cn25_sku'),
                           'why': '오더 원장 밖 — 중국차 오더분석 파일이 원본'}

    _lp = os.path.join(ROOT, 'lordco_data.json')
    if os.path.exists(_lp):
        _l = json.load(open(_lp, encoding='utf-8'))
        _o = _l.get('order_usd') or {}
        _mk = lambda yr, arr: {'%d-%02d' % (yr, i + 1): float(v)
                               for i, v in enumerate(arr or []) if v}
        cur, prv = _mk(2026, _o.get('y26')), _mk(2025, _o.get('y25'))
        if cur or prv:
            # 브리지 rows 의 a26/a25 는 원장 마감월까지만 센다. 월 시계열도 거기서 자른다.
            _cut = max(cur) if cur else ''
            prv = {m: v for m, v in prv.items() if not _cut or m <= '%d%s' % (int(_cut[:4]) - 1, _cut[4:])}
            mser['NA|Strategic Partner Program'] = {
                'a26': cur, 'a25': prv,
                'why': 'orders.csv 에 2026-01 등이 없음 — lordco_data.json 이 원본(전 품목·연간)'}

    out = {
        '_readme': '효과 분석 대시보드(promo_dashboard_v10_6.html)의 캠페인 KPI. '
                   '메인 대시보드(index.html)가 이 파일을 읽어 같은 값을 보여 줌 — '
                   '두 화면이 각자 계산하지 않게 하려는 것임. '
                   '재생성: python3 scripts/sync_kpi_bridge.py',
        '_basis': '연관 오더 = 캠페인 기간 · 대상 SKU 기준. 달성률 = 당해 ÷ (전년 동기 × 1.2). '
                  '셀아웃 실적·타깃은 달성률에 넣지 않음 — 마케팅 KPI 는 연관 오더만 봄.',
        'src': os.path.basename(SRC),
        'cut': cuts[-1] if cuts else None,
        'cut_from': cuts[0] if cuts else None,
        'a25': a25, 'a26': a26,
        'yoy': round((a26 - a25) / a25 * 100, 1) if a25 else None,
        'target_mult': mult, 'target': tgt,
        'target_fix': fix,
        # 소수 한 자리로 깎아 두면 메인에서 다시 반올림할 때 효과 분석과 1% 갈림
        # (87.49 → 87.5 → '88%'). 두 자리로 두면 양쪽 다 87% 로 떨어짐.
        'achv': round(a26 / tgt * 100, 4) if tgt else None,
        'camps_started': len(cs), 'camps_total': len(D['campaigns']),
        'n_cust': len({str(r.get('code') or '') for r in D.get('cust_delta', []) if r.get('code')}),
        'sku_tgt': sum(c.get('tgt_sku') or 0 for c in tg),
        'sku_conv25': sum(c.get('s25') or 0 for c in tg),
        'sku_conv26': sum(c.get('s26') or 0 for c in tg),
        # ⚠ 합집합이 아니라 **캠페인별 종수의 단순 합**이다(지역 split 기준).
        # 여러 캠페인이 같은 품번을 다루면 중복으로 들어간다. 중복 제거한
        # 합집합은 sku_impact.json 의 camp_sku.union 하나뿐이고, 화면의
        # '캠페인 연관 오더 발생 SKU' 와 Promotion Performance 의 🏆 Total 은
        # 그 합집합을 쓴다. 이 값은 '그냥 더하면 몇 종' 을 보여 줄 때만 쓴다.
        'ord_sku': sum(c.get('ord_sku') or 0 for c in cs),
        'ord_sku_is_sum': True,
        'krw_per_usd': KRW,
        # 비용도 같은 원장(활동 원장)에서 나온 값을 씀. 메인은 marketing.csv 를 따로
        # 집계하고 환율도 달라 $53K / $57K 로 갈렸음.
        'cost_krw': round(sum(c.get('cost') or 0 for c in cs), 2),
        'exp_krw': round(sum(c.get('exp') or 0 for c in cs), 2),
        'cost': round(sum(c.get('cost') or 0 for c in cs) / KRW, 2),
        'exp': round(sum(c.get('exp') or 0 for c in cs) / KRW, 2),
        # ASIA Sell-out 목표·실적 — 고객사 묶음(const AO · C 표)이 원본.
        # marketing.csv 의 SELL-OUT Target 은 프로그램 단위 합이라 메인 대시보드가
        # 그걸 쓰면 $836K/$864K 로 어긋남. 여기서 같이 내려보냄.
        'so': _ao,
        # 원장 밖 캠페인의 월별 원본 — 메인의 월간 Overview 가 원장 행 '대신' 쓴다
        'mser': mser,
        # s26 = 그 캠페인의 연관 오더에 실제로 걸린 품번 종수(효과 분석 집계).
        # 메인 표의 'CK 오더 SKU' 올해 칸이 이걸 쓴다 — 금액과 같은 원본에서.
        # 전년 종수는 효과 분석에도 없어서 메인이 baseline 으로 따로 센다.
        'rows': [{'region': c.get('region'), 'program': c.get('program'),
                  'a25': c.get('a25'), 'a26': c.get('a26'), 'cut': c.get('cut'),
                  # tgt = 이 캠페인의 마케팅 목표(전년 동기 × 1.2, SELLIN_FIX 는 그 값).
                  # 메인 대시보드의 권역 종합 현황이 'Order Target' 칸에 이걸 쓴다 —
                  # marketing.csv 의 Order_Target($) 을 쓰면 $6.7M 이 되어 종합 지표의
                  # 목표 $3.95M·달성률 87.6% 와 갈렸다(그쪽은 58%로 떴음).
                  'tgt': round(goal(c), 2),
                  's26': c.get('ord_sku')}
                 for c in sorted(cs, key=lambda x: -(x.get('a26') or 0))],
    }

    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else None
    changed = old != out
    if not a.check and changed:
        json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f"연관 오더 ${a25:,.0f} → ${a26:,.0f}  ({out['yoy']:+.1f}%)")
    print(f"  목표 ${tgt:,.0f} (전년 ×{mult}" + (f" · 정정 {len(fix)}건" if fix else "") + f") · 달성률 {out['achv']}%")
    print(f"  집행 캠페인 {out['camps_started']}/{out['camps_total']} · 대상 고객 {out['n_cust']}곳")
    print(f"  대상 SKU {out['sku_tgt']}종 · 전환 {out['sku_conv25']} → {out['sku_conv26']}종 · "
          f"오더 발생 SKU {out['ord_sku']}종(캠페인별 합 · 중복 포함)")
    print(f"  실집행 ${out['cost']:,.0f} (₩{out['cost_krw']:,.0f}) · 예상 ${out['exp']:,.0f} "
          f"(₩{out['exp_krw']:,.0f}) · 예상 대비 "
          f"{out['cost'] / out['exp'] * 100:.0f}%" if out['exp'] else '')
    print(f"  환율 KRW/USD {KRW:,} · 원장 ~{out['cut']}")
    print('campaign_kpi.json ' + ('갱신됨' if changed and not a.check
                                  else ('변경 있음' if changed else '변경 없음')))


if __name__ == '__main__':
    main()
