"""Fixed, label-free measurements. Signals are not a report-quality ranking."""
from collections import Counter
import re

SENTENCE_RULE_VERSION = 'punctuation_citation_aware_v1'
CITATION = re.compile(r'«([^»]+)»')
METRIC_DESCRIPTIONS = {
    'citation_sentence_fraction': '인용 위치 장치: 채택 원고 문장 중 자신이 읽은 자료의 인용이 붙은 비율. 의미적 적합성은 보장하지 않는다.',
    'cited_read_source_fraction': '근거 사용 장치: 전체 열람 문서 중 채택 원고가 인용한 문서 비율. 질문 관련성이나 정답 재현율이 아니다.',
    'duplicate_read_fraction': '분업/구역 장치: 전체 열람 중 서로 다른 문서 수를 초과한 중복 열람 비율.',
    'read_budget_utilization': '공정한 대조: 실제 읽기 건수 / 조건 공통으로 부여한 총 읽기 상한.',
    'insufficiency_resolution_fraction': '재조사 장치: 처음 부족 신고한 절 중 채택본에서 부족이 해소된 비율. 자기신고 신호다.',
}


def sentences(text):
    """Protect citation titles/decimals; attach citations after punctuation.

    This is a fixed mechanical rule, not a claim of linguistic completeness.
    Korean abbreviations and unusual punctuation still need human inspection.
    """
    saved=[]
    def protect(match):
        saved.append(match.group(0)); return f'\ue000{len(saved)-1}\ue001'
    protected=CITATION.sub(protect,text.replace('\r\n','\n'))
    result=[]; start=0
    boundary=re.compile(r'[.!?。！？]+["”’]?(?:\s*\ue000\d+\ue001)*\s+(?=\S)|\n+')
    chunks=[]
    for match in boundary.finditer(protected):
        chunks.append(protected[start:match.end()].strip()); start=match.end()
    chunks.append(protected[start:].strip())
    for chunk in chunks:
        chunk=re.sub(r'\ue000(\d+)\ue001',lambda m:saved[int(m.group(1))],chunk)
        if not chunk:continue
        if not CITATION.sub('',chunk).strip() and result:result[-1]+=' '+chunk
        else:result.append(chunk)
    return result


def measure(run, corpus, config, granted_read_budget):
    selected=run.get('selected',[]); events=run.get('events',[])
    reads=[e for e in events if e['kind']=='read']
    assignments=[e for e in events if e['kind']=='assignment']
    read_titles=[e['document'] for e in reads]
    unique=set(read_titles); cited=set(); sentence_count=0; cited_sentences=0
    unread=0; unknown=0; short=0
    for section in selected:
        own=set(section['읽은문서']); body=section['본문']; references=CITATION.findall(body)
        unread+=sum(t not in own for t in references)
        unknown+=sum(t not in corpus.docs for t in references)
        cited.update(set(references)&own)
        short+=len(body)<config['minimum_section_chars']
        for sentence in sentences(body):
            sentence_count+=1
            cited_sentences+=bool(set(CITATION.findall(sentence))&own)
    first={s['번호'] for s in run.get('attempts',[]) if s['round']==0 and s['부족']}
    resolved=sum(s['번호'] in first and s['round']>0 and not s['부족'] for s in selected)
    per_attempt=Counter((e['agent'],e['round']) for e in reads)
    excess=sum(max(0,per_attempt[(a['agent'],a['round'])]-a['task']['예산']) for a in assignments)
    contexts={}
    for e in events:
        if e['kind']!='context':continue
        totals=contexts.setdefault(e['actor'],{k:0 for k in ['model_calls','input_chars','source_chars','card_chars','manuscript_chars']})
        totals['model_calls']+=1
        for k in totals:
            if k!='model_calls':totals[k]+=e.get(k,0)
    planned={t['번호'] for t in run.get('plan',{}).get('목차',[])}
    report=run.get('report','')
    retained_all=all(s['본문'] in report for s in selected)
    return {
        'sentence_rule_version':SENTENCE_RULE_VERSION,
        'signals':{'citation_sentence_fraction':cited_sentences/sentence_count if sentence_count else None,
                   'cited_read_source_fraction':len(cited&unique)/len(unique) if unique else None,
                   'duplicate_read_fraction':(len(reads)-len(unique))/len(reads) if reads else None,
                   'read_budget_utilization':len(reads)/granted_read_budget if granted_read_budget else None,
                   'insufficiency_resolution_fraction':resolved/len(first) if first else None},
        'alarms_expected_zero':{'unread_document_citations':unread,'unknown_document_citations':unknown,
                   'attempt_read_budget_excess':excess,'total_read_budget_excess':max(0,len(reads)-granted_read_budget),
                   'missing_planned_sections':len(planned-{s['번호'] for s in selected}),
                   'short_selected_sections':short,'synthesis_lost_section_bodies':0 if retained_all else 1},
        'counts':{'read_events':len(reads),'unique_read_documents':len(unique),'granted_read_budget':granted_read_budget,
                  'issued_attempt_budget':sum(a['task']['예산'] for a in assignments),'sentence_count':sentence_count,
                  'selected_sections':len(selected),'report_chars':len(report),'raw_read_chars':sum(e['source_chars'] for e in reads)},
        'context_by_actor':contexts,
        'interpretation':'No gold labels, judge model, relevance recall, semantic support score, or automatic ranking. Zero alarms do not prove factual correctness.'}
