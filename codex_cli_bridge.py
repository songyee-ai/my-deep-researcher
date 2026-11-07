"""ChatGPT-login CLI structured generation, isolated from the research repository."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


class UsageLimitError(ValueError):
    """Subscription usage limit; every later call fails too, so callers should stop."""


def child_environment():
    # Subscription login only; never pass ambient API billing credentials.
    excluded={'OPENAI_API_KEY','CODEX_API_KEY','OPENROUTER_API_KEY','OPENAI_BASE_URL','OPENAI_API_BASE'}
    return {key:value for key,value in os.environ.items() if key.upper() not in excluded}


def redact(text):
    text=re.sub(r'sk-[A-Za-z0-9_-]{8,}','[redacted]',text)
    return re.sub(r'Bearer\s+[A-Za-z0-9._-]+','Bearer [redacted]',text,flags=re.I)


def build_command(executable,folder,model,resume_id=None,persist_session=False):
    folder=Path(folder).resolve()
    command=[executable,'exec','--ignore-user-config','--skip-git-repo-check',
            '--sandbox','read-only','--disable','shell_tool','--disable','apps',
            '--disable','browser_use','--disable','computer_use',
            '--model',model,'--config','model_reasoning_effort="medium"',
            '--json','--color','never','--cd',str(folder/'sandbox')]
    if not persist_session:command.append('--ephemeral')
    if resume_id:
        if not re.fullmatch(r'[a-f0-9-]{36}',resume_id):raise ValueError('정확한 CLI 세션 ID가 필요합니다.')
        command+=['resume',resume_id]
    command+=['--output-schema',str(folder/'schema.json'),'--output-last-message',str(folder/'response.json'),'-']
    return command


def generate(prompt,schema,folder,model,timeout=240,resume_id=None,persist_session=False):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    (folder/'sandbox').mkdir()
    (folder/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    instruction=('This is a supplied-text extraction task, not a coding task. '
                 'Use only the source in this prompt. Do not invoke tools, read files, browse, edit, '
                 'or delegate. Return exactly one JSON object matching the output schema.\n\n'
                 +prompt.system+'\n\n'+prompt.user)
    (folder/'prompt.txt').write_text(instruction,encoding='utf-8')
    executable=shutil.which('codex')
    if not executable:raise ValueError('Codex CLI가 설치되어 있지 않습니다.')
    environment=child_environment()
    auth=subprocess.run([executable,'login','status'],capture_output=True,text=True,encoding='utf-8',errors='replace',env=environment,timeout=30)
    if auth.returncode!=0 or 'Logged in using ChatGPT' not in auth.stdout+auth.stderr:
        raise ValueError('ChatGPT 로그인 상태가 아니어서 실행하지 않습니다.')
    command=build_command(executable,folder,model,resume_id,persist_session)
    (folder/'command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
    start=time.monotonic()
    try:
        completed=subprocess.run(command,input=instruction,capture_output=True,text=True,encoding='utf-8',errors='replace',env=environment,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        def partial(value):return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else (value or '')
        (folder/'events.jsonl').write_text(redact(partial(exc.stdout)),encoding='utf-8')
        (folder/'stderr.txt').write_text(redact(partial(exc.stderr)),encoding='utf-8')
        (folder/'transport.json').write_text(json.dumps({'status':'timeout','exit_code':None,
            'seconds':round(time.monotonic()-start,3),'model_requested':model,'authentication':'ChatGPT login'},indent=2),encoding='utf-8')
        raise ValueError('Codex CLI 제한 시간을 넘겨 중단했습니다. 부분 기록은 보존했습니다.') from None
    (folder/'events.jsonl').write_text(redact(completed.stdout),encoding='utf-8')
    (folder/'stderr.txt').write_text(redact(completed.stderr),encoding='utf-8')
    events=[]
    for line in completed.stdout.splitlines():
        try:events.append(json.loads(line))
        except ValueError:pass
    usage=[event.get('usage') for event in events if event.get('type')=='turn.completed']
    allowed={'agent_message','reasoning','plan'}
    forbidden=[event.get('item',{}).get('type') for event in events
               if event.get('item',{}).get('type') and event['item']['type'] not in allowed]
    transport={'exit_code':completed.returncode,'seconds':round(time.monotonic()-start,3),
               'model_requested':model,'authentication':'ChatGPT login','usage':usage,
               'session_id':next((e.get('thread_id') for e in events if e.get('type')=='thread.started'),None),
               'resumed_session_id':resume_id,'session_persisted':persist_session,
               'unexpected_tool_items':forbidden,'billing_note':'ChatGPT subscription usage; not an OpenRouter free request.'}
    (folder/'transport.json').write_text(json.dumps(transport,ensure_ascii=False,indent=2),encoding='utf-8')
    if completed.returncode!=0:
        messages=[str(e.get('message','')) for e in events if e.get('type') in ('error','turn.failed')]
        messages+=[str(e.get('error',{}).get('message','')) for e in events if isinstance(e.get('error'),dict)]
        limit=next((m for m in messages if 'usage limit' in m.lower()),None)
        if limit:raise UsageLimitError(limit)
        raise ValueError('Codex CLI 실행 실패: 로컬 transport.json/stderr.txt 확인')
    if forbidden:raise ValueError('자료 추출 외의 도구 실행이 감지돼 결과를 채택하지 않습니다.')
    response=folder/'response.json'
    if not response.is_file():raise ValueError('Codex CLI의 최종 JSON 응답이 없습니다.')
    return json.loads(response.read_text(encoding='utf-8-sig')),transport
