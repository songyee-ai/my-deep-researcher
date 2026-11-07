"""Verify extractive note spans against the document actually supplied."""
import re


def normalize(text):return re.sub(r'\s+',' ',text).strip()


def validate_note(reply,source):
    if not isinstance(reply,dict) or not isinstance(reply.get('부족'),bool) or not isinstance(reply.get('근거'),list):
        raise ValueError('조사 노트에 근거 배열과 부족 신고가 필요합니다.')
    verified=[]
    for item in reply['근거']:
        quote=item.get('원문') if isinstance(item,dict) else None
        memo=item.get('메모') if isinstance(item,dict) else None
        if not isinstance(quote,str) or len(normalize(quote))<20 or normalize(quote) not in normalize(source):
            raise ValueError('실제 문서에서 확인되지 않는 원문 발췌를 거부했습니다.')
        if not isinstance(memo,str) or not memo.strip():raise ValueError('근거에 연결된 조사 메모가 없습니다.')
        verified.append({'원문':quote,'메모':memo})
    if not verified and not reply['부족']:raise ValueError('근거 없이 충분하다고 한 조사 노트를 거부했습니다.')
    return {'근거':verified,'부족':reply['부족'],'이유':str(reply.get('이유','')),
            'validation':'Exact source-span membership only; semantic relevance still needs review.'}
