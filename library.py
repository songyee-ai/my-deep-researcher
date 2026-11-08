"""Read-only public corpus and engineering records for the local demo."""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data/planetary_exploration'
ENGINEERING=ROOT/'output/engineering_runs'


def read_json(path):return json.loads(path.read_text(encoding='utf-8'))


CORPUS_LABELS={'base':'기본 자료','expanded':'정식 비교 자료'}


def corpus_folder(identifier):
    # Clients select an allowlisted name, never a filesystem path.
    if identifier=='base':return DATA
    if identifier=='expanded':return DATA/'versions/engineering-v2'
    raise ValueError('허용된 자료 모음이 아닙니다.')


def comparison_corpus(manifest):
    path=manifest.get('corpus_dir') or (manifest.get('base_config') or {}).get('corpus_dir')
    if not isinstance(path,str):return None
    return {'data/planetary_exploration':'base',
            'data/planetary_exploration/versions/engineering-v2':'expanded'}.get(path.replace('\\','/'))


def corpus_index(identifier='base'):
    folder=corpus_folder(identifier)
    corpus=read_json(folder/'corpus.json')
    stats=read_json(folder/'statistics.json')
    questions=read_json(folder/'questions.json')['questions']
    corpora=[]
    for key,label in CORPUS_LABELS.items():
        path=corpus_folder(key)
        if not (path/'corpus.json').is_file():continue
        measured=read_json(path/'statistics.json')
        corpora.append({'id':key,'label':label,'document_count':measured['document_count']})
    return {'documents':[{'title':title,'planet':m['planet'],'chars':m['chars'],'pages':m.get('pdf_pages'),
                         'type':m['document_type']} for title,m in corpus['metadata'].items()],
            'questions':questions,'document_count':len(corpus['docs']),'characters':stats['total_characters'],
            'links':stats['directed_edges'],'read_only':True,
            'corpus_id':identifier,'corpus_label':CORPUS_LABELS[identifier],'corpora':corpora}


def document(title,identifier='base'):
    corpus=read_json(corpus_folder(identifier)/'corpus.json')
    if title not in corpus['docs']:raise ValueError('자료 목록에 없는 문서입니다.')
    m=corpus['metadata'][title]
    return {'title':title,'body':corpus['docs'][title],'planet':m['planet'],'source_url':m['final_url'],
            'published_at':m.get('published_at') or m.get('publication_date_label'),
            'collected_at':m['retrieved_at'],'pages':m.get('pdf_pages'),'chars':m['chars'],
            'links':corpus['links'][title],'corpus_id':identifier,'corpus_label':CORPUS_LABELS[identifier]}


def run_path(identifier):
    if not isinstance(identifier,str) or not re.fullmatch(r'\d{8}-\d{6}',identifier):
        raise ValueError('올바른 기록 ID가 아닙니다.')
    path=ENGINEERING/identifier/'run.json'
    if not path.is_file():raise ValueError('실행 기록을 찾지 못했습니다.')
    return path


def run_summary(identifier,record):
    alarms=record.get('metrics',{}).get('alarms_expected_zero',{})
    quality=('내용 검토 미통과' if any(alarms.values()) else '내용 검토 필요') if record['status']=='complete' else '실행 미완료'
    return {'id':identifier,'status':record['status'],'question':record['question'],
            'model':record.get('requested_model') or record.get('model_identity',{}).get('model'),
            'http_status':record.get('http_status'),'report_chars':len(record.get('result',{}).get('report','')),
            'quality_status':quality}


def engineering_index():
    result=[]
    for path in sorted(ENGINEERING.glob('*/run.json'),reverse=True):
        if not re.fullmatch(r'\d{8}-\d{6}',path.parent.name):continue
        try:result.append(run_summary(path.parent.name,read_json(path)))
        except (OSError,ValueError,KeyError):continue
    return result


