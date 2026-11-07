"""Paired CLI comparison: distributed CodexResearch vs. fact-table single agent.

Uses ChatGPT-login Codex CLI (subscription usage, no API-key billing). A small
diagnostic run is NOT the formal 54-run comparison in EXPERIMENT_SPEC.md.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import tomllib
import uuid

from ablation import CONDITIONS,run_experiments,corpus_fingerprint
from baseline import shared_budget
from codex_graph import codex_engine_factory,codex_model_identity,codex_settings
from graph import load_project
from pipeline import Corpus
from codex_cli_bridge import UsageLimitError

ROOT=Path(__file__).resolve().parent


def build_parser():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='실제 CLI 호출(ChatGPT 구독 한도 사용)')
    parser.add_argument('--questions',default='P04',help='쉼표로 구분한 질문 ID')
    parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--conditions',default=','.join(CONDITIONS),help='basic으로 시작하는 조건 목록')
    parser.add_argument('--sections',type=int,default=2)
    parser.add_argument('--budget',type=int,default=1)
    parser.add_argument('--rounds',type=int,default=1)
    parser.add_argument('--model')
    parser.add_argument('--scope',choices=['diagnostic','formal'],default='diagnostic')
    parser.add_argument('--resume',help='한도 등으로 멈춘 output/codex_comparisons/<폴더>를 저장된 설정 그대로 이어 돌림')
    parser.add_argument('--corpus-dir',help='data/ 아래 코퍼스 폴더(기본: config.json의 corpus_dir). 예: data/planetary_exploration/versions/engineering-v2')
    return parser


def resume_run(parser,folder):
    """Continue a stopped comparison with exactly the stored settings."""
    folder=Path(folder).resolve()
    if not folder.is_relative_to(ROOT/'output'/'codex_comparisons') or not (folder/'manifest.json').is_file():
        parser.error('--resume must be an output/codex_comparisons folder with manifest.json')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')=='complete' and manifest.get('complete_rows')==manifest.get('expected_rows'):
        parser.error('모든 실행이 완료된 비교는 이어 돌리지 않습니다.')
    config=manifest['base_config']
    corpus=Corpus.load(ROOT/config['corpus_dir'])
    if corpus_fingerprint(corpus)!=manifest['corpus_sha256']:parser.error('코퍼스가 저장된 실행과 다릅니다.')
    manifest.setdefault('resumes',[]).append({'previous_status':manifest.get('status'),'previous_stop':manifest.get('stopped_early'),
                                              'resumed_at':datetime.now(timezone.utc).isoformat()})
    manifest['status']='running'
    return folder,manifest,corpus,config,manifest['questions'],manifest['conditions'],manifest['repeats'],manifest['model_identity']['model']


def main():
    parser=build_parser();args=parser.parse_args()
    if not args.live:parser.error('실제 CLI 비교는 --live를 명시해야 합니다.')
    if args.resume:
        folder,manifest,corpus,config,chosen,conditions,repeats,model_name=resume_run(parser,args.resume)
        return execute(folder,manifest,corpus,config,chosen,conditions,repeats,model_name,resume=True)
    model_name=args.model or tomllib.loads((Path.home()/'.codex/config.toml').read_text(encoding='utf-8')).get('model')
    if not model_name:parser.error('CLI model is not configured')
    corpus,config=load_project()
    if args.corpus_dir:
        chosen_dir=(ROOT/args.corpus_dir).resolve()
        if not chosen_dir.is_relative_to(ROOT/'data') or not (chosen_dir/'corpus.json').is_file():
            parser.error('--corpus-dir must be a folder under data/ containing corpus.json')
        corpus=Corpus.load(chosen_dir)
        config['corpus_dir']=chosen_dir.relative_to(ROOT).as_posix()
    config=codex_settings(config)
    config.update(max_sections=args.sections,document_budget=args.budget,max_redispatch_rounds=args.rounds)
    questions=json.loads((ROOT/config['corpus_dir']/'questions.json').read_text(encoding='utf-8'))['questions']
    wanted=[q.strip() for q in args.questions.split(',') if q.strip()]
    chosen=[q for q in questions if q['id'] in wanted]
    if len(chosen)!=len(wanted):parser.error('Unknown question ID')
    chosen=[{'id':q['id'],'question':q['question']} for q in chosen]
    conditions=[c.strip() for c in args.conditions.split(',') if c.strip()]
    folder=ROOT/'output'/'codex_comparisons'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=False)
    identity=codex_model_identity(model_name)
    manifest={'scope':'SMALL_LIVE_DIAGNOSTIC_NOT_FORMAL_COMPARISON' if args.scope=='diagnostic' else 'FORMAL_COMPARISON',
              'model_identity':identity,'corpus_dir':config['corpus_dir'],'corpus_sha256':corpus_fingerprint(corpus),
              'questions':chosen,'conditions':conditions,'repeats':args.repeats,'base_config':config,
              'shared_read_budget':shared_budget(config),'billing':'ChatGPT subscription usage; no API key billing fallback',
              'started_at':datetime.now(timezone.utc).isoformat(),'status':'running'}
    return execute(folder,manifest,corpus,config,chosen,conditions,args.repeats,model_name,resume=False)


def execute(folder,manifest,corpus,config,chosen,conditions,repeats,model_name,resume):
    identity=codex_model_identity(model_name)
    if manifest['model_identity']!=identity:raise SystemExit('모델 설정(identity)이 저장된 실행과 다릅니다.')
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        result=run_experiments(corpus,config,chosen,None,identity,folder,repeats=repeats,
                               engine_factory=codex_engine_factory(model_name,folder/'calls'),conditions=conditions,
                               resume=resume,abort_on=(UsageLimitError,))
        expected=len(chosen)*repeats*len(conditions)
        finished=sum(r['status']=='complete' for r in result['records'])
        manifest.update(status='stopped_usage_limit' if result['stopped_early'] else ('complete' if finished==expected else 'finished_with_errors'),
                        stopped_early=result['stopped_early'],records=len(result['records']),
                        complete_rows=finished,expected_rows=expected,
                        errors=sum(r['status']!='complete' for r in result['records']))
    except Exception as exc:
        # Setup errors (duplicate call folder, schema mismatch) stop the whole run on purpose;
        # rows already in runs.jsonl stay, the failing row is not written there.
        manifest.update(status='error',error_type=type(exc).__name__,error=str(exc)[:500])
    except BaseException as exc:
        manifest.update(status='interrupted',error_type=type(exc).__name__)
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    manifest['ended_at']=datetime.now(timezone.utc).isoformat()
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'output':str(folder),'records':manifest.get('records'),
                      'complete_rows':manifest.get('complete_rows'),'expected_rows':manifest.get('expected_rows'),
                      'errors':manifest.get('errors'),'stopped_early':manifest.get('stopped_early')},ensure_ascii=False))


if __name__=='__main__':main()
