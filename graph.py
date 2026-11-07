"""Planetary LangGraph engine, independent of unchanged course pipeline.py.

The model is injected. Importing/running with a fixture model never reads keys.
No raw source or worker notes are returned to coordinator/synthesis prompts.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import operator
from pathlib import Path
import re
import threading
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
import pipeline as p
from drafts import render_draft
from evidence import validate_note
from cards import document_cards

ROOT = Path(__file__).resolve().parent


class State(TypedDict):
    question: str
    plan: dict
    pending: list[int]
    round: int
    attempts: Annotated[list[dict], operator.add]
    selected: list[dict]
    review: Annotated[list[dict], operator.add]
    report: str


class WorkerInput(TypedDict):
    question: str
    task: dict
    round: int
    previous_reads: list[str]


@dataclass
class PlanetaryResearch:
    corpus: p.Corpus
    model: p.ChatModel
    config: dict
    emit: object = None

    def __post_init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.worker_notes = {}
        if not 1 <= self.config['max_sections'] <= 8:
            raise ValueError('리서처 수는 1~8명이어야 합니다.')
        if not 1 <= self.config['document_budget'] <= 5:
            raise ValueError('문서 예산은 1~5건이어야 합니다.')
        if not 0 <= self.config['max_redispatch_rounds'] <= 3:
            raise ValueError('재조사 상한은 0~3회여야 합니다.')

    def event(self, kind, **values):
        event = {'kind':kind, **values}
        with self.lock:
            self.events.append(event)
        if self.emit:
            self.emit(event)

    def call(self, actor, step, prompt, source_chars=0, card_chars=0, manuscript_chars=0):
        self.event('context', actor=actor, step=step.value,
                   input_chars=len(prompt.system)+len(prompt.user), source_chars=source_chars,
                   card_chars=card_chars, manuscript_chars=manuscript_chars)
        return self.model(step, prompt)

    def build_graph(self):
        g = StateGraph(State)
        g.add_node('plan',self.plan)
        g.add_node('researcher',self.researcher,input_schema=WorkerInput)
        g.add_node('inspect',self.inspect)
        g.add_node('synthesize',self.synthesize)
        g.add_edge(START,'plan')
        g.add_conditional_edges('plan',self.fanout,['researcher','synthesize'])
        g.add_edge('researcher','inspect')
        g.add_conditional_edges('inspect',self.fanout,['researcher','synthesize'])
        g.add_edge('synthesize',END)
        return g.compile()

    def run(self, question):
        if not question.strip():
            raise ValueError('질문을 입력해 주세요.')
        self.events = []
        self.worker_notes = {}
        state = self.build_graph().invoke({'question':question,'plan':{},'pending':[],
                    'round':0,'attempts':[],'selected':[],'review':[],'report':''})
        state['events'] = list(self.events)
        return state

    def plan(self, state):
        roster = self.config['roles']
        cards = self.corpus.cards()
        if self.config.get('planning_cards')=='topic_snippets_v1':
            cards=document_cards(self.corpus,state['question'],self.config.get('planning_term_groups',[]))
        role_instruction=(f'역할 명단: {json.dumps(roster,ensure_ascii=False)}. ' if self.config['switches']['roles'] else '역할은 일반 자료 조사원으로 한다. ')
        seed_instruction=('서로 다른 시작문서를 정확한 이름으로 지정하라. ' if self.config['switches']['seeds'] else '시작문서는 배정하지 말고 빈 문자열로 두어라. ')
        system = ('행성 탐사 연구의 코디네이터다. 제공된 문서 카드만 보고 질문에 답할 목차를 내용 단위로 나눠라. '
                  '형식(개요·연표·분석)으로 나누지 마라. 한 문서로 답하면 한 절만 배정하라. '
                  f"최대 {self.config['max_sections']}개 절. "+seed_instruction+role_instruction+
                  '자료 범위를 벗어나면 {"범위밖":true,"목차":[]}로 답하라. '
                  '그 외 JSON {"제목":"...","목차":[{"절":"...","지시":"...","역할":"명단 이름","시작문서":"정확한 문서명"}]}만 반환하라.')
        reply = p.parse_json_object(self.call('coordinator',p.Step.PLAN,p.Prompt(system,f"질문: {state['question']}\n문서 카드:\n{cards}"),card_chars=len(cards)))
        if reply.get('범위밖') is True:
            return {'plan':{'제목':state['question'],'목차':[],'범위밖':True},'pending':[]}
        items = reply.get('목차')
        if not isinstance(items,list) or not items:
            raise ValueError('기획 응답에 유효한 목차가 없습니다.')
        taken = set(); toc = []
        for i,item in enumerate(items[:self.config['max_sections']]):
            if not isinstance(item,dict) or not item.get('절') or not item.get('지시'):
                raise ValueError('절 제목과 조사 지시를 확인할 수 없습니다.')
            seed = item.get('시작문서','')
            if self.config['switches']['seeds']:
                if seed not in self.corpus.docs or seed in taken:
                    raise ValueError('기획자가 존재하지 않거나 중복된 시작문서를 배정했습니다.')
                taken.add(seed)
            else:
                seed = ''
            role = item.get('역할')
            if self.config['switches']['roles'] and role not in roster:
                raise ValueError('기획자가 명단에 없는 역할을 배정했습니다.')
            toc.append({'번호':i,'절':str(item['절']),'지시':str(item['지시']),
                        '역할':role if self.config['switches']['roles'] else '자료 조사원',
                        '시작문서':seed,'예산':self.config['document_budget']})
        plan = {'제목':str(reply.get('제목') or state['question']),'목차':toc}
        plan = self.finalize_plan(plan,state['question'])
        self.event('plan',plan=plan)
        return {'plan':plan,'pending':list(range(len(toc)))}

    def finalize_plan(self,plan,question):
        return plan

    def fanout(self, state):
        if not state['pending']:
            return 'synthesize'
        sends = []
        for index in state['pending']:
            task = dict(state['plan']['목차'][index])
            others = [t for t in state['plan']['목차'] if t['번호']!=index]
            task['다른구역'] = [{'절':t['절'],'지시':t['지시'],'시작문서':t['시작문서']} for t in others] if self.config['switches']['zones'] else []
            previous = list(dict.fromkeys(doc for s in state['attempts'] if s['번호']==index for doc in s['읽은문서']))
            sends.append(Send('researcher',{'question':state['question'],'task':task,'round':state['round'],'previous_reads':previous}))
        return sends

    def researcher(self, state):
        task = state['task']; actor = f"researcher-{task['번호']}"
        read = list(state['previous_reads'])
        notes = list(self.worker_notes.get(task['번호'],[]))
        self.event('assignment',agent=actor,round=state['round'],task=task)
        avoid = {z['시작문서'] for z in task['다른구역'] if z['시작문서']}
        # Fresh evidence on redispatch. Each attempt gets the same explicit cap.
        used_before = state['previous_reads'] if state['round'] else []
        seed = task['시작문서'] if not used_before else None
        zone = json.dumps(task['다른구역'],ensure_ascii=False)
        duty = self.config['roles'].get(task['역할'],'할당된 내용 구역을 근거 자료로 조사한다')
        brief = f"질문: {state['question']}\n맡은 절: {task['절']}\n역할: {task['역할']} — {duty}\n지시: {task['지시']}\n다른 연구원의 구역(중복 집필 금지): {zone}"
        for _ in range(task['예산']):
            candidates = [x for x in self.corpus.candidates(read,list(avoid)) if x not in read and x not in used_before and x not in avoid]
            if seed:
                doc = seed; seed = None
            else:
                if not candidates:
                    self.event('stop_reading',agent=actor,round=state['round'],reason='candidate_exhausted')
                    break
                linked = any(x in candidates for s in read for x in self.corpus.links.get(s,[]))
                self.event('candidates',agent=actor,round=state['round'],path='links' if linked else 'all_docs_fallback',count=len(candidates))
                choice = p.parse_json_object(self.call(actor,p.Step.PICK,p.Prompt('후보에서 1건 선택해 JSON {"문서":"정확한 문서명"}으로 답하라. 더 읽을 자료가 없으면 {"문서":null}.',brief+'\n읽은 문서: '+json.dumps(read,ensure_ascii=False)+'\n후보: '+json.dumps(candidates,ensure_ascii=False))))
                if '문서' not in choice:raise ValueError('다음 문서 선택 응답이 올바른 JSON이 아닙니다.')
                picked=choice['문서']
                if picked is None:
                    self.event('stop_reading',agent=actor,round=state['round'],reason='model_stop')
                    break
                if picked not in candidates: raise ValueError('후보 밖 문서 선택을 거부했습니다.')
                doc = picked
            text = self.corpus.docs[doc]
            note,evidence=self.read_document(actor,doc,text,brief)
            read.append(doc); notes.append((doc,note))
            self.event('read',agent=actor,round=state['round'],document=doc,source_chars=len(text),
                       evidence=evidence)
        with self.lock:
            self.worker_notes[task['번호']] = list(notes)
        structured=self.config.get('draft_format','legacy')=='source_ids_v1'
        source_map={f'D{i+1}':doc for i,(doc,_) in enumerate(notes)}
        material = ('\n\n'.join(f'출처ID D{i+1}\n문서명 {doc}\n{note}' for i,(doc,note) in enumerate(notes))
                    if structured else '\n\n'.join(f'«{doc}»\n{note}' for doc,note in notes))
        prompt = p.Prompt(f'한국어 연구 원고를 쓰라. {brief}\n아래 자기 조사 노트만 근거로 작성하라. '
                         f"본문은 {self.config['minimum_section_chars']}자 이상이며 사실 문장 바로 뒤에 «문서명» 인용을 붙여라. "
                         '목표·예정과 관측 성과를 구분하라. 자료 부족을 숨기지 마라. '
                         'JSON {"본문":"...","부족":true 또는 false,"이유":"부족한 내용 또는 충분한 이유"}만 반환하라.',material)
        if structured:
            # Sentence range scales with the length target (600 chars -> 6~12, unchanged);
            # a fixed range would cap a single-agent control asked for N×600 chars.
            low=max(6,round(self.config['minimum_section_chars']/100))
            prompt=p.Prompt(f'한국어 연구원이다. {brief}\n자기 조사 노트만 사용하라. 고유명사를 임의로 번역하지 말고 본문과 이유는 한국어로 써라. '
                            f'내용을 구체적인 {low}~{low*2}문장으로 충분히 설명하라. 각 단락의 내용과 명시적인 출처ID 배열을 분리하라. '
                            '내용에 인용 기호를 직접 넣지 마라. 계획·장비의 설계 목적을 실제 관측 성과로 바꾸지 마라. '
                            '근거가 부족하면 부족=true로 신고하고 필요한 자료를 이유에 적어라. '
                            'JSON {"단락":[{"내용":"한국어 설명","출처ID":["D1"]}],"부족":true 또는 false,"이유":"..."}만 반환하라.',material)
        reply = p.parse_json_object(self.call(actor,p.Step.WRITE,prompt))
        raw_draft=reply
        if structured:reply=render_draft(reply,source_map)
        if not isinstance(reply.get('부족'),bool) or not isinstance(reply.get('본문'),str):
            raise ValueError('원고에 본문과 명시적인 부족 신고가 필요합니다.')
        section = {**{k:task[k] for k in ['번호','절','역할']},'round':state['round'],
                   '본문':reply['본문'],'부족':reply['부족'],'이유':str(reply.get('이유','')),
                   '읽은문서':read,'인용':re.findall(r'«([^»]+)»',reply['본문'])}
        section['draft_format']='source_ids_v1' if structured else 'legacy'
        if structured:section.update(raw_draft=raw_draft,source_map=source_map)
        self.event('section',agent=actor,section=section)
        return {'attempts':[section]}

    def read_document(self,actor,doc,text,brief):
        extractive=self.config.get('note_format')=='extractive_v1'
        read_prompt=p.read_prompt(doc,text,brief)
        if extractive:
            read_prompt=p.Prompt('실제 제공 문서만 읽는 조사원이다. 지시에 관련된 원문 구절을 그대로 발췌하고 한국어 메모를 붙여라. '
                '제공되지 않은 지식이나 원인 추측을 추가하지 마라. 목적·예정·실제 성과를 구분하라. '
                '관련 근거가 없거나 지시의 핵심을 답할 수 없으면 부족=true와 필요한 자료를 밝혀라. '
                '원문은 최소 20자이며 생략 기호나 번역 없이 문서와 일치해야 한다. 5개 이내. '
                'JSON {"근거":[{"원문":"문서의 정확한 연속 구절","메모":"해당 구절에서 확인되는 것"}],"부족":true 또는 false,"이유":"..."}만 반환하라.\n'+brief,
                f'[문서: {doc}]\n{text}')
        note = self.call(actor,p.Step.READ,read_prompt,source_chars=len(text))
        if not note.strip(): raise ValueError('빈 조사 노트입니다.')
        evidence=None
        if extractive:
            evidence=validate_note(p.parse_json_object(note),text)
            write_evidence=evidence
            if self.config.get('quotes_only'):
                write_evidence={'근거':[{'원문':item['원문']} for item in evidence['근거']],
                                '부족':evidence['부족'],'검사':'발췌 존재만 확인. 설계 목적과 실제 성과를 구분해 원문에서 답할 수 없는 내용은 추가하지 말 것.'}
            note=json.dumps(write_evidence,ensure_ascii=False)
        return note,evidence

    def valid(self, section):
        return (len(section['본문'])>=self.config['minimum_section_chars'] and bool(section['인용'])
                and set(section['인용'])<=set(section['읽은문서']))

    def inspect(self, state):
        selected = {s['번호']:s for s in state['selected']}; pending = []; reviews = []
        latest = [s for s in state['attempts'] if s['round']==state['round']]
        for section in sorted(latest,key=lambda s:s['번호']):
            index = section['번호']; old = selected.get(index)
            # Preserve a valid first draft if the revision loses valid citations.
            accept = old is None or (self.valid(section) and (not self.valid(old) or len(set(section['인용']))>=len(set(old['인용']))))
            if accept: selected[index] = section
            retry = (section['부족'] and self.config['switches']['redispatch']
                     and state['round']<self.config['max_redispatch_rounds'])
            if retry: pending.append(index)
            review = {'section':index,'round':state['round'],'self_reported_insufficient':section['부족'],
                      'accepted':accept,'valid_draft':self.valid(section),'redispatch':retry,
                      'reason':('valid nonregressing draft' if self.valid(section) else 'provisional draft with validation warnings') if accept else 'kept previous draft; revision lost validity or cited-source breadth'}
            reviews.append(review); self.event('review',**review)
        return {'selected':[selected[i] for i in sorted(selected)],'pending':pending,'round':state['round']+1,'review':reviews}

    def synthesize(self, state):
        if state['plan'].get('범위밖'):
            return {'report':'현재 자료는 수성·금성·화성·목성 무인 탐사에 한정됩니다. 해당 범위의 질문을 입력해 주세요.'}
        sections = state['selected']
        # Coordinator receives manuscripts, not source texts or worker notes.
        outline = '\n\n'.join(f"## {s['절']}\n{s['본문']}" for s in sections)
        reply = p.parse_json_object(self.call('synthesizer',p.Step.EDIT,p.Prompt('절 본문을 고치지 말고 JSON {"머리말":"...","맺음말":"..."}로 각 두 문장 이내를 써라. 절의 부족을 숨기지 말고 새 사실이나 새 인용을 추가하지 마라.',state['question']+'\n'+outline),manuscript_chars=len(outline)))
        body = '\n\n'.join(f"## {s['번호']+1}. {s['절']}\n\n{s['본문']}" for s in sections)
        warnings = [f"{s['절']}: 근거·분량 검토 필요" for s in sections if not self.valid(s) or s['부족']]
        report = f"# {state['plan']['제목']}\n\n{reply.get('머리말','')}\n\n{body}\n\n## 맺음말\n\n{reply.get('맺음말','')}"
        if warnings: report+='\n\n검토 경고:\n'+'\n'.join(warnings)
        self.event('report',report=report,warnings=warnings)
        return {'report':report}


def load_project():
    config = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
    return p.Corpus.load(ROOT/config['corpus_dir']), config