def engineering_detail(identifier):
    path=run_path(identifier);record=read_json(path)
    calls_path=path.with_name('calls.json')
    calls=list(read_json(calls_path).get('calls',{}).values()) if calls_path.exists() else []
    result=record.get('result',{})
    sections=[]
    for section in result.get('selected',[]):
        trace=[{k:c.get(k) for k in ['step','system','user','response']} for c in calls
               if c['step'] in ['read','write','pick'] and
               (f"맡은 절: {section['절']}" in c['system'] or f"맡은 절: {section['절']}" in c['user'])]
        sections.append({'index':section['번호'],'title':section['절'],'role':section['역할'],
                         'body':section['본문'],'read_documents':section['읽은문서'],
                         'insufficient':section['부족'],'reason':section['이유'],'round':section['round'],
                         'trace':trace})
    return {**run_summary(identifier,record),'scope':'기능 진단 · 정식 성능 비교 아님',
            'context_gate':record.get('class_context_gate'),'sections':sections,
            'metrics':record.get('metrics'),'report':result.get('report',''),
            'notice':('실행 완료와 내용 정확성은 별개입니다. 원문과 조사 노트·원고를 대조하고, 표시된 경보와 실패 분석을 확인해 주세요.' if record['status']=='complete' else '아직 완성된 원고가 없습니다. 표시된 오류와 실행 상태를 확인해 주세요.'),
            'review':path.with_name('REVIEW.md').read_text(encoding='utf-8') if path.with_name('REVIEW.md').exists() else None}


def engineering_playback(identifier):
    """Old graph records lack event clocks: show order, never invented API timings."""
    from planetary_web import display_event
    record=read_json(run_path(identifier))
    events=record.get('events',[])
    if record['status']!='complete' or not events:
        raise ValueError('재생할 그래프 이벤트가 없는 미완료 기록입니다.')
    view=[]
    for index,event in enumerate(events):
        value=display_event(event)
        value.update(id=index,t=float(index))
        view.append(value)
    cfg=record['config']
    return {'id':identifier,'domain':'planetary','mode':'planetary_trace',
            'time_basis':'event_order_illustration_not_elapsed_seconds',
            'question':record['question'],'model':record.get('requested_model'),
            'status':'complete' if record['status']=='complete' else 'error',
            'events':view,'report':record.get('result',{}).get('report',''),
            'settings':{'max_sections':cfg['max_sections'],'budget':cfg['document_budget'],
                        'rounds':cfg['max_redispatch_rounds']},
            'quality_warnings':['저장된 실제 진단 · 내용 품질 미통과/미검증 · 이벤트 순서 연출이며 실제 소요시간이 아닙니다.']}


COMPARISONS=ROOT/'output/codex_comparisons'
CONDITION_LABELS={'basic':'기본형','no_roles':'역할 끔','no_seeds':'시작 자료 끔',
                  'no_zones':'구역 공유 끔','no_redispatch':'재조사 끔','single_agent':'단일 대조군'}
CONDITION_DESCRIPTIONS={
    'no_zones':'다른 연구원의 담당 구역을 알려 주지 않고, 그 연구원에게 배정된 시작 자료도 다음 자료 후보에서 제외하지 않습니다.'}


def comparison_folder(identifier):
    if not isinstance(identifier,str) or not re.fullmatch(r'\d{8}-\d{6}(-[0-9a-f]{4,12})?',identifier):
        raise ValueError('올바른 비교 기록 ID가 아닙니다.')
    path=COMPARISONS/identifier
    if not path.is_dir() or not path.resolve().is_relative_to(COMPARISONS.resolve()):raise ValueError('비교 기록을 찾지 못했습니다.')
    return path


def comparison_rows(folder):
    """진행 중에는 runs.jsonl이 없거나 마지막 줄이 잘려 있을 수 있어 깨진 줄은 건너뛴다."""
    path=folder/'runs.jsonl'
    if not path.is_file():return []
    rows=[]
    try:lines=path.read_text(encoding='utf-8',errors='replace').splitlines()
    except OSError:return []
    for line in lines:
        try:row=json.loads(line)
        except ValueError:continue
        if isinstance(row,dict) and isinstance(row.get('id'),str):rows.append(row)
    # A resumed run appends a new row for the same id (aborted -> complete): keep the
    # latest row per id, in first-seen order, and say how many attempts there were.
    latest={};tries={}
    for row in rows:
        tries[row['id']]=tries.get(row['id'],0)+1
        latest[row['id']]=row
    return [{**row,'attempts_recorded':tries[key]} for key,row in latest.items()]


def comparison_manifest(folder):
    try:value=read_json(folder/'manifest.json')
    except (OSError,ValueError):return {}
    return value if isinstance(value,dict) else {}


def alarm_names(row):
    alarms=(row.get('metrics') or {}).get('alarms_expected_zero') or {}
    return sorted(k for k,v in alarms.items() if v)


