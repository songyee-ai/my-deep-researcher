"""Bridge the planetary graph to the existing timestamped 3D event viewer."""
import uuid

from graph import PlanetaryResearch
from free_api import safe_api_error


class WebResearch(PlanetaryResearch):
    def call(self, actor, step, prompt, **counts):
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
    value.setdefault('agent', {'report':'crystal'}.get(kind, 'moon'))
    if kind == 'review':
        value['agent'] = f"researcher-{value['section']}"
    value.setdefault('label', {
        'context':'입력량 기록', 'plan':'연구원 배치', 'assignment':'조사 시작',
        'read':'원문 읽기 완료', 'section':'이번 조사 원고', 'candidates':'다음 자료 후보',
        'stop_reading':'읽기 종료', 'report':'보고서 종합',
        'review': ('부족 절 재조사' if value.get('redispatch') else
                   '원고 채택' if value.get('accepted') else '이전 원고 보존'),
    }.get(kind, kind))
    return value
