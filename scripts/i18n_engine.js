/* CTR ChoiceKit dashboards · 언어 전환 (KO / EN / RU)
 * 두 대시보드(index.html, promo_dashboard_v10_6.html)가 공유. 원문(한국어)은 그대로 두고 화면 문구만 번역한다.
 * 번역 추가/수정: i18n_dict.json 의 키(한국어, 숫자는 {1},{2}…)를 고친 뒤 `python3 scripts/build_i18n.py` 실행. */
(function () {
  'use strict';
  var DICT = /*__DICT__*/{};
  var LANGS = ['ko', 'en', 'ru'];
  var LABEL = { ko: 'KO', en: 'EN', ru: 'RU' };
  var TITLE = { ko: '한국어', en: 'English', ru: 'Русский' };
  var KEY = 'ck_lang';
  var MON = { en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], ru: ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'] };
  var HAN = /[가-힣]/, LAT = /[A-Za-z]{2}/;
  function need(v) { return HAN.test(v) || (lang === 'ru' && LAT.test(v)); }
  var NUM = /[$₩]?\d[\d,]*(?:\.\d+)?(?:[%KMB])?(?:[-\/:]\d+)*/g;
  var lang = 'ko';
  try { var sv = localStorage.getItem(KEY); if (LANGS.indexOf(sv) >= 0) lang = sv; } catch (e) {}

  function tpl(s) { var nums = []; var t = s.replace(NUM, function (m) { nums.push(m); return '{' + nums.length + '}'; }); return { t: t, n: nums }; }
  function fill(str, nums) { return str.replace(/\{(\d+)\}/g, function (m, i) { return nums[i - 1] != null ? nums[i - 1] : m; }); }
  function core(c, L) {
    var x = tpl(c), hit = DICT[x.t], i = L === 'en' ? 0 : 1;
    if (hit) return fill(hit[i], x.n);
    var mm = /^(\d{1,2})월$/.exec(c); if (mm && +mm[1] >= 1 && +mm[1] <= 12) return MON[L][+mm[1] - 1];
    if (c.indexOf(' · ') > 0) { var parts = c.split(' · '), ok = true, out = parts.map(function (p) { var r = core1(p, L); if (r == null) ok = false; return r; }); if (ok) return out.join(' · '); }
    return null;
  }
  function core1(p, L) { var x = tpl(p), hit = DICT[x.t]; if (hit) return fill(hit[L === 'en' ? 0 : 1], x.n); if (!HAN.test(p)) return p; return null; }
  function tr(s, L) {
    if (!s || !(HAN.test(s) || (L === 'ru' && LAT.test(s)))) return s;
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s), c = m[2].replace(/\s+/g, ' ');
    var r = core(c, L);
    return r == null ? s : m[1] + r + m[3];
  }

  var TEXT = new WeakMap(), ATTR = new WeakMap(), AT = ['title', 'placeholder', 'aria-label', 'alt'];
  var busy = false;
  function skip(el) { var n = el; while (n && n.nodeType === 1) { var t = n.tagName; if (t === 'SCRIPT' || t === 'STYLE' || t === 'TEXTAREA' || t === 'CODE' || n.hasAttribute('data-noi18n')) return true; n = n.parentNode; } return false; }
  function doText(n) {
    var rec = TEXT.get(n), v = n.nodeValue;
    if (rec && v === rec.out) { if (lang === 'ko') { n.nodeValue = rec.orig; TEXT.delete(n); } else { var o2 = tr(rec.orig, lang); if (o2 !== rec.out) { rec.out = o2; n.nodeValue = o2; } } return; }
    if (lang === 'ko' || !need(v)) { if (rec) TEXT.delete(n); return; }
    var out = tr(v, lang); if (out !== v) { TEXT.set(n, { orig: v, out: out }); n.nodeValue = out; }
  }
  function doAttrs(el) {
    var m = ATTR.get(el);
    AT.forEach(function (a) {
      if (!el.hasAttribute(a)) return;
      var v = el.getAttribute(a), rec = m && m[a];
      if (rec && v === rec.out) { var nv = lang === 'ko' ? rec.orig : tr(rec.orig, lang); if (nv !== v) el.setAttribute(a, nv); rec.out = nv; if (lang === 'ko') delete m[a]; return; }
      if (lang === 'ko' || !need(v)) return;
      var out = tr(v, lang); if (out !== v) { if (!m) { m = {}; ATTR.set(el, m); } m[a] = { orig: v, out: out }; el.setAttribute(a, out); }
    });
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!skip(root.parentNode)) doText(root); return; }
    if (root.nodeType !== 1 || skip(root)) return;
    doAttrs(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null), n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) { if (!skip(n.parentNode)) doText(n); } else if (!skip(n)) doAttrs(n); }
  }
  var mo = null, pend = [], sched = false;
  function flush() {
    sched = false; var list = pend; pend = []; busy = true;
    try { list.forEach(function (n) { if (n.isConnected !== false) walk(n); }); } finally { busy = false; if (mo) mo.takeRecords(); }
  }
  function queue(n) { pend.push(n); if (!sched) { sched = true; (window.requestAnimationFrame || setTimeout)(flush); } }
  function observe() {
    if (mo || !document.body) return;
    mo = new MutationObserver(function (recs) {
      if (busy) return;
      recs.forEach(function (r) {
        if (r.type === 'childList') r.addedNodes.forEach(function (n) { queue(n); });
        else if (r.type === 'characterData') queue(r.target);
        else if (r.type === 'attributes') queue(r.target);
      });
    });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: AT });
  }

  /* Chart.js 라벨(캔버스) */
  var CH = new WeakMap();
  function chartTr(chart) {
    var d = chart.data || {}, rec = CH.get(chart) || { lab: null, ds: [] };
    function conv(arr, prev) {
      if (!Array.isArray(arr)) return;
      var same = prev && prev.out.length === arr.length && arr.every(function (v, i) { return v === prev.out[i]; });
      var base = same ? prev.orig : arr.slice();
      var out = base.map(function (v) { return typeof v === 'string' ? (lang === 'ko' ? v : tr(v, lang)) : v; });
      for (var i = 0; i < out.length; i++) arr[i] = out[i];
      return { orig: base, out: out };
    }
    rec.lab = conv(d.labels, rec.lab) || rec.lab;
    (d.datasets || []).forEach(function (ds, i) {
      var p = rec.ds[i], same = p && ds.label === p.out;
      var base = same ? p.orig : ds.label, out = typeof base === 'string' ? (lang === 'ko' ? base : tr(base, lang)) : base;
      if (typeof ds.label === 'string') ds.label = out; rec.ds[i] = { orig: base, out: out };
    });
    CH.set(chart, rec);
  }
  function hookCharts() {
    if (!window.Chart || window.Chart.__ckI18n) return !!window.Chart;
    window.Chart.__ckI18n = true;
    window.Chart.register({ id: 'ckI18n', beforeUpdate: chartTr });
    return true;
  }
  function refreshCharts() {
    if (!window.Chart) return;
    var inst = window.Chart.instances; if (!inst) return;
    Object.keys(inst).forEach(function (k) { try { inst[k].update('none'); } catch (e) {} });
  }

  var btns = [];
  function paintButtons() { btns.forEach(function (b) { var on = b.getAttribute('data-lang') === lang; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); }); }
  var docTitle = null;
  function apply() {
    document.documentElement.setAttribute('lang', lang);
    if (docTitle == null) docTitle = document.title;
    document.title = lang === 'ko' ? docTitle : tr(docTitle, lang);
    busy = true; try { walk(document.body); } finally { busy = false; if (mo) mo.takeRecords(); }
    hookCharts(); refreshCharts(); paintButtons();
  }
  function setLang(l) {
    if (LANGS.indexOf(l) < 0 || l === lang) return;
    lang = l; try { localStorage.setItem(KEY, l); } catch (e) {}
    apply();
    try { window.dispatchEvent(new CustomEvent('ck-lang', { detail: l })); } catch (e) {}
  }
  function mount(host) {
    if (!host) return;
    host.classList.add('ck-lang'); host.setAttribute('data-noi18n', '');
    host.setAttribute('role', 'group'); host.setAttribute('aria-label', 'Language');
    host.innerHTML = '';
    LANGS.forEach(function (l) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = LABEL[l]; b.title = TITLE[l];
      b.setAttribute('data-lang', l); b.addEventListener('click', function (e) { e.stopPropagation(); setLang(l); });
      host.appendChild(b); btns.push(b);
    });
    paintButtons();
  }
  var css = document.createElement('style');
  css.textContent = '.ck-lang{display:inline-flex;align-items:center;gap:0;border:1px solid var(--bd,var(--line,#cfd4dc));border-radius:6px;overflow:hidden;vertical-align:middle;margin:0 10px 0 6px;flex:0 0 auto;white-space:nowrap}' +
    '.ck-lang button{all:unset;cursor:pointer;padding:3px 8px;font:600 11px/1.4 inherit;font-family:inherit;letter-spacing:.04em;color:inherit;opacity:.7}' +
    '.ck-lang button+button{border-left:1px solid var(--bd,var(--line,#cfd4dc))}' +
    '.ck-lang button:hover{opacity:1}.ck-lang button.on{background:var(--brand,#CE0E2D);color:#fff;opacity:1}';
  (document.head || document.documentElement).appendChild(css);

  window.CK_I18N = { get lang() { return lang; }, set: setLang, mount: mount, tr: function (s) { return lang === 'ko' ? s : tr(s, lang); } };
  function boot() {
    mount(document.getElementById('ckLang'));
    observe(); apply();
    var n = 0, t = setInterval(function () { if (hookCharts() || ++n > 40) { clearInterval(t); if (lang !== 'ko') refreshCharts(); } }, 250);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