def comparison_row_summary(row):
    return {'id':row['id'],'question_id':row.get('question_id'),'repeat':row.get('repeat'),
            'condition':row.get('condition'),'condition_label':CONDITION_LABELS.get(row.get('condition'),row.get('condition')),
            'condition_description':CONDITION_DESCRIPTIONS.get(row.get('condition')),
            'status':row.get('status'),'error_type':row.get('error_type'),'alarms':alarm_names(row)}


def comparison_summary(identifier):
    folder=comparison_folder(identifier);manifest=comparison_manifest(folder);rows=comparison_rows(folder)
    completed=sum(r.get('status')=='complete' for r in rows)
    errors=sum(r.get('status') in {'error','aborted','failed','interrupted'} for r in rows)
    expected=manifest.get('expected_rows')
    if not isinstance(expected,int) or isinstance(expected,bool) or expected<=0:
        expected=len(manifest.get('questions') or [])*len(manifest.get('conditions') or [])*(manifest.get('repeats') or 0)
    if not isinstance(expected,int) or expected<=0:expected=None
    process=manifest.get('status') or ('running' if not manifest.get('ended_at') else 'unknown')
    terminal=bool(rows) and completed+errors==len(rows)
    covered=expected is None or len(rows)>=expected
    # The manifest can lag the final row, or say complete despite row failures.
    # Partial rows are not the final outcome while a process is running/stopped.
    if terminal and covered and (process!='running' or expected is not None):
        status='failed' if errors==len(rows) else 'partial_failure' if errors else 'complete'
    elif process=='running':status='running'
    elif process in {'stopped_usage_limit','interrupted','stopped','error'}:status='stopped'
    elif process in {'complete','finished_with_errors'}:status='incomplete'
    else:status='unknown'
    reason={'stopped_usage_limit':'사용 한도','interrupted':'사용자 중단','error':'실행 오류'}.get(process)
    scope_label={'FORMAL_COMPARISON':'정식 비교',
                 'SMALL_LIVE_DIAGNOSTIC_NOT_FORMAL_COMPARISON':'연결 확인 진단'}.get(manifest.get('scope'),'비교 기록')
    corpus_id=comparison_corpus(manifest);corpus_label='자료 모음 미확인'
    if corpus_id:
        try:
            count=read_json(corpus_folder(corpus_id)/'statistics.json')['document_count']
            corpus_label=f"{'기본' if corpus_id=='base' else '확장'} {count}건"
        except (OSError,ValueError,KeyError):pass
    date_label=None
    try:
        started=datetime.fromisoformat(manifest.get('started_at') or '')
        if started.tzinfo is not None:
            local=started.astimezone(timezone(timedelta(hours=9)))
            date_label=f'{local.month}월 {local.day}일'
    except (ValueError,TypeError):pass
    title_parts=[scope_label,corpus_label]
    if expected is not None:title_parts.append(f'{expected}회')
    if date_label:title_parts.append(date_label)
    return {'id':identifier,'scope':manifest.get('scope'),'status':status,
            'corpus_id':corpus_id,'scope_label':scope_label,'display_title':' · '.join(title_parts),
            'process_status':process,'stop_reason':reason if status=='stopped' else None,
            'completed_rows':completed,'pending_rows':max(0,expected-completed-errors) if expected is not None else None,
            'model':(manifest.get('model_identity') or {}).get('model'),'started_at':manifest.get('started_at'),
            'ended_at':manifest.get('ended_at'),'rows':len(rows),'expected_rows':expected or None,'errors':errors,
            'conditions':manifest.get('conditions') or [],'shared_read_budget':manifest.get('shared_read_budget'),
            'all_failed':status=='failed' and bool(rows) and errors==len(rows)}


def comparison_index():
    result=[]
    if not COMPARISONS.is_dir():return result
    for path in sorted(COMPARISONS.iterdir(),reverse=True):
        try:result.append(comparison_summary(path.name))
        except (OSError,ValueError):continue
    return result


