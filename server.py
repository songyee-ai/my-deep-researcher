"""Moonlight Research: local-only observability around the unchanged D48 pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Local inspection must not forward prompts to an ambient tracing service.
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'

from dotenv import dotenv_values
import pipeline as p
import library
from free_api import load_config, verify_free_model, FreeAPIModel, safe_api_error

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
RUNS_DIR = ROOT / 'runs'
CONTEXT = threading.local()
LOCK = threading.RLock()
RUNS: dict[str, dict] = {}
STOPS: dict[str, threading.Event] = {}
ACTIVE: str | None = None
SECRET = ''
PLANETARY_QUESTION = '수성과 금성 탐사에서 강한 열 환경에 대응하는 설계는 어떻게 달랐으며, 그 차이가 관측에 주는 제약은 무엇인가?'
LEGACY_FILE = ROOT / 'legacy_mode.json'
PHASE_LABELS = {'plan': '목차 짜기', 'read': '문서 읽기', 'pick': '다음 자료 고르기', 'write': '원고 쓰기', 'edit': '보고서 엮기'}


def legacy_texts():
    """이전 단계 모드(저장 자료 재생·이전 코퍼스 실호출)의 문구. 문구 파일과 자료가 모두 있을 때만 켜진다."""
    if not (LEGACY_FILE.is_file() and (DATA / 'corpus.json').is_file() and (DATA / '결과자료.json').is_file()):
        return None
    try:
        return json.loads(LEGACY_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


class Stopped(Exception):
    pass


def clean(value):
    if isinstance(value, str):
        if SECRET:
            value = value.replace(SECRET, '[키 숨김]')
        return re.sub(r'sk-[A-Za-z0-9_\-]{8,}', '[키 숨김]', value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def emit(run_id, kind, **fields):
    if STOPS[run_id].is_set():
        raise Stopped('사용자가 실행을 중지했습니다.')
    with LOCK:
        run = RUNS[run_id]
        event = clean(dict(id=len(run['events']), t=round(time.monotonic() - run['_start'], 3), kind=kind, **fields))
        run['events'].append(event)
    return event


class ObservedModel:
    def __init__(self, model, run_id):
        self.model, self.run_id = model, run_id

    def __call__(self, step, prompt):
        agent = getattr(CONTEXT, 'agent', 'moon' if step == p.Step.PLAN else 'crystal')
        call_id = uuid.uuid4().hex[:12]
        emit(self.run_id, 'call_start', agent=agent, step=step.value, label=PHASE_LABELS[step.value],
             call_id=call_id, system=prompt.system, user=prompt.user,
             input_chars=len(prompt.system) + len(prompt.user),
             sent_user_chars=min(len(prompt.user), 60_000) if isinstance(self.model, p.OpenAIModel) else len(prompt.user))
        try:
            answer = self.model(step, prompt)
        except Exception as exc:
            if isinstance(exc, Stopped):
                raise
            emit(self.run_id, 'call_error', agent=agent, call_id=call_id, step=step.value, label=PHASE_LABELS[step.value], error=safe_api_error(exc))
            raise
        emit(self.run_id, 'call_end', agent=agent, call_id=call_id, step=step.value,
             label=PHASE_LABELS[step.value], response=answer, output_chars=len(answer))
        return answer


class ObservedResearch(p.DeepResearch):
    def plan(self, state):
        result = super().plan(state)
        emit(self.model.run_id, 'plan', agent='moon', label='행성 연구원 배치', plan=result['plan'])
        return result

    def researcher(self, state):
        CONTEXT.agent = f"researcher-{state['task']['번호']}"
        try:
            emit(self.model.run_id, 'assignment', agent=CONTEXT.agent, label='조사 시작', task=state['task'])
            result = super().researcher(state)
            emit(self.model.run_id, 'section', agent=CONTEXT.agent, label='원고 완성', section=result['sections'][0])
            return result
        finally:
            del CONTEXT.agent

    def synthesize(self, state):
        CONTEXT.agent = 'crystal'
        try:
            result = super().synthesize(state)
            emit(self.model.run_id, 'report', agent='crystal', label='보고서 완성', report=result['report'])
            return result
        finally:
            del CONTEXT.agent


def public_run(run):
    return {k: v for k, v in run.items() if not k.startswith('_')}


def report_warnings(sections):
    warnings=[]
    for section in sections:
        if len(section['본문'])<600:
            warnings.append(f"{section['절']}: 요청한 600자보다 짧습니다.")
        if not section.get('인용'):
            warnings.append(f"{section['절']}: 문서 인용 표기가 없습니다.")
    return warnings


def persist(run):
    RUNS_DIR.mkdir(exist_ok=True)
    target = RUNS_DIR / f"{run['id']}.json"
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(clean(public_run(run)), ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(target)


def work(run_id):
    global ACTIVE
    run = RUNS[run_id]
    try:
        if run.get('domain') == 'planetary':
            work_planetary(run_id)
            return
        corpus = p.Corpus.load(DATA)
        emit(run_id, 'start', agent='moon', label='달빛 연구 시작', summary=corpus.summary())
        if run['mode']=='replay':
            model=p.ReplayModel.load(DATA, run['question'])
        else:
            config=load_config()
            verify_free_model(config)
            model=FreeAPIModel(config)
        observed = ObservedModel(model, run_id)
        settings = p.Settings(**run['settings'])
        result = ObservedResearch(corpus, observed, settings).run(run['question'])
        with LOCK:
            run['report'] = result['report']
            run['quality_warnings'] = report_warnings(result['sections']) if run['mode']=='live' else []
            run['status'] = 'complete'
    except (Exception, SystemExit) as exc:
        with LOCK:
            run['status'] = 'stopped' if isinstance(exc, Stopped) else 'error'
            run['error'] = clean(str(exc) if isinstance(exc,Stopped) else safe_api_error(exc))
    finally:
        with LOCK:
            run['duration'] = round(time.monotonic() - run['_start'], 3)
            try:
                persist(run)
            except OSError:
                run['save_error'] = '기록을 파일로 저장하지 못했습니다. 실행 기록을 내려받아 주세요.'
            ACTIVE = None


def work_planetary(run_id):
    from graph import load_project
    from planetary_web import WebResearch, display_event
    from planetary_api import PlanetaryAPIModel
    from baseline import shared_budget
    from metrics import measure
    import copy
    run = RUNS[run_id]
    corpus, config = load_project()
    config = copy.deepcopy(config)
    options = run['settings']
    config.update(max_sections=options['max_sections'], document_budget=options['budget'],
                  max_redispatch_rounds=options['rounds'], draft_format='source_ids_v1',
                  note_format='extractive_v1', planning_cards='topic_snippets_v1', quotes_only=True)
    config['switches'].update(roles=options['use_roles'], seeds=options['assign_seeds'],
                              zones=options['respect_zones'])
    run.update(config=config, quality_qualification='pending',
               class_context_gate='NOT_CHECKED_IN_WEB_RUN')
    def forward(event):
        value = display_event(event)
        emit(run_id, value.pop('kind'), **value)
    emit(run_id, 'start', agent='moon', label='행성 탐사 기능 진단 시작',
         summary=f'공식 원문 {len(corpus.docs)}건 · 내용 품질 미검증')
    model = PlanetaryAPIModel(load_config(), run['model'],
        DATA/'planetary_exploration/model_checks/google_gemma_4_26b_a4b_it_free/tokenizer.json',
        RUNS_DIR/'planetary_calls'/run_id/'calls.json')
    result = WebResearch(corpus, model, config, emit=forward).run(run['question'])
    # The out-of-scope branch intentionally makes no synthesis model call.
    if not any(e['kind']=='report' for e in run['events']):
        emit(run_id, 'report', agent='crystal', label='자료 범위 안내', report=result['report'])
    with LOCK:
        run.update(report=result['report'], result=result, config=config,
                   metrics=measure(result, corpus, config, shared_budget(config)),
                   quality_warnings=['기능 진단: 원문·인과·부족 신고의 내용 검토가 필요합니다.'],
                   model_identity=model.model_identity, transport_stats=model.transport_stats,
                   status='complete')


def start_run(payload):
    global ACTIVE, SECRET
    legacy = legacy_texts()
    mode = payload.get('mode', 'replay' if legacy else 'planetary')
    if mode not in ('replay', 'live', 'planetary') or (mode != 'planetary' and not legacy):
        raise ValueError('실행 모드를 확인해 주세요.')
    question = str(payload.get('question', p.DEFAULT_QUESTION if legacy else PLANETARY_QUESTION)).strip()
    if not question or len(question) > 2000:
        raise ValueError('질문은 1~2,000자로 입력해 주세요.')
    settings = payload.get('settings', {})
    sections = int(settings.get('max_sections', 4))
    budget = int(settings.get('budget', 3))
    if not 1 <= sections <= 8 or not 1 <= budget <= 5:
        raise ValueError('리서처 1~8명, 읽기 예산 1~5건을 선택해 주세요.')
    options = dict(max_sections=sections, budget=budget,
                   use_roles=bool(settings.get('use_roles', True)),
                   assign_seeds=bool(settings.get('assign_seeds', True)),
                   respect_zones=bool(settings.get('respect_zones', True)))
    if mode == 'planetary':
        rounds = int(settings.get('rounds', 1))
        if not 0 <= rounds <= 3:
            raise ValueError('재조사 상한은 0~3회입니다.')
        options['rounds'] = rounds
    with LOCK:
        if ACTIVE:
            raise ValueError('진행 중인 연구가 있어요. 완료하거나 중지한 뒤 실행해 주세요.')
        if mode in ('live', 'planetary'):
            config=load_config()
            SECRET=config.key
        else:
            # ReplayModel is a reconstruction of Q4, not arbitrary-question API output.
            question = p.DEFAULT_QUESTION
        run_id = uuid.uuid4().hex
        run = dict(id=run_id, created=datetime.now().astimezone().isoformat(timespec='seconds'),
                   mode=mode, question=question, model=('google/gemma-4-26b-a4b-it:free' if mode=='planetary' else config.model) if mode != 'replay' else legacy['replay_model'],
                   domain='planetary' if mode=='planetary' else 'history',
                   scope='LIVE_ENGINEERING_ONLY_NOT_CLASS_COMPARISON' if mode=='planetary' else 'course',
                   provider=config.provider if mode!='replay' else None,free_only=mode!='replay',
                   settings=options, status='running', events=[], report='', _start=time.monotonic(),
                   pipeline_sha256=hashlib.sha256((ROOT / 'pipeline.py').read_bytes()).hexdigest())
        RUNS[run_id] = run
        STOPS[run_id] = threading.Event()
        ACTIVE = run_id
        threading.Thread(target=work, args=(run_id,), daemon=True).start()
        return {'id': run_id}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'web'), **kwargs)

    def log_message(self, *_args):
        pass

    def json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/api/library'):
            try:
                if path=='/api/library':value=library.corpus_index(parse_qs(urlparse(self.path).query).get('corpus',['base'])[0])
                elif path=='/api/library/document':
                    params=parse_qs(urlparse(self.path).query)
                    value=library.document(params.get('title',[''])[0],params.get('corpus',['base'])[0])
                elif path=='/api/library/runs':value=library.engineering_index()
                elif path=='/api/library/comparisons':value=library.comparison_index()
                elif path.startswith('/api/library/comparisons/'):
                    parts=path[len('/api/library/comparisons/'):].split('/')
                    if len(parts)==1:value=library.comparison_detail(parts[0])
                    elif len(parts)==2:value=library.comparison_run(parts[0],parts[1])
                    else:raise ValueError('없는 자료실 주소입니다.')
                elif path.endswith('/playback') and path.startswith('/api/library/runs/'):
                    value=library.engineering_playback(path.split('/')[-2])
                elif path.startswith('/api/library/runs/'):value=library.engineering_detail(path.rsplit('/',1)[-1])
                else:raise ValueError('없는 자료실 주소입니다.')
                self.json(clean(value))
            except (ValueError,OSError,KeyError):
                self.json({'error':'자료 또는 기록을 찾지 못했습니다.'},404)
        elif path == '/api/status':
            corpus = p.Corpus.load(DATA) if (DATA / 'corpus.json').exists() else None
            try:
                config=load_config()
                api_status=dict(api_configured=True,provider=config.provider,model=config.model,free_only=True)
            except (ValueError,OSError):
                api_status=dict(api_configured=False,provider='OpenRouter',model=None,free_only=True)
            legacy = legacy_texts()
            self.json(dict(default_question=p.DEFAULT_QUESTION if legacy else PLANETARY_QUESTION,
                           planetary_question=PLANETARY_QUESTION, legacy=legacy, active=ACTIVE,
                           docs=[dict(title=k, chars=len(v)) for k, v in corpus.docs.items()] if corpus else [],
                           **api_status))
        elif path == '/api/runs':
            with LOCK:
                self.json([dict(id=r['id'], question=r['question'], mode=r['mode'], created=r['created'], status=r['status'])
                           for r in sorted(RUNS.values(),key=lambda r:r['created'],reverse=True)])
        elif path.startswith('/api/runs/'):
            run_id = path.split('/')[-1]
            with LOCK:
                run = RUNS.get(run_id)
                self.json(public_run(run) if run else {'error': '기록을 찾지 못했습니다.'}, 200 if run else 404)
        elif path.startswith('/api/'):
            self.json({'error': '없는 주소입니다.'}, 404)
        else:
            super().do_GET()

    def do_POST(self):
        origin = self.headers.get('Origin')
        expected = f"http://{self.headers.get('Host')}"
        if origin and origin != expected:
            return self.json({'error': '다른 사이트에서 실행할 수 없습니다.'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json({'error': 'JSON 요청만 지원합니다.'}, 415)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length < 20_000:
            return self.json({'error': '요청 크기를 확인해 주세요.'}, 400)
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('요청 형식이 올바르지 않습니다.')
            if self.path == '/api/run':
                self.json(start_run(payload), 202)
            elif self.path == '/api/stop':
                with LOCK:
                    if ACTIVE:
                        STOPS[ACTIVE].set()
                self.json({'ok': True})
            else:
                self.json({'error': '없는 주소입니다.'}, 404)
        except (ValueError, TypeError) as exc:
            self.json({'error': clean(str(exc))}, 400)


def load_runs():
    for path in sorted(RUNS_DIR.glob('*.json')) if RUNS_DIR.exists() else []:
        try:
            run = json.loads(path.read_text(encoding='utf-8'))
            if re.fullmatch(r'[a-f0-9]{32}', run['id']):
                RUNS[run['id']] = run
        except (OSError, ValueError, KeyError):
            continue


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8785)
    args = parser.parse_args()
    load_runs()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Moonlight Research http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
