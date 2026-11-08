"""Bridge the planetary graph to the existing timestamped 3D event viewer."""
import json
import uuid

import pipeline as p

from graph import PlanetaryResearch
from free_api import safe_api_error


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
    return None


class WebResearch(PlanetaryResearch):
    """Web runs use free models without structured output. If the plan fails the
    graph's own validation, the model gets the error and rewrites it once; the
    program never edits the plan itself, and the retry is recorded."""
    _plan_feedback = None

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
        'stop_reading':'읽기 종료', 'report':'보고서 종합', 'plan_retry':'목차 다시 쓰기',
        'review': ('부족 절 재조사' if value.get('redispatch') else
                   '원고 채택' if value.get('accepted') else '이전 원고 보존'),
    }.get(kind, kind))
    return value
