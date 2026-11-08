"""Explicit free-provider configuration; credentials stay in a local .env (project root first, then the parent folder)."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import urllib.error
import urllib.request

from dotenv import dotenv_values
from langchain_openai import ChatOpenAI
import pipeline as p

ROOT = Path(__file__).resolve().parent
BASE_URL = 'https://openrouter.ai/api/v1'


@dataclass(frozen=True)
class APIConfig:
    provider: str
    model: str
    key: str = field(repr=False)


def load_config() -> APIConfig:
    settings = json.loads((ROOT / 'api-config.json').read_text(encoding='utf-8'))
    if settings.get('provider') != 'openrouter' or not str(settings.get('model','')).endswith(':free'):
        raise ValueError('무료 OpenRouter 모델(:free)만 설정할 수 있습니다.')
    # Read only OPENROUTER_API_KEY; ignore all other secrets and URLs. Do not copy the file.
    key = ''
    for env_path in (ROOT / '.env', ROOT.parent / '.env'):
        key = dotenv_values(env_path, interpolate=False).get('OPENROUTER_API_KEY') or ''
        if key:
            break
    if not key:
        raise ValueError('프로젝트 폴더 .env(없으면 상위 폴더 .env)의 OPENROUTER_API_KEY를 확인해 주세요.')
    return APIConfig('OpenRouter', settings['model'], key)


def verify_free_model(config):
    req = urllib.request.Request(BASE_URL+'/models', headers={
        'Authorization':'Bearer '+config.key,'User-Agent':'MoonlightResearch/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            models=json.load(response)['data']
    except urllib.error.HTTPError as exc:
        raise ValueError(f'무료 모델 확인 실패 (HTTP {exc.code}). 키와 할당량을 확인해 주세요.') from None
    except Exception:
        raise ValueError('무료 모델 목록에 연결하지 못했습니다. 네트워크를 확인해 주세요.') from None
    model=next((m for m in models if m['id']==config.model),None)
    if not model or any(float(model.get('pricing',{}).get(k,-1))!=0 for k in ('prompt','completion')):
        raise ValueError('선택 모델의 무료 요금을 확인할 수 없어 실행을 중단했습니다.')


class FreeAPIModel(p.OpenAIModel):
    def __init__(self, config):
        self._llm=ChatOpenAI(model=config.model, api_key=config.key, base_url=BASE_URL,
                            temperature=0,timeout=60,max_retries=0,max_tokens=4096,
                            extra_body={'provider':{'max_price':{'prompt':0,'completion':0}},
                                        'reasoning':{'enabled':False}})
        self._max_chars=60_000
        self._attempts=2

    def __call__(self,step,prompt):
        answer=super().__call__(step,prompt)
        if not answer.strip():
            raise ValueError('모델이 빈 응답을 반환해 연구를 중단했습니다. 완성되지 않은 보고서를 성공으로 처리하지 않습니다.')
        if step==p.Step.WRITE:
            body=str(p.parse_json_object(answer).get('본문') or '')
            if len(body)<p.MIN_SECTION_CHARS:
                raise ValueError('모델이 충분한 원고 본문을 반환하지 않아 연구를 중단했습니다.')
        return answer


def safe_api_error(exc):
    # Never serialize raw provider errors, request headers, or request objects.
    code=getattr(exc,'status_code',None)
    body=getattr(exc,'body',{})
    error=body.get('error',body) if isinstance(body,dict) else {}
    metadata=error.get('metadata',{}) if isinstance(error,dict) else {}
    upstream=str(metadata.get('raw','')) if isinstance(metadata,dict) else ''
    category=getattr(exc,'limit_category',None)
    if code==429 and category=='daily_quota':
        reset=getattr(exc,'reset_ms',None)
        when='매일 오전 9시(한국 시간)'
        if reset:
            from datetime import datetime,timedelta,timezone
            when=datetime.fromtimestamp(reset/1000,timezone(timedelta(hours=9))).strftime('%m월 %d일 %H시 %M분(한국 시간)')
        return (f'오늘 쓸 수 있는 무료 모델 요청 수를 모두 썼습니다 (HTTP 429, 하루 한도). {when}에 초기화됩니다. '
                'OpenRouter 계정에 충전액이 없으면 하루 50회이고, 충전하면 무료 모델 하루 한도가 1,000회로 늘어납니다.')
    if code==429 and (category=='upstream_capacity' or 'temporarily rate-limited upstream' in upstream):
        return '선택한 무료 모델이 공급자 쪽에서 붐빕니다 (HTTP 429). 메인 화면 목록에서 다른 무료 모델을 골라 다시 실행해 주세요.'
    if code==429 and category=='request_rate':
        return '분당 요청 한도에 걸렸습니다 (HTTP 429). 1분쯤 뒤에 다시 실행하거나 ⚙ 설정에서 연구원 수를 줄여 주세요.'
    if code==429:return '무료 API의 요청 제한에 도달했습니다 (HTTP 429). 잠시 후 다시 실행하거나 메인 화면 목록에서 다른 무료 모델을 골라 주세요.'
    if code in (401,403):return f'무료 API 인증 또는 접근 권한을 확인해 주세요 (HTTP {code}).'
    if code==402:return '무료 모델 제공 조건이나 계정 제한을 확인해 주세요 (HTTP 402). 유료 모델로 전환하지 않았습니다.'
    if code:return f'무료 API 호출에 실패했습니다 (HTTP {code}).'
    if isinstance(exc,ValueError):return str(exc)
    return f'무료 API 호출을 완료하지 못했습니다 ({type(exc).__name__}).'
