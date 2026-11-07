"""Strict fact-table contract. Mechanical checks never certify semantic support."""
import pipeline as p
from grounded_drafts import numeric_tokens

FIELDS=('subject','relation','comparison_target','value','unit','basis')


def fact_schema(line_count=None):
    fields={name:{'type':'string'} for name in FIELDS}
    for name in ('subject','relation','basis'):fields[name]['minLength']=1
    bounds={'type':'integer','minimum':1}
    if line_count is not None:
        if type(line_count) is not int or line_count<1:raise ValueError('원문 줄 수가 올바르지 않습니다.')
        bounds['maximum']=line_count
    fields.update(start_line=dict(bounds),end_line=dict(bounds))
    return {'type':'object','properties':{
        'facts':{'type':'array','maxItems':8,'items':{'type':'object','properties':fields,
                 'required':list(fields),'additionalProperties':False}},
        'insufficient':{'type':'boolean'},'reason':{'type':'string'}},
        'required':['facts','insufficient','reason'],'additionalProperties':False}


def fact_prompt(question,title,source):
    return p.Prompt(
        '제공된 원문만 읽고 질문에 필요한 사실을 최대 8행의 표로 추출하라. 아직 원고를 쓰지 마라. '
        'subject는 사실의 주체, relation은 관계/특성, comparison_target은 비교 대상, value는 수치 표현, '
        'unit은 단위, basis는 비율의 기준/분모/설계목표·실제결과 구분이다. '
        '원문에 없는 값은 추정하지 말고 빈 문자열로 둔다. 숫자가 없는 사실도 기록할 수 있다. '
        '주체·비교대상·수치·단위는 원문 영어 표현을 그대로 쓰고 relation/basis/reason은 한국어로 쓴다. '
        '각 행은 하나의 사실과 하나의 연속된 수치 표현만 담아라. 떨어진 두 수치를 세미콜론 등으로 합치지 말고 별도 행으로 분리하라. '
        '선택 줄에 주체 이름이 없다면 이름이 나오는 앞뒤 문맥까지 포함하라. relation과 basis에 다른 언어 설명을 섞지 마라. '
        'subject에는 문서 제목의 임무명을 반복하기보다 선택 줄에 실제 쓰인 명사구나 대명사를 그대로 적어도 된다. 문서명은 별도로 보존된다. '
        '수치와 그 수치의 주체를 포함하는 시작/끝 줄을 선택하라. 다른 장비의 정보로 질문 대상의 성과를 대신하지 마라. '
        '필요한 사실이 빠지면 insufficient=true로 누락된 항목을 reason에 명시하라. '
        '반드시 지정된 JSON Schema 객체 하나만 반환하라.',
        f'질문: {question}\n문서: {title}\n'+'\n'.join(f'L{i}: {line}' for i,line in enumerate(source.splitlines(),1)))


def validate_facts(reply,title,source):
    if not isinstance(reply,dict) or set(reply)!={'facts','insufficient','reason'}:
        raise ValueError('사실표 루트 필드가 스키마와 다릅니다.')
    if type(reply['insufficient']) is not bool or not isinstance(reply['reason'],str):
        raise ValueError('명시적인 부족 신고와 이유가 필요합니다.')
    if reply['insufficient'] and not reply['reason'].strip():
        raise ValueError('부족하다고 신고할 때 누락된 정보의 이유가 필요합니다.')
    if not isinstance(reply['facts'],list) or len(reply['facts'])>8:
        raise ValueError('사실표는 최대 8행이어야 합니다.')
    if not reply['facts'] and not reply['insufficient']:
        raise ValueError('빈 사실표로 충분하다고 신고할 수 없습니다.')
    lines=source.splitlines();verified=[]
    for index,row in enumerate(reply['facts'],1):
        if not isinstance(row,dict) or set(row)!=set(FIELDS)|{'start_line','end_line'}:
            raise ValueError('사실표 행 필드가 스키마와 다릅니다.')
        if any(not isinstance(row[k],str) for k in FIELDS):raise ValueError('사실 필드는 문자열이어야 합니다.')
        if any(not row[k].strip() for k in ('subject','relation','basis')):
            raise ValueError('주체·관계·비교 기준은 비워 둘 수 없습니다.')
        start,end=row['start_line'],row['end_line']
        if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines):
            raise ValueError('원문에 없는 줄 범위입니다.')
        quote='\n'.join(lines[start-1:end])
        if numeric_tokens(row['value'])-numeric_tokens(quote):
            raise ValueError('선택한 근거에 없는 수치를 거부했습니다.')
        for field in ('subject','comparison_target','value','unit'):
            # This contract explicitly asks for verbatim source expressions.
            normalized=' '.join(row[field].split())
            if normalized and normalized not in ' '.join(quote.split()):
                raise ValueError(f'선택한 원문에 없는 {field} 표현입니다.')
        verified.append({'id':f'F{index}',**row,'document':title,'quote':quote})
    return {'facts':verified,'insufficient':reply['insufficient'],'reason':reply['reason'],
            'semantic_review':'pending','validation_scope':'Schema, source expressions, line bounds, numeric membership only. Attribution/basis needs direct review.'}


def facts_markdown(table):
    def cell(value):return str(value).replace('|','\\|').replace('\n','<br>')
    lines=['# 원문 기반 사실표 · 의미 검토 필요','','| ID | 주체 | 관계 | 비교 대상 | 수치 | 단위 | 기준 | 근거 줄 |',
           '|---|---|---|---|---|---|---|---|']
    for row in table['facts']:
        lines.append('| '+' | '.join(cell(row[k]) for k in ('id',*FIELDS))+f" | {row['start_line']}–{row['end_line']} |")
    lines+=['',f"부족 신고: {table['insufficient']} · {table['reason']}",'']
    for row in table['facts']:lines += [f"## {row['id']} 실제 원문",'',row['quote'],'']
    return '\n'.join(lines)