def comparison_row_statistics(folder,row):
    """Display recorded counts without treating absent/failed output as zero."""
    stats={key:None for key in ('sections','report_chars','read_events','unique_read_documents',
                                'initial_insufficient_sections','duplicate_read_fraction','baseline_full_budget_used')}
    if row.get('status')!='complete':return stats
    metrics=row.get('metrics') or {};counts=metrics.get('counts') or {}
    stats.update(sections=row.get('plan_sections',counts.get('selected_sections')),
                 report_chars=counts.get('report_chars'),read_events=counts.get('read_events'),
                 unique_read_documents=counts.get('unique_read_documents'),
                 duplicate_read_fraction=(metrics.get('signals') or {}).get('duplicate_read_fraction'),
                 baseline_full_budget_used=(row.get('baseline_validation') or {}).get('full_budget_used'))
    identifier=row.get('id','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identifier):return stats
    try:result=read_json(folder/'reports'/f'{identifier}.json')
    except (OSError,ValueError):return stats
    if not isinstance(result,dict):return stats
    if stats['sections'] is None and isinstance((result.get('plan') or {}).get('목차'),list):
        stats['sections']=len(result['plan']['목차'])
    if stats['report_chars'] is None and isinstance(result.get('report'),str):
        stats['report_chars']=len(result['report'])
    if isinstance(result.get('attempts'),list):
        stats['initial_insufficient_sections']=len({s['번호'] for s in result['attempts']
            if s.get('round')==0 and s.get('부족') and s.get('번호') is not None})
    if isinstance(result.get('events'),list):
        reads=[e for e in result['events'] if e.get('kind')=='read']
        if stats['read_events'] is None:stats['read_events']=len(reads)
        if stats['unique_read_documents'] is None and all(isinstance(e.get('document'),str) for e in reads):
            stats['unique_read_documents']=len({e['document'] for e in reads})
    return stats


def comparison_detail(identifier):
    folder=comparison_folder(identifier);manifest=comparison_manifest(folder)
    rows=[{**comparison_row_summary(r),'statistics':comparison_row_statistics(folder,r)} for r in comparison_rows(folder)]
    documents=[]
    for name,label in [('HUMAN_REVIEW.md','직접 판단과 실패 추적'),('RUN_NOTES.md','실행 경과와 한계')]:
        path=folder/name
        if path.is_file() and path.resolve().is_relative_to(folder.resolve()):
            documents.append({'name':name,'label':label,'body':path.read_text(encoding='utf-8')})
    return {**comparison_summary(identifier),'questions':manifest.get('questions') or [],'repeats':manifest.get('repeats'),
            'review_documents':documents,
            'rows_detail':rows,'billing':manifest.get('billing'),
            'principle':'지표는 명백한 실패를 거르는 용도입니다. 점수·승자·순위는 매기지 않습니다. 보고서와 근거를 사람이 직접 읽고 판단하세요.'}


def comparison_run(identifier,row_id):
    folder=comparison_folder(identifier)
    if not isinstance(row_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',row_id):
        raise ValueError('올바른 실행 ID가 아닙니다.')
    row=next((r for r in comparison_rows(folder) if r['id']==row_id),None)
    if row is None:raise ValueError('실행 행을 찾지 못했습니다.')
    view={**comparison_row_summary(row),'corpus_id':comparison_corpus(comparison_manifest(folder)),
          'question':row.get('question'),'engine_class':row.get('engine_class'),
          'wiring':row.get('wiring'),'transport_stats':row.get('transport_stats'),
          'alarms_expected_zero':(row.get('metrics') or {}).get('alarms_expected_zero'),
          'signals':(row.get('metrics') or {}).get('signals'),
          'baseline_validation':row.get('baseline_validation'),'sections':[],'report':'','plan_title':None,
          'stop_events':[]}
    result_path=folder/'reports'/f'{row_id}.json'
    if row.get('status')=='complete' and result_path.is_file():
        try:result=read_json(result_path)
        except (OSError,ValueError):result={}
        agents={}
        for e in result.get('events',[]):
            if e.get('kind')=='assignment':agents[(e.get('task') or {}).get('번호')]=e.get('agent')
            elif e.get('kind')=='stop_reading':view['stop_events'].append({'agent':e.get('agent'),'reason':e.get('reason'),'round':e.get('round')})
        view['plan_title']=(result.get('plan') or {}).get('제목')
        view['report']=result.get('report','')
        for s in result.get('selected',[]):
            view['sections'].append({'index':s.get('번호'),'title':s.get('절'),'role':s.get('역할'),
                'agent':agents.get(s.get('번호')),'read_documents':s.get('읽은문서') or [],
                'body':s.get('본문',''),'insufficient':bool(s.get('부족')),'reason':s.get('이유'),'round':s.get('round')})
    return view
