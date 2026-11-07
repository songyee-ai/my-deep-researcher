"""Quote-linked drafting; span and number checks do not certify semantics."""
import json
import re

import pipeline as p
from drafts import render_draft
from evidence import validate_note


def extract_prompt(question,title,source):
    return p.Prompt(
        '제공된 원문에서 질문에 필요한 근거만 최대 8개 줄 범위로 선택하라. 각 범위는 20자 이상의 연속 원문이어야 한다. '
        '비교를 발췌할 때는 주체·비교 대상·비율의 기준·단위가 들어간 문장을 함께 보존하라. '
        '목표·설계 기능·실제 성과를 구분하라. 원문을 재작성하지 말고 표시된 줄 번호만 반환하라. '
        '질문의 특정 대상에 없는 정보를 문서 전체에 전혀 없다고 확대하지 마라. '
        '다른 장비/임무의 언급은 해당 장비/임무의 최종 성과가 아니다. '
        '답할 수 없는 항목은 부족=true로 신고하고 정확히 어떤 대상의 정보가 빠졌는지 이유에 적어라. '
        'JSON {"근거":[{"시작줄":1,"끝줄":2,"메모":"여기서 직접 확인되는 내용"}],'
        '"부족":true 또는 false,"이유":"..."}만 반환하라.\n질문: '+question,
        f'[문서: {title}]\n'+'\n'.join(f'L{i}: {line}' for i,line in enumerate(source.splitlines(),1)))


def resolve_spans(reply,source):
    if not isinstance(reply,dict) or not isinstance(reply.get('근거'),list):
        raise ValueError('원문 줄 범위 배열이 필요합니다.')
    if len(reply['근거'])>8:raise ValueError('원문 범위는 최대 8개입니다.')
    lines=source.splitlines();evidence=[]
    for item in reply['근거']:
        if not isinstance(item,dict):raise ValueError('잘못된 원문 범위입니다.')
        start=item.get('시작줄');end=item.get('끝줄')
        if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines):
            raise ValueError('원문에 없는 줄 범위를 거부했습니다.')
        quote='\n'.join(lines[start-1:end])
        evidence.append({'원문':quote,'메모':item.get('메모')})
    return validate_note({'근거':evidence,'부족':reply.get('부족'),'이유':reply.get('이유','')},source)


def draft_prompt(question,evidence,minimum_chars=600):
    return p.Prompt(
        '한국어 연구 원고를 작성하라. 제공된 발췌만 근거로 하며 외부 사실을 보충하지 마라. '
        '각 단락에 실제 뒷받침하는 근거ID를 붙인다. 주체·비교 대상·수치의 기준과 단위를 '
        '원문과 동일하게 보존하라. A가 B보다 20% 많다는 것을 20% 사용했다로 바꾸지 마라. '
        '원문 수치의 새 계산·반올림·환산을 하지 마라. 관련 없는 장치·성분·성과를 덧붙이지 마라. '
        '설계 목적을 관측 성공으로 바꾸지 마라. 열 설계가 질문이면 원문에 없는 고장 원인을 추정하지 마라. '
        f'한국어 본문 {minimum_chars}자 이상을 목표로 5~8개 단락을 쓰되 근거가 모자라면 분량보다 부족 신고를 우선하라. '
        '부족 이유는 해당 대상의 누락 범위만 말하고 다른 장비에 관한 언급까지 부정하지 마라. '
        '인용 기호를 본문에 넣지 마라. JSON {"단락":[{"내용":"...","근거ID":["E1"]}],'
        '"부족":true 또는 false,"이유":"..."}만 반환하라.',
        '질문: '+question+'\n검증된 원문 발췌:\n'+json.dumps(evidence,ensure_ascii=False))


def numeric_tokens(text):
    # Canonical spelling equivalents only; do not infer ratios or do arithmetic.
    words={'one':'1','two':'2','three':'3','four':'4','five':'5','six':'6',
           'seven':'7','eight':'8','nine':'9','ten':'10','twice':'2'}
    normalized=re.sub(r'\b(?:'+ '|'.join(words) +r')\b',lambda m:words[m.group().lower()],text,flags=re.I)
    return {m.replace(',','') for m in re.findall(r'\d+(?:[.,]\d+)*',normalized)}


def render_grounded(reply,evidence):
    if not isinstance(reply,dict) or not isinstance(reply.get('단락'),list):
        raise ValueError('근거 연결 단락이 필요합니다.')
    paragraphs=[]
    for paragraph in reply['단락']:
        if not isinstance(paragraph,dict):raise ValueError('잘못된 단락입니다.')
        ids=paragraph.get('근거ID')
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in evidence for i in ids):
            raise ValueError('발췌하지 않은 근거ID를 거부했습니다.')
        if len(ids)!=len(set(ids)):raise ValueError('중복 근거ID입니다.')
        text=paragraph.get('내용')
        if not isinstance(text,str):raise ValueError('단락 내용이 필요합니다.')
        available='\n'.join(evidence[i]['quote'] for i in ids)
        if numeric_tokens(text)-numeric_tokens(available):
            raise ValueError('단락의 숫자가 연결한 원문 발췌에 없습니다.')
        paragraphs.append({'내용':text,'출처ID':ids})
    result=render_draft({'단락':paragraphs,'부족':reply.get('부족'),'이유':reply.get('이유','')},
                        {i:e['document'] for i,e in evidence.items()})
    result['evidence_ids_by_paragraph']=[paragraph['근거ID'] for paragraph in reply['단락']]
    result['validation_scope']='Quote existence and numeric membership only; subject, units, and semantic support require review.'
    return result
