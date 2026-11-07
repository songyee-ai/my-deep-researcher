"""Validate source IDs, then render citations. Never infer a missing source."""
import re


def render_draft(reply,source_map):
    if not isinstance(reply,dict) or not isinstance(reply.get('부족'),bool):
        raise ValueError('Draft needs an explicit boolean insufficiency report')
    paragraphs=reply.get('단락')
    if not isinstance(paragraphs,list) or not paragraphs:
        raise ValueError('Draft needs nonempty structured paragraphs')
    bodies=[]
    for paragraph in paragraphs:
        if not isinstance(paragraph,dict):raise ValueError('Invalid paragraph')
        text=paragraph.get('내용'); refs=paragraph.get('출처ID')
        if not isinstance(text,str) or not text.strip() or '«' in text or '»' in text:
            raise ValueError('Paragraph text must be nonempty and omit manual citation markup')
        if not isinstance(refs,list) or not refs or any(not isinstance(i,str) or i not in source_map for i in refs):
            raise ValueError('Missing or unread source ID; refusing to invent a citation')
        if len(refs)!=len(set(refs)):raise ValueError('Duplicate paragraph source ID')
        bodies.append(text.strip()+' '+''.join(f'«{source_map[i]}»' for i in refs))
    body='\n\n'.join(bodies)
    return {'본문':body,'부족':reply['부족'],'이유':str(reply.get('이유','')),
            '인용':re.findall(r'«([^»]+)»',body),'raw_paragraphs':paragraphs,
            'note':'Source membership is validated. Semantic claim support still needs source review.'}


def draft_schema(source_ids):
    return {'type':'object','properties':{
        '단락':{'type':'array','minItems':1,'items':{'type':'object','properties':{
            '내용':{'type':'string'},'출처ID':{'type':'array','minItems':1,'items':{'type':'string','enum':list(source_ids)}}},
            'required':['내용','출처ID'],'additionalProperties':False}},
        '부족':{'type':'boolean'},'이유':{'type':'string'}},
        'required':['단락','부족','이유'],'additionalProperties':False}
