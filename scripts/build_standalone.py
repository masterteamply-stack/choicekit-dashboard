#!/usr/bin/env python3
"""효과 분석 대시보드를 파일 하나로 묶음 (OneNote·SharePoint 첨부용).

  python3 scripts/build_standalone.py
  python3 scripts/build_standalone.py --out 내보낼이름.html

왜 필요한가
  promo_dashboard_v10_6.html 은 열릴 때 같은 폴더의 orders.csv · marketing.csv ·
  baseline_data/*.json 을 fetch 함. 이 파일만 떼어 다른 곳(OneNote 페이지,
  SharePoint 문서함)에 올리면 그 파일들이 없어 일부 블록이 '불러오지 못했음'
  으로 뜸. 그래서 필요한 자료를 파일 안에 넣고 fetch 를 가로채게 만듦.

어떻게 작게 만드나
  원본 그대로 넣으면 8MB 가 넘음(orders.csv 2.5MB + baseline 4.5MB).
  읽히는 범위가 정해져 있어 그만큼만 담음.
    orders.csv     쓰이는 4개 열만 남김 — 마지막 오더일(mx)이 달라지면 안 되므로
                   행은 모두 둠
    baseline_data  SteerStar 고객사 7곳의 행만 한 덩어리로 — manifest 도 1개로
    marketing.csv  그대로 (작음)
  화면 코드는 한 글자도 고치지 않음. fetch 가로채기만 머리에 넣음.
"""
import argparse, csv, glob, io, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'promo_dashboard_v10_6.html')
ORD_COLS = ['order date', 'Customer_No', 'sell_type', 'amount']   # cdetCsv 가 보는 열


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='promo_dashboard_standalone.html')
    a = ap.parse_args()
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)

    html = open(SRC, encoding='utf-8', newline='').read()
    CD = json.loads(re.search(r'<script>const CD = (\{.*?\});</script>', html, re.S).group(1))
    codes = {str(c.get('code') or '').strip() for c in (CD.get('custs') or [])}
    codes.discard('')

    # ── orders.csv — 쓰이는 열만
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ORD_COLS, extrasaction='ignore', lineterminator='\n')
    w.writeheader()
    n_ord = 0
    for r in csv.DictReader(open(os.path.join(ROOT, 'orders.csv'), encoding='utf-8')):
        w.writerow({k: r.get(k, '') for k in ORD_COLS}); n_ord += 1
    orders = buf.getvalue()

    # ── baseline — SteerStar 고객사 행만
    rows, n_base = [], 0
    for f in sorted(glob.glob(os.path.join(ROOT, 'baseline_data', 'chunk_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        for o in (d if isinstance(d, list) else d.get('rows', [])):
            n_base += 1
            if str(o.get('Customer_No') or '').strip() in codes:
                rows.append({'Customer_No': o.get('Customer_No'),
                             'sell_type': o.get('sell_type'),
                             'order_date': o.get('order_date'),
                             'amount_usd': o.get('amount_usd')})

    emb = {
        'orders.csv': orders,
        'marketing.csv': open(os.path.join(ROOT, 'marketing.csv'), encoding='utf-8').read(),
        'baseline_data/manifest.json': {'total_chunks': 1,
                                        'note': 'SteerStar 고객사 행만 담은 단일 파일 빌드'},
        'baseline_data/chunk_0000.json': rows,
    }

    shim = ('<script>/* 단일 파일 빌드 — 같은 폴더의 자료를 파일 안에 넣고 fetch 를 가로챔.\n'
            '   재생성: python3 scripts/build_standalone.py */\n'
            'window.__EMB__=' + json.dumps(emb, ensure_ascii=False, separators=(',', ':')) + ';\n'
            '(function(){var f=window.fetch?window.fetch.bind(window):null;\n'
            ' window.fetch=function(u,o){var k=String(u).split("?")[0].replace(/^\\.\\//,"");\n'
            '  if(Object.prototype.hasOwnProperty.call(window.__EMB__,k)){var v=window.__EMB__[k];\n'
            '   var s=(typeof v==="string")?v:JSON.stringify(v);\n'
            '   return Promise.resolve(new Response(s,{status:200,headers:{"Content-Type":'
            '(typeof v==="string")?"text/plain;charset=utf-8":"application/json"}}));}\n'
            '  return f?f(u,o):Promise.reject(new Error("fetch 없음: "+k));};})();</script>\n')

    # 언어 전환 파일도 밖에 있어 같이 넣음 (안에 사전까지 들어 있어 이것만 넣으면 됨)
    tag = re.search(r'<script src="(i18n\.js[^"]*)"></script>', html)
    n_i18n = 0
    if tag:
        js = open(os.path.join(ROOT, 'i18n.js'), encoding='utf-8').read()
        n_i18n = len(js.encode())
        html = html[:tag.start()] + '<script>/* i18n.js 끼워 넣음 */\n' + js + '\n</script>' + html[tag.end():]

    i = html.lower().index('</head>') if '</head>' in html.lower() else html.index('<script>')
    doc = html[:i] + shim + html[i:]
    open(out, 'w', encoding='utf-8', newline='').write(doc)

    mb = lambda n: '%.2fMB' % (n / 1048576)
    print(f"{os.path.basename(out)} — {mb(len(doc.encode()))}")
    print(f"  화면 {mb(len(html.encode()))} + 끼워 넣은 자료 {mb(len(shim.encode()))}")
    print(f"  orders.csv  {n_ord:,} 행 · {len(ORD_COLS)}개 열만 ({mb(len(orders.encode()))})")
    print(f"  baseline    {n_base:,} 행 중 SteerStar 고객사 {len(codes)}곳 {len(rows):,} 행")
    print(f"  marketing.csv 그대로 · i18n.js {mb(n_i18n)} 끼워 넣음" if n_i18n
          else "  marketing.csv 그대로 · i18n.js 태그를 못 찾아 넣지 않음")


if __name__ == '__main__':
    main()
