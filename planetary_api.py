"""Explicit free model adapter; no clipping, raw errors, or implicit paid route."""
import hashlib
import json
from pathlib import Path
import threading
import time
import re
from email.utils import parsedate_to_datetime
from datetime import datetime,timezone

import requests
from tokenizers import Tokenizer
from free_api import BASE_URL


class FreeRequestError(RuntimeError):
    def __init__(self,status_code,retry_after=None,limit_category='unknown'):
        self.status_code=status_code
        self.retry_after=safe_retry_after(retry_after)
        self.limit_category=limit_category if limit_category in ('daily_quota','request_rate','upstream_capacity') else 'unknown'
        super().__init__(f'무료 모델 요청 실패 (HTTP {status_code})')


def safe_retry_after(value):
    """Allow only the standard seconds/date forms, never arbitrary header text."""
    if not isinstance(value,str):return None
    if re.fullmatch(r'\d{1,9}',value):return value
    try:
        date=parsedate_to_datetime(value)
        if date.tzinfo is not None:return date.strftime('%a, %d %b %Y %H:%M:%S %z')
    except (ValueError,TypeError,OverflowError):pass
    return None


def limit_category(response):
    """Classify known error phrases locally; provider error bodies are not saved."""
    if response.status_code!=429:return 'unknown'
    try:
        body=response.json()
        error=body.get('error',{}) if isinstance(body,dict) else {}
        if not isinstance(error,dict):return 'unknown'
        message=str(error.get('message','')).lower()
        metadata=error.get('metadata')
        upstream=str(metadata.get('raw','')).lower() if isinstance(metadata,dict) else ''
        if 'per-day' in message or 'daily' in message:return 'daily_quota'
        if 'temporarily rate-limited upstream' in upstream:return 'upstream_capacity'
        if 'per-minute' in message:return 'request_rate'
    except (ValueError,TypeError):pass
    return 'unknown'


class PlanetaryAPIModel:
    def __init__(self,api_config,model_id,tokenizer_path,checkpoint=None):
        catalog=requests.get(BASE_URL+'/models',timeout=30);catalog.raise_for_status()
        m=next((x for x in catalog.json()['data'] if x['id']==model_id),None)
        if not m or not model_id.endswith(':free') or any(float(m.get('pricing',{}).get(k,-1))!=0 for k in ['prompt','completion']):
            raise ValueError('무료 모델 가격을 확인하지 못했습니다.')
        if (m.get('reasoning') or {}).get('mandatory'):
            raise ValueError('이 어댑터는 추론 비활성화가 가능한 모델만 지원합니다.')
        self._key=api_config.key;self.context_length=m['context_length']
        self.model_identity={'model':model_id,'temperature':0.1,'max_tokens':8192,'reasoning_enabled':False,'automatic_retries':0}
        self.tokenizer=Tokenizer.from_file(str(tokenizer_path));self.tokenizer.no_truncation();self.tokenizer.no_padding()
        self.checkpoint=Path(checkpoint) if checkpoint else None
        self.lock=threading.Lock();self.calls={}
        self.transport_stats={'cache_hits':0,'http_requests':0}
        if self.checkpoint and self.checkpoint.exists():
            previous=json.loads(self.checkpoint.read_text(encoding='utf-8'))
            if previous['model_identity']!=self.model_identity:raise ValueError('체크포인트의 모델 설정이 다릅니다.')
            self.calls=previous['calls']

    def save(self):
        if not self.checkpoint:return
        saved=json.dumps({'model_identity':self.model_identity,'calls':self.calls},ensure_ascii=False,indent=2)
        if self._key in saved:raise ValueError('비밀 값이 있어 기록을 거부했습니다.')
        self.checkpoint.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.checkpoint.with_suffix('.tmp')
        temporary.write_text(saved,encoding='utf-8');temporary.replace(self.checkpoint)

    def __call__(self,step,prompt):
        fingerprint=hashlib.sha256(json.dumps([self.model_identity,step.value,prompt.system,prompt.user],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        with self.lock:
            if fingerprint in self.calls:
                self.transport_stats['cache_hits']+=1
                return self.calls[fingerprint]['response']
        # Conservative overhead reserve; never silently truncate a source.
        estimated=len(self.tokenizer.encode(prompt.system+'\n'+prompt.user,add_special_tokens=False).ids)
        if estimated+self.model_identity['max_tokens']+1024>self.context_length:
            raise ValueError('입력과 출력 여유가 실제 제공 컨텍스트 한도를 초과합니다.')
        request={'model':self.model_identity['model'],'messages':[{'role':'system','content':prompt.system},{'role':'user','content':prompt.user}],
                 'temperature':self.model_identity['temperature'],'max_tokens':self.model_identity['max_tokens'],
                 'reasoning':{'enabled':False},'provider':{'max_price':{'prompt':0,'completion':0},'require_parameters':True}}
        started_at=datetime.now(timezone.utc).isoformat();start=time.monotonic()
        with self.lock:self.transport_stats['http_requests']+=1
        response=requests.post(BASE_URL+'/chat/completions',headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json'},json=request,timeout=90)
        if response.status_code!=200:
            raise FreeRequestError(response.status_code,response.headers.get('Retry-After'),limit_category(response))
        raw=response.json();choice=raw['choices'][0];text=choice['message'].get('content') or ''
        if not text.strip() or choice.get('finish_reason')=='length':raise ValueError('완성된 모델 응답을 받지 못했습니다.')
        if self._key in text:raise ValueError('비밀 값이 포함된 응답을 거부했습니다.')
        record={'step':step.value,'system':prompt.system,'user':prompt.user,'response':text,
                'estimated_input_tokens_without_chat_template':estimated,'usage':raw.get('usage',{}),'finish_reason':choice.get('finish_reason'),
                'started_at':started_at,'ended_at':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-start,3),
                'returned_model':raw.get('model'),'provider':raw.get('provider')}
        with self.lock:self.calls[fingerprint]=record;self.save()
        return text
