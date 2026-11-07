"""Optional CLI adapter and fact-table reading hook for the existing graph."""
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

import pipeline as p
from graph import PlanetaryResearch
from baseline import SingleAgentResearch
from codex_cli_bridge import generate
from drafts import draft_schema
from structured_facts import fact_schema,fact_prompt,validate_facts


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


# P04 review (output/engineering_runs/20261106-224622/INSUFFICIENCY_REVIEW.md): sub-item
# gaps (unstated angles, areas) were reported as whole-section insufficiency, so a
# redispatch round was spent on facts the corpus does not contain.
INSUFFICIENCY_RULE=('부족=true는 질문에 답할 핵심 근거가 자기 자료에 없을 때만 신고하라. '
                    '질문이 묻지 않은 세부 수치가 없다는 이유만으로 부족=true로 하지 말고, 그런 한계는 이유에 적어라.')


def codex_model_identity(model):
    return {'transport':'codex_cli','model':model,'reasoning_effort':'medium',
            'read_policy':'fact_table_atomic_v3','insufficiency_policy':'question_scope_v1',
            'read_validation_repairs':1,'output_contract':'step_schema_v1',
            'automatic_retries':0,'authentication':'ChatGPT login'}


class CodexGraphModel:
    def __init__(self,corpus,config,folder,model):
        self.corpus=corpus;self.config=config;self.folder=Path(folder)
        self.folder.mkdir(parents=True,exist_ok=True)
        self.model_identity=codex_model_identity(model)
        self.lock=threading.Lock();self.calls={}
        self.transport_stats={'cache_hits':0,'cli_invocations':0}
        checkpoint=self.folder/'calls.json'
        if checkpoint.exists():
            previous=json.loads(checkpoint.read_text(encoding='utf-8'))
            if previous.get('model_identity')!=self.model_identity:raise ValueError('CLI 재개 모델 설정이 다릅니다.')
            self.calls=previous['calls']

    def schema(self,step,prompt):
        if step==p.Step.PLAN:
            item=object_schema({'절':{'type':'string'},'지시':{'type':'string'},
                '역할':{'type':'string','enum':list(self.config['roles']) if self.config['switches']['roles'] else ['자료 조사원']},
                '시작문서':{'type':'string','enum':list(self.corpus.docs) if self.config['switches']['seeds'] else ['']}})
            return object_schema({'제목':{'type':'string'},'목차':{'type':'array','maxItems':self.config['max_sections'],'items':item},'범위밖':{'type':'boolean'}})
        if step==p.Step.READ:
            line_numbers=re.findall(r'^L(\d+):',prompt.user,flags=re.M)
            if not line_numbers:raise ValueError('CLI 조사에는 줄 번호가 있는 사실표 입력이 필요합니다.')
            return fact_schema(max(map(int,line_numbers)))
        if step==p.Step.PICK:
            candidates=json.loads(prompt.user.rsplit('\n후보: ',1)[1])
            return object_schema({'문서':{'type':['string','null'],'enum':candidates+[None]}})
        if step==p.Step.WRITE:
            ids=list(dict.fromkeys(re.findall(r'출처ID (D\d+)',prompt.user)))
            if not ids:raise ValueError('조사 자료 없이 원고 출처를 만들지 않습니다.')
            return draft_schema(ids)
        if step==p.Step.EDIT:return object_schema({'머리말':{'type':'string'},'맺음말':{'type':'string'}})
        raise ValueError('지원하지 않는 그래프 단계입니다.')

    def __call__(self,step,prompt):
        if step==p.Step.PLAN:
            prompt=p.Prompt(prompt.system+'\n각 절은 자기 자료로 답할 내용 구역을 맡겨라. 다른 연구원의 시작 자료를 읽어야만 수행할 수 있는 교차 의존 지시는 피하라. 같은 비교 축으로 각 대상의 근거를 정리하게 하되 타 구역 집필을 중복시키지 마라.'
                            '\n지시에는 질문이 실제로 묻는 범위만 넣어라. 질문에 없는 정량값(각도·면적·시간 등)을 필수 항목으로 요구하지 마라.',prompt.user)
        schema=self.schema(step,prompt)
        if step==p.Step.WRITE:
            prompt=p.Prompt(prompt.system+f"\n본문은 {self.config['minimum_section_chars']}자 이상을 목표로 작성하되 근거 부족을 숨기지 마라. 주체·비교 대상·수치 기준을 사실표와 동일하게 보존하라.\n"+INSUFFICIENCY_RULE,prompt.user)
        fingerprint=hashlib.sha256(json.dumps([self.model_identity,step.value,prompt.system,prompt.user,schema],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with self.lock:
            if fingerprint in self.calls:
                self.transport_stats['cache_hits']+=1
                return self.calls[fingerprint]['response']
            self.transport_stats['cli_invocations']+=1
        call_folder=self.folder/'cli_calls'/f'{step.value}-{uuid.uuid4().hex}'
        parsed,transport=generate(prompt,schema,call_folder,self.model_identity['model'])
        answer=json.dumps(parsed,ensure_ascii=False)
        with self.lock:
            self.calls[fingerprint]={'step':step.value,'system':prompt.system,'user':prompt.user,
                'response':answer,'transport':transport,'artifact':str(call_folder.relative_to(self.folder))}
            target=self.folder/'calls.json';temporary=self.folder/'calls.tmp'
            temporary.write_text(json.dumps({'model_identity':self.model_identity,'calls':self.calls},ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(target)
        return answer


class FactTableReading:
    """The researcher keeps the table; the coordinator still gets manuscripts only."""
    def read_document(self,actor,doc,text,brief):
        prompt=fact_prompt(brief,doc,text)
        prompt=p.Prompt(prompt.system+'\n맡은 절과 다른 연구원의 구역이 지정돼 있으면 부족 신고는 자기 절의 지시 범위로 판단하라. 다른 연구원이 맡은 자료가 자기 입력에 없다는 사실만으로 자기 절을 부족하다고 신고하지 마라.\n'+INSUFFICIENCY_RULE,prompt.user)
        parsed=p.parse_json_object(self.call(actor,p.Step.READ,prompt,source_chars=len(text)))
        try:table=validate_facts(parsed,doc,text)
        except ValueError as exc:
            # One explicit model correction, never a programmatic rewrite of facts.
            # Both source-bearing calls count in context/transport traces; logical
            # document budget counts the document once after successful validation.
            self.event('fact_validation_error',agent=actor,document=doc,error=str(exc),repair_limit=1)
            repair=p.Prompt(prompt.system+'\n이전 응답이 계약 검사에 실패했다: '+str(exc)+
                '\n동일 원문을 다시 읽고 정확한 원문 표현과 줄 범위를 선택해 완전한 사실표 하나를 다시 반환하라. 값을 추측하거나 검사를 생략하지 마라.',prompt.user)
            parsed=p.parse_json_object(self.call(actor,p.Step.READ,repair,source_chars=len(text)))
            table=validate_facts(parsed,doc,text)
        evidence={'근거':[{'원문':row['quote'],'메모':json.dumps({k:row[k] for k in ('subject','relation','comparison_target','value','unit','basis')},ensure_ascii=False)} for row in table['facts']],
                  '부족':table['insufficient'],'이유':table['reason'],'fact_table':table,
                  'validation':'Schema/source membership checked; semantic support pending direct review.'}
        self.event('fact_table',agent=actor,document=doc,table=table)
        return json.dumps(evidence,ensure_ascii=False),evidence


class CodexResearch(FactTableReading,PlanetaryResearch):
    pass


class CodexSingleAgentResearch(FactTableReading,SingleAgentResearch):
    """Single-agent control: same fact-table READ, same tools, explicit total budget."""
    pass


def codex_settings(config,topic_cards=True):
    """run_planetary.py's --transport codex settings plus draft_format; topic cards on by
    default (run_planetary needs --topic-cards). Applied identically to every condition."""
    settings=copy.deepcopy(config)
    settings.update(model_transport='codex_cli',note_format='fact_table_v1',quotes_only=False,draft_format='source_ids_v1')
    if topic_cards:settings['planning_cards']='topic_snippets_v1'
    return settings


def plan_schema_alignment(model,engine,condition=None):
    """Compare the PLAN schema the CLI actually receives with what the condition requires.

    With a condition name the expectations come from the condition, not from the same
    config the schema reads, so the roles/seeds checks can actually fail.
    """
    schema=model.schema(p.Step.PLAN,p.Prompt('',''))
    items=schema['properties']['목차']
    item=items['items']['properties']
    config=engine.config
    if condition is None:
        roles_on=config['switches']['roles'];seeds_on=config['switches']['seeds'];sections=config['max_sections']
    else:
        roles_on=condition not in ('no_roles','single_agent');seeds_on=condition!='no_seeds'
        sections=1 if condition=='single_agent' else engine.config['max_sections']
    expected_roles=list(config['roles']) if roles_on else ['자료 조사원']
    expected_seeds=list(engine.corpus.docs) if seeds_on else ['']
    checks={'shares_engine_config':model.config is config,
            'max_sections':items['maxItems']==sections,
            'roles':item['역할']['enum']==expected_roles,
            'seeds':item['시작문서']['enum']==expected_seeds}
    return {'aligned':all(checks.values()),'checks':checks,'max_sections':items['maxItems'],
            'roles_enabled':item['역할']['enum']!=['자료 조사원'],'seeds_enabled':item['시작문서']['enum']!=['']}


def codex_engine_factory(model_name,call_root):
    """Build engine first, then a fresh CLI model bound to that engine's effective config.

    SingleAgentResearch rewrites max_sections/switches in __init__, so a model built
    from the base config would hand the CLI a schema that disagrees with the run.
    Every run gets its own never-used call folder: no cache or notes cross conditions.
    """
    root=Path(call_root)

    def build(corpus,condition,settings,grant,target_chars,identifier):
        folder=root/identifier
        if folder.exists():raise ValueError(f'CLI 호출 폴더가 이미 있습니다: {identifier}. 조건 간 캐시를 공유하지 않습니다.')
        if condition=='single_agent':
            engine=CodexSingleAgentResearch(corpus,None,settings,grant,target_chars)
        else:engine=CodexResearch(corpus,None,settings)
        engine.model=CodexGraphModel(corpus,engine.config,folder,model_name)
        alignment=plan_schema_alignment(engine.model,engine,condition)
        if not alignment['aligned']:raise ValueError(f'조건 {condition}의 CLI 스키마가 실제 설정과 다릅니다: {alignment}')
        return engine,{'plan_schema_alignment':alignment,'call_folder':str(folder),'read_policy':engine.model.model_identity['read_policy']}
    return build
