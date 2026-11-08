"""Bridge the planetary graph to the existing timestamped 3D event viewer."""
import json
import re
import threading
import uuid

import pipeline as p

from graph import PlanetaryResearch
from free_api import safe_api_error
from drafts import draft_schema


# Plan validation failures that a rewrite can fix (format, not model outage).
PLAN_FORMAT_ERRORS = ('기획 응답에 유효한 목차가 없습니다', '절 제목과 조사 지시를',
                      '기획자가 존재하지 않거나 중복된 시작문서', '기획자가 명단에 없는 역할')


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def web_schema(engine, step, prompt):
    """Constrain choices the graph validates: real documents, listed roles, real candidates."""
    config = engine.config
    if step == p.Step.PLAN:
        item = _object({'절': {'type': 'string'}, '지시': {'type': 'string'},
            '역할': {'type': 'string', 'enum': list(config['roles']) if config['switches']['roles'] else ['자료 조사원']},
            '시작문서': {'type': 'string', 'enum': list(engine.corpus.docs) if config['switches']['seeds'] else ['']}})
        return _object({'제목': {'type': 'string'}, '범위밖': {'type': 'boolean'},
                        '목차': {'type': 'array', 'maxItems': config['max_sections'], 'items': item}})
    if step == p.Step.PICK and '\n후보: ' in prompt.user:
        candidates = json.loads(prompt.user.rsplit('\n후보: ', 1)[1])
        return _object({'문서': {'type': ['string', 'null'], 'enum': candidates + [None]}})
    if step == p.Step.READ and config.get('note_format') == 'extractive_v1':
        quote = _object({'원문': {'type': 'string'}, '메모': {'type': 'string'}})
        return _object({'근거': {'type': 'array', 'maxItems': 5, 'items': quote},
                        '부족': {'type': 'boolean'}, '이유': {'type': 'string'}})
    if step == p.Step.WRITE and config.get('draft_format') == 'source_ids_v1':
        ids = list(dict.fromkeys(re.findall(r'출처ID (D\d+)', prompt.user)))
        return draft_schema(ids) if ids else None
    if step == p.Step.EDIT:
        return _object({'머리말': {'type': 'string'}, '맺음말': {'type': 'string'}})
    return None


class WebResearch(PlanetaryResearch):
    """Web runs use free models without structured output. If the plan fails the
    graph's own validation, the model gets the error and rewrites it once; the
    program never edits the plan itself, and the retry is recorded."""
    _plan_feedback = None
    READ_REPAIR = (' 원문은 위 문서에 실제로 있는 연속 구절을 한 글자도 바꾸지 말고 그대로 복사하라. '
                   '다른 문서나 배경지식의 문장을 원문으로 쓰지 마라. 확실한 구절이 없으면 근거를 줄이고 부족=true로 신고하라. '
                   '완전한 JSON 하나만 반환하라.')

    def read_document(self, actor, doc, text, brief):
        # Researchers run in parallel; one bad note must not stop the others.
        # The model rereads once with the error. A second failure drops that
        # document's evidence (never the check) and is recorded.
        try:
            return super().read_document(actor, doc, text, brief)
        except ValueError as exc:
            self.event('read_retry', agent=actor, document=doc, reason=str(exc), limit=1)
            self._feedback(actor, str(exc))
            try:
                return super().read_document(actor, doc, text, brief)
            except ValueError as again:
                reason = '원문 발췌 검증에 두 번 실패해 이 문서의 근거를 쓰지 않았다: ' + str(again)
                self.event('read_rejected', agent=actor, document=doc, reason=str(again))
                evidence = {'근거': [], '부족': True, '이유': reason, 'validation': 'rejected_after_one_repair'}
                return json.dumps({'근거': [], '부족': True, '이유': reason}, ensure_ascii=False), evidence
            finally:
                self._feedback(actor, None)

    def _feedback(self, actor, value):
        with self._feedback_lock:
            if value is None:
                self._read_feedback.pop(actor, None)
            else:
                self._read_feedback[actor] = value

    def __post_init__(self):
        super().__post_init__()
        self._read_feedback = {}
        self._feedback_lock = threading.Lock()

    def plan(self, state):
        try:
            return super().plan(state)
        except ValueError as exc:
            if not str(exc).startswith(PLAN_FORMAT_ERRORS):
                raise
            self.event('plan_retry', agent='moon', reason=str(exc), limit=1)
            self._plan_feedback = str(exc)
            try:
                return super().plan(state)
            finally:
                self._plan_feedback = None

    def call(self, actor, step, prompt, **counts):
        if step == p.Step.READ and self._read_feedback.get(actor):
            prompt = p.Prompt(prompt.system + chr(10) + '이전 응답이 검사에서 거부됐다: ' +
                              self._read_feedback[actor] + self.READ_REPAIR, prompt.user)
        if step == p.Step.PLAN and self._plan_feedback:
            prompt = p.Prompt(prompt.system + chr(10) + '이전 응답이 검사에서 거부됐다: ' + self._plan_feedback +
                              ' 시작문서는 문서 카드 줄의 제목 부분만 그대로 쓰고 "[관련 용어: ...]" 같은 표시는 넣지 마라. '
                              '역할은 명단의 이름 하나만 정확히 쓴다. 절마다 서로 다른 시작문서를 쓴다. 완전한 JSON을 다시 반환하라.',
                              prompt.user)
        agent = {'coordinator': 'moon', 'synthesizer': 'crystal'}.get(actor, actor)
        call_id = uuid.uuid4().hex[:12]
        fields = dict(agent=agent, step=step.value, call_id=call_id,
                      label={'plan':'목차 짜기','read':'문서 읽기','pick':'다음 자료 고르기',
                             'write':'원고 쓰기','edit':'보고서 엮기'}[step.value])
        self.emit(dict(kind='call_start', **fields, system=prompt.system, user=prompt.user,
                       input_chars=len(prompt.system)+len(prompt.user), sent_user_chars=len(prompt.user)))
        try:
            answer = super().call(actor, step, prompt, **counts)
        except Exception as exc:
            self.emit(dict(kind='call_error', **fields, error=safe_api_error(exc)))
            raise
        self.emit(dict(kind='call_end', **fields, response=answer, output_chars=len(answer)))
        return answer


def display_event(event):
    """Keep graph events, adding viewer labels without changing their meaning."""
    value = dict(event)
    kind = value['kind']
    if 'agent' not in value and value.get('actor'):
        value['agent'] = {'coordinator': 'moon', 'synthesizer': 'crystal'}.get(value['actor'], value['actor'])
    value.setdefault('agent', {'report':'crystal'}.get(kind, 'moon'))
    if kind == 'review':
        value['agent'] = f"researcher-{value['section']}"
    value.setdefault('label', {
        'context':'입력량 기록', 'plan':'연구원 배치', 'assignment':'조사 시작',
        'read':'원문 읽기 완료', 'section':'이번 조사 원고', 'candidates':'다음 자료 후보',
        'stop_reading':'읽기 종료', 'report':'보고서 종합', 'plan_retry':'목차 다시 쓰기', 'read_retry':'원문 다시 읽기', 'read_rejected':'발췌 검증 실패 · 근거 제외',
        'review': ('부족 절 재조사' if value.get('redispatch') else
                   '원고 채택' if value.get('accepted') else '이전 원고 보존'),
    }.get(kind, kind))
    return value
