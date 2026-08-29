#!/usr/bin/env python3
"""GSRT 轨B判分: 独立盲重标注 vs 金标推断层一致性。
用法: python3 agreement_report.py relabel_runs/<run>.json
输出: agreement_report_<run>.json (emotion 三档 + felt_intent role-signal + shot_type exact)
"""
import json, sys, re, unicodedata
from datetime import datetime, timezone

GS = '/home/kai/learning_sets/golden-standard-xiaojianghu-ep01'
LAB = '/data/workspace/kais-shot-timeline/gsrt'

EMO_SYN = {  # 同义聚类 → 规范档
    'warm': ['温暖','温馨','治愈','安心','幸福','舒适'],
    'admire': ['崇拜','钦佩','敬佩','仰慕','自豪','骄傲'],
    'fear': ['恐惧','害怕','紧张','担忧','焦虑','不安','惊恐'],
    'tense': ['紧张','危急','危机','压迫','千钧一发'],
    'joy': ['开心','快乐','高兴','欢喜','兴奋','喜悦'],
    'sad': ['委屈','难过','伤心','失落','悲伤'],
    'resolve': ['决然','坚定','成长','勇气','决心'],
    'calm': ['平静','叙事推进','舒缓','日常'],
}
ROLE_SIGNALS = [  # felt_intent 角色信号词
    ('hook', ['钩','开场','建立','亮相','第一印象']),
    ('setup', ['铺陈','铺垫','日常','介绍','建立','世界观','关系']),
    ('turn', ['转折','打破','突变','出现','来袭','入侵','挑战']),
    ('climax', ['高潮','苦战','危机','生死','决战','爆发']),
    ('resolve', ['收束','化解','胜利','解决','策略','取胜']),
    ('growth', ['成长','约定','承诺','传承','尾声','结尾']),
    ('dialogue_carry', ['对话','对白','交流','问答','对话推进']),
    ('emotion_beat', ['情绪','情感','共情','催泪','温情']),
]

def norm(s):
    if not s: return ''
    s = unicodedata.normalize('NFKC', str(s))
    return re.sub(r'\s+', '', s)

def emo_bucket(s):
    for b, words in EMO_SYN.items():
        if any(w in s for w in words): return b
    return 'other:' + s[:6]

def emo_match(g, r):
    g, r = norm(g), norm(r)
    if not g or not r: return 'missing'
    gb, rb = emo_bucket(g), emo_bucket(r)
    if gb == rb: return 'exact'
    if gb.startswith('other') or rb.startswith('other'):
        # 桶外字面部分重合也算 partial
        chars = set(g) & set(r)
        return 'partial' if len(chars) >= 2 else 'off'
    return 'off'

def role_signals(s):
    s = norm(s)
    return {name for name, words in ROLE_SIGNALS if any(w in s for w in words)}

def intent_match(g, r):
    gs, rs = role_signals(g), role_signals(r)
    if not gs and not rs: return 'missing'
    if gs & rs: return 'exact' if len(gs & rs) >= max(1, len(gs)//2) else 'partial'
    return 'off'

def shot_type_match(g, r):
    g, r = norm(g), norm(r)
    if not g or not r: return 'missing'
    alias = {'特写':['大特写','特写'],'近景':['中近景','近景'],'中景':['中景'],
             '中全景':['中全景','中远景'],'全景':['全景','全景镜头'],'远景':['远景','大远景','外景']}
    for k, vals in alias.items():
        if (k in g or g in vals) and (k in r or r in vals): return 'exact'
    return 'off'

def main(run_path):
    answers = {a['shot_id']: a for a in json.load(open(f'{LAB}/golden_answers_sealed.json'))}
    relabel = {r['shot_id']: r for r in json.load(open(run_path))}
    rows = []
    for sid, a in answers.items():
        r = relabel.get(sid, {})
        rows.append({
            'shot_id': sid,
            'emotion': emo_match(a.get('emotion'), r.get('emotion')),
            'felt_intent': intent_match(a.get('felt_intent') or '', r.get('felt_intent') or ''),
            'shot_type': shot_type_match(a.get('shot_type'), r.get('shot_type')),
            '_detail': {'golden': {'emotion': a.get('emotion'), 'felt_intent': (a.get('felt_intent') or '')[:60], 'shot_type': a.get('shot_type')},
                        'relabel': {'emotion': r.get('emotion'), 'felt_intent': (r.get('felt_intent') or '')[:60], 'shot_type': r.get('shot_type')},
                        'notes': r.get('notes','')[:80]},
        })
    from collections import Counter
    summary = {}
    for dim in ('emotion','felt_intent','shot_type'):
        c = Counter(row[dim] for row in rows)
        n = sum(v for k,v in c.items() if k != 'missing')
        summary[dim] = {
            'exact': c.get('exact',0), 'partial': c.get('partial',0), 'off': c.get('off',0), 'missing': c.get('missing',0),
            'agreement_exact_pct': round(c.get('exact',0)/n*100,1) if n else None,
            'agreement_exact_plus_partial_pct': round((c.get('exact',0)+c.get('partial',0))/n*100,1) if n else None,
        }
    out = {
        'run': run_path, 'judged_at': datetime.now(timezone.utc).isoformat(),
        'n_shots': len(rows), 'summary': summary,
        'interpretation': _interpret(summary),
        'rows': rows,
    }
    outp = f"{LAB}/agreement_report_{re.sub(r'[^0-9A-Za-z_-]','',run_path.split('/')[-1])}"
    json.dump(out, open(outp+'.json','w'), ensure_ascii=False, indent=1)
    print(json.dumps({'output': outp+'.json', 'summary': summary, 'interpretation': out['interpretation']}, ensure_ascii=False, indent=1))

def _interpret(s):
    e = s['emotion']['agreement_exact_pct'] or 0
    ep = s['emotion']['agreement_exact_plus_partial_pct'] or 0
    i = s['felt_intent']['agreement_exact_plus_partial_pct'] or 0
    lines = []
    if ep >= 70 and i >= 70: lines.append('T3高一致: 金标推断层可信, 零点有效')
    elif ep < 40 and i < 40: lines.append('T3低一致: 金标推断层单采样噪声嫌疑大, 建议多标注集成或降级为参考')
    else: lines.append('T3中等: 需分歧字段抽样视频终审定谳')
    return lines

if __name__ == '__main__':
    main(sys.argv[1])
