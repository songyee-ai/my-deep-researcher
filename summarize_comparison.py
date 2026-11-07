"""비교 실행 폴더를 질문×조건 표로 요약한다. 순위·승자는 만들지 않는다.

사용: python -X utf8 summarize_comparison.py output/codex_comparisons/<폴더>
결과: 같은 폴더의 summary.md, summary.json
"""
import json
import statistics
import sys
from pathlib import Path

ORDER=['basic','no_roles','no_seeds','no_zones','no_redispatch','single_agent']
LABEL={'basic':'기본형','no_roles':'역할 끔','no_seeds':'시작 자료 끔','no_zones':'구역 공유 끔',
       'no_redispatch':'재조사 끔','single_agent':'단일 대조군'}


def latest_rows(folder):
    rows={}
    for line in (folder/'runs.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            row=json.loads(line);rows[row['id']]=row
    return list(rows.values())


def describe(folder,row):
    item={'id':row['id'],'question_id':row['question_id'],'repeat':row['repeat'],'condition':row['condition'],
          'status':row['status'],'cli_calls':(row.get('transport_stats') or {}).get('cli_invocations')}
    if row['status']!='complete':return item
    result=json.loads((folder/'reports'/f"{row['id']}.json").read_text(encoding='utf-8'))
    events=result['events']
    reads=[e for e in events if e['kind']=='read']
    first=[s for s in result['attempts'] if s['round']==0]
    item.update(sections=len(result['plan']['목차']),report_chars=len(result['report']),
                reads=len(reads),distinct_docs=len({e['document'] for e in reads}),
                first_round_insufficient=sum(s['부족'] for s in first),
                redispatched=len({s['번호'] for s in result['attempts'] if s['round']>0}),
                final_insufficient=sum(s['부족'] for s in result['selected']),
                alarms=sorted(k for k,v in row['metrics']['alarms_expected_zero'].items() if v),
                citation_sentence_fraction=row['metrics']['signals'].get('citation_sentence_fraction'),
                read_budget_utilization=row['metrics']['signals'].get('read_budget_utilization'))
    validation=row.get('baseline_validation')
    if validation:item.update(budget_status=validation['status'],stopping=validation['stopping_reasons'])
    return item


def spread(values):
    values=[v for v in values if v is not None]
    if not values:return '-'
    if len(values)==1:return f'{values[0]}'
    return f"{statistics.mean(values):.0f} ({min(values)}~{max(values)})"


def main(path):
    folder=Path(path)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    items=[describe(folder,row) for row in latest_rows(folder)]
    questions=[q['id'] for q in manifest['questions']]
    lines=[f"# 비교 실행 요약 — {folder.name}",'',
           f"범위: {manifest['scope']} · 모델 {manifest['model_identity']['model']} · 코퍼스 `{manifest['corpus_dir']}` · "
           f"반복 {manifest['repeats']}회 · 공통 읽기 상한 {manifest['shared_read_budget']}건 · 상태 {manifest.get('status')}",'',
           '숫자는 명백한 실패를 거르고 장치가 작동했는지 보는 용도다. 순위나 승자를 뜻하지 않는다. 괄호는 반복 간 최소~최대.','']
    for qid in questions:
        question=next(q['question'] for q in manifest['questions'] if q['id']==qid)
        lines+=[f'## {qid} — {question}','',
                '| 조건 | 완료 | 절 | 보고서 글자 | 읽은 문서 | 처음 부족 신고 절 | 재조사 절 | 최종 부족 절 | 인용 문장 비율 | CLI 호출 | 경보 | 예산 |',
                '|---|---|---|---|---|---|---|---|---|---|---|---|']
        for condition in [c for c in ORDER if c in manifest['conditions']]:
            group=[i for i in items if i['question_id']==qid and i['condition']==condition]
            done=[i for i in group if i['status']=='complete']
            pick=lambda key:spread([i.get(key) for i in done])
            ratio=[round(i['citation_sentence_fraction']*100) for i in done if i.get('citation_sentence_fraction') is not None]
            alarms=sorted({a for i in done for a in i.get('alarms',[])})
            budget=', '.join(sorted({i.get('budget_status','') for i in done if i.get('budget_status')})) or '-'
            lines.append(f"| {LABEL[condition]} | {len(done)}/{len(group)} | {pick('sections')} | {pick('report_chars')} | {pick('reads')} | "
                         f"{pick('first_round_insufficient')} | {pick('redispatched')} | {pick('final_insufficient')} | "
                         f"{spread(ratio)}% | {pick('cli_calls')} | {', '.join(alarms) or '0'} | {budget} |")
        lines.append('')
    unfinished=[i['id'] for i in items if i['status']!='complete']
    lines+=['## 완료되지 않은 실행','',', '.join(unfinished) if unfinished else '없음','']
    (folder/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    (folder/'summary.json').write_text(json.dumps({'runs':items,'ranking':None},ensure_ascii=False,indent=2),encoding='utf-8')
    print('\n'.join(lines))


if __name__=='__main__':main(sys.argv[1])
