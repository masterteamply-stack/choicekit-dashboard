#!/usr/bin/env python3
"""i18n_dict.json(한국어 키 → [English, Русский]) + scripts/i18n_engine.js → i18n.js (두 대시보드 공용).
번역 수정: i18n_dict.json 편집 후 이 스크립트 실행."""
import json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(R, 'i18n_dict.json'), encoding='utf-8'))
e = open(os.path.join(R, 'scripts', 'i18n_engine.js'), encoding='utf-8').read()
assert '/*__DICT__*/{}' in e
open(os.path.join(R, 'i18n.js'), 'w', encoding='utf-8', newline='\n').write(e.replace('/*__DICT__*/{}', json.dumps(d, ensure_ascii=False, separators=(',', ':'))))
print('i18n.js built,', len(d), 'entries')
