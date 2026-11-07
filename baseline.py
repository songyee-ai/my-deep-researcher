"""Single-agent comparison with the same source tools and explicit total budget."""
import copy
from graph import PlanetaryResearch


def shared_budget(config):
    """Reserve every configured slot and redispatch round before seeing output."""
    return config['max_sections']*config['document_budget']*(1+config['max_redispatch_rounds'])


class SingleAgentResearch(PlanetaryResearch):
    def __init__(self,corpus,model,config,read_budget,target_chars,emit=None):
        if not isinstance(read_budget,int) or not 1<=read_budget<=160:
            raise ValueError('Invalid shared document budget')
        self.read_budget=read_budget
        settings=copy.deepcopy(config)
        settings.update(max_sections=1,max_redispatch_rounds=0,minimum_section_chars=target_chars)
        settings['switches'].update(roles=False,zones=False,redispatch=False)
        super().__init__(corpus,model,settings,emit)

    def finalize_plan(self,plan,question):
        for task in plan['목차']:
            task['절']='전체 질문 조사'
            task['지시']=question+' — 질문 전체를 맡아 내용별 소제목을 포함한 장문 보고서를 작성한다.'
            task['예산']=self.read_budget
        return plan

    def run(self,question):
        result=super().run(question)
        used=sum(e['kind']=='read' for e in result['events'])
        result['baseline_validation']={'granted_read_budget':self.read_budget,'actual_reads':used,
            'full_budget_used':used==self.read_budget,'unused_budget':max(0,self.read_budget-used),
            'status':'budget_consumed' if used==self.read_budget else 'UNDERUSED_DO_NOT_CLAIM_MULTIAGENT_WIN',
            'stopping_reasons':[e['reason'] for e in result['events'] if e['kind']=='stop_reading'],
            'note':'Uses the same read/pick/write/synthesis tools. Early stopping or corpus exhaustion is visible; an underused baseline cannot support a win claim.'}
        return result
