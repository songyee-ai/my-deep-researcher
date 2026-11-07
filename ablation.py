"""Paired experiment harness. Model factory is injected; never loads credentials."""
import copy
import hashlib
import json
import re
from pathlib import Path

from baseline import SingleAgentResearch,shared_budget
from graph import PlanetaryResearch
from metrics import measure

CONDITIONS={'basic':None,'no_roles':'roles','no_seeds':'seeds','no_zones':'zones','no_redispatch':'redispatch','single_agent':None}


def corpus_fingerprint(corpus):
    return hashlib.sha256(json.dumps({'docs':corpus.docs,'links':corpus.links},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def default_engine_factory(model_factory):
    """Original behaviour: general READ prompt, one fresh model object per run."""
    def build(corpus,condition,settings,grant,target_chars,identifier):
        model=model_factory()
        if condition=='single_agent':engine=SingleAgentResearch(corpus,model,settings,grant,target_chars)
        else:engine=PlanetaryResearch(corpus,model,settings)
        return engine,{}
    return build


def load_previous_rows(output,model_identity,fingerprint,grant):
    """Rows from an interrupted run of the same experiment; refuse any other experiment."""
    rows=[]
    for line in (output/'runs.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        row=json.loads(line)
        if (row.get('model_identity')!=model_identity or row.get('corpus_sha256')!=fingerprint
                or row.get('shared_read_budget')!=grant):
            raise ValueError('Resume must use the same model, corpus and read ceiling as the stored rows')
        rows.append(row)
    return rows


def run_experiments(corpus,config,questions,model_factory,model_identity,output_dir,repeats=3,synthetic=False,
                    engine_factory=None,conditions=None,resume=False,abort_on=()):
    """abort_on: exception types after which every later call would fail as well
    (e.g. a subscription usage limit). The run stops there and can be resumed;
    completed rows are reused, unfinished ones re-run in a fresh call folder."""
    if not isinstance(repeats,int) or repeats<2:
        raise ValueError('Repeat at least twice; one run is not a direction-of-effect experiment')
    selected=list(CONDITIONS) if conditions is None else list(conditions)
    if not selected or selected[0]!='basic' or len(set(selected))!=len(selected) or any(c not in CONDITIONS for c in selected):
        raise ValueError('Conditions must be unique known names starting with basic (it sets the length anchor)')
    if engine_factory is None:
        if model_factory is None:raise ValueError('Provide model_factory or engine_factory')
        engine_factory=default_engine_factory(model_factory)
    ids=[q['id'] for q in questions]
    if len(set(ids))!=len(ids) or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',qid) for qid in ids):
        raise ValueError('Question IDs must be unique, safe filename components')
    output=Path(output_dir)
    output.mkdir(parents=True,exist_ok=True)
    grant=shared_budget(config)
    fingerprint=corpus_fingerprint(corpus)
    previous=[]
    if (output/'runs.jsonl').exists():
        if not resume:raise ValueError('Use a new output directory; existing experiment records are preserved')
        previous=load_previous_rows(output,model_identity,fingerprint,grant)
    done={row['id']:row for row in previous if row.get('status')=='complete'}
    attempts={}
    for row in previous:attempts[row['id']]=attempts.get(row['id'],0)+1
    records=[];stop=None
    for question_item in questions:
        if stop:break
        for repeat in range(repeats):
            if stop:break
            # Basic establishes a length target, never a gold answer. Rotate the
            # other conditions to reduce a fixed last-position baseline effect.
            others=[(c,CONDITIONS[c]) for c in selected[1:]]
            shift=repeat%len(others) if others else 0
            ordered=[('basic',None)]+others[shift:]+others[:shift]
            basic_sections=None
            for condition,switch in ordered:
                settings=copy.deepcopy(config)
                if switch:settings['switches'][switch]=False
                identifier=f"{question_item['id']}-r{repeat+1}-{condition}"
                if identifier in done:
                    row=done[identifier];records.append(row)
                    if condition=='basic':
                        basic_sections=row.get('plan_sections') or len(json.loads(
                            (output/'reports'/f'{identifier}.json').read_text(encoding='utf-8'))['plan']['목차'])
                    continue
                attempt=attempts.get(identifier,0)+1
                call_id=identifier if attempt==1 else f'{identifier}-a{attempt}'
                target_chars=config['minimum_section_chars']*(basic_sections or config['max_sections'])
                engine,wiring=engine_factory(corpus,condition,settings,grant,target_chars,call_id)
                model=engine.model
                if getattr(model,'model_identity',None)!=model_identity:
                    raise ValueError('Every condition must use the declared identical model and generation settings')
                folder=output/'reports';folder.mkdir(exist_ok=True)
                record={'id':identifier,'question_id':question_item['id'],'question':question_item['question'],
                        'repeat':repeat+1,'condition':condition,'model_identity':model_identity,
                        'corpus_sha256':fingerprint,'shared_read_budget':grant,
                        'synthetic_control_flow_only':synthetic,'condition_settings':settings,
                        'effective_settings':engine.config,
                        'paired_basic_sections':basic_sections,
                        'basic_length_anchor_available':condition=='basic' or basic_sections is not None,
                        'baseline_task_budget_override':grant if condition=='single_agent' else None,
                        'engine_class':type(engine).__name__,'wiring':wiring,'attempt':attempt}
                try:
                    result=engine.run(question_item['question'])
                    if condition=='basic':basic_sections=len(result['plan']['목차'])
                    metrics=measure(result,corpus,engine.config,grant)
                    record.update(status='complete',metrics=metrics,plan_sections=len(result['plan']['목차']),baseline_validation=result.get('baseline_validation'),
                                  mechanical_alarms_clear=not any(metrics['alarms_expected_zero'].values()),
                                  scope_accepted=not result['plan'].get('범위밖',False),human_review_status='pending')
                    (folder/f'{identifier}.md').write_text(result['report'],encoding='utf-8')
                    (folder/f'{identifier}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                except Exception as exc:
                    # Errors can include provider internals; retain type only.
                    record.update(status='error',error_type=type(exc).__name__)
                    if abort_on and isinstance(exc,abort_on):
                        record['status']='aborted'
                        stop={'after':identifier,'error_type':type(exc).__name__,'message':str(exc)[:300]}
                stats=getattr(model,'transport_stats',None)
                if stats is not None:record['transport_stats']=dict(stats)
                records.append(record)
                with (output/'runs.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                if stop:break
    result={'scope':'SYNTHETIC_CONTROL_FLOW_ONLY' if synthetic else 'ACTUAL_MODEL_EXPERIMENTS',
            'stopped_early':stop,'resumed':bool(previous),
            'model_identity':model_identity,'corpus_sha256':fingerprint,'repeats':repeats,
            'shared_read_budget':grant,'conditions':selected,'records':records,
            'ranking':None,'human_review_required':True,
            'comparison_note':'Same corpus/model/tools/read ceiling. Check baseline full-budget use and actual input/output lengths before interpreting differences. Configured retry capacity remains in the common ceiling when retry is disabled.'}
    (output/'ablation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
