import {buildPlayback, indexAtTime} from './playback.mjs';
import {transformationAt,workStatusAt} from './transformation.mjs?v=20261108-b1';
import {AGENTS,teamSize} from './team.mjs?v=20261108-heart';
import {reportView} from './report-display.mjs';
import {crystalAt} from './crystal.mjs';
const $ = id => document.getElementById(id);
let state={legacy:null,run:null,view:[],time:0,index:0,selected:'moon',tab:'activity',playing:false,docs:[],plan:null};
let scene=null, timer=null, pollTimer=null, shownError='';
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message){$('toast').textContent=message;$('toast').classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.add('hidden'),6500);}
async function api(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await response.json();if(!response.ok)throw Error(data.error||'연결을 확인해 주세요.');return data;}
const visibleEvents=()=>state.view.slice(0,state.index+1);
function snapshot(){
  const events=visibleEvents(), agents=Object.fromEntries(AGENTS.map(a=>[a.id,{status:'대기 중',label:'별빛을 모을 준비 중',calls:0,documents:[],task:null,section:null,review:null,pending:false}]));
  let plan=null,report='';
  for(const e of events){const a=agents[e.agent];if(!a)continue;
    if(e.kind==='call_start'){a.status='연구 중';a.label=e.label;a.pending=true;a.calls++;if(e.step==='read'){const m=e.user.match(/^\[문서: (.+)\]/);if(m&&!a.documents.includes(m[1]))a.documents.push(m[1]);}}
    if(e.kind==='call_end'){a.pending=false;a.status='응답 도착';a.label=e.label+' 완료';}
    if(e.kind==='call_error'){a.pending=false;a.status='오류';a.label='호출을 확인해 주세요';}
    if(e.kind==='read')a.label='원문 읽기 완료';
    if(e.kind==='plan'){plan=e.plan;a.status='배치 완료';a.label=`연구원 ${e.plan.목차.length}명 배치`;}
    if(e.kind==='assignment'){a.task=e.task;a.status='조사 중';a.label=e.task.절;}
    if(e.kind==='section'){a.section=e.section;a.status='원고 완성';a.label=`${e.section.본문.length.toLocaleString()}자 원고 완성`;}
    if(e.kind==='read'&&!a.documents.includes(e.document))a.documents.push(e.document);
    if(e.kind==='review')a.review=e;
    if(e.kind==='report'){report=e.report;a.status='완성';a.label='우리의 보고서가 도착했어요';}
  }
  if(state.time >= (state.view.at(-1)?.displayTime||0) && (state.run?.status==='stopped'||state.run?.status==='error')){for(const a of Object.values(agents)){if(a.pending){a.pending=false;a.status=state.run.status==='stopped'?'중지됨':'오류';}}}
  for(const agent of AGENTS){
    agents[agent.id].workStatus=['중지됨','오류'].includes(agents[agent.id].status)?agents[agent.id].status:workStatusAt(state.view,state.time,agent.id);
    if(agent.id!=='crystal')agents[agent.id].transformation=transformationAt(state.view,state.time,agent.id,state.run?.settings?.budget||3);
  }
  return {events,agents,plan,report,crystal:crystalAt(state.view,state.time),time:state.time,playing:state.playing,researcherCount:teamSize(state.run,$('sections').value)};
}
function chooseAgent(id){state.selected=id;render();}
for(const agent of AGENTS){const button=document.createElement('button');button.className='agent-chip';button.style.setProperty('--c',agent.color);button.textContent=`${agent.symbol} ${agent.name}`;button.addEventListener('click',()=>chooseAgent(agent.id));button.dataset.agent=agent.id;$('agent-picker').append(button);}
function box(title,text){return `<div class="detail-label">${escapeHTML(title)}</div><pre class="detail-box">${escapeHTML(text)}</pre>`;}
function renderDetails(snap){
  const agent=AGENTS.find(a=>a.id===state.selected),a=snap.agents[agent.id],agentEvents=snap.events.filter(e=>e.agent===agent.id);
  $('agent-name').textContent=agent.name;
  $('agent-role').textContent=a.task?`${a.task.역할} · ${a.task.절}`:agent.role;
  $('agent-avatar').textContent=agent.symbol;$('agent-avatar').style.color=agent.color;
  $('agent-avatar').style.background=agent.color+'18';$('agent-status').textContent=a.workStatus;
  const call=[...agentEvents].reverse().find(e=>e.kind==='call_start');
  const end=call?agentEvents.find(e=>e.call_id===call.call_id&&e.kind==='call_end'):null;
  const error=call?agentEvents.find(e=>e.call_id===call.call_id&&e.kind==='call_error'):null;
  if(state.tab==='prompt'){
    $('detail').innerHTML=call?`<span class="step-pill">${escapeHTML(call.label)} · 입력 ${call.input_chars.toLocaleString()}자</span>${box('시스템 프롬프트',call.system)}${box('사용자 프롬프트',call.user)}${call.sent_user_chars<call.user.length?'<p class="detail-hint">원본 모델의 60,000자 제한에 따라 사용자 프롬프트 앞부분만 전송됩니다.</p>':''}`:'<p class="detail-hint">호출이 시작되면 실제 사용한 프롬프트가 여기에 표시돼요.</p>';
  }else if(state.tab==='response'){
    $('detail').innerHTML=error?box('호출 오류',error.error):end?box(`${end.label} · 모델 응답`,end.response):'<p class="detail-hint">이 시점에는 아직 도착한 응답이 없어요.<br>다음 단계로 이동해 보세요.</p>';
  }else{
    let html=`<div class="detail-label">작업 상태</div><span class="step-pill">${escapeHTML(a.workStatus)}</span>`;
    if(a.transformation)html+=`<div class="transformation-note"><span>${agent.symbol} ${escapeHTML(a.transformation.phase)}</span><b>${Math.round(a.transformation.progress*100)}%</b><div class="transformation-meter"><i style="width:${a.transformation.progress*100}%;background:${agent.color}"></i></div></div>`;
    const mission=a.task?.지시||(agent.id==='moon'?'질문을 읽고 목차를 나눈 다음, 각 행성 연구원에게 서로 다른 시작 자료를 배정해요.':agent.id==='crystal'?'모든 연구원이 원고를 마치면 머리말과 맺음말을 쓰고 하나의 보고서로 엮어요.':'배정받은 자료를 읽고, 다음 문서를 골라 근거가 있는 원고를 써요.');
    html+=`<div class="detail-label">지금의 작은 임무</div><div class="detail-box">${escapeHTML(mission)}</div>`;
    if(agent.id==='moon'&&snap.plan){html+='<div class="detail-label">함께 찾을 이야기</div>'+snap.plan.목차.map((item,i)=>`<div class="doc-entry">${i+1}. ${escapeHTML(item.절)}<span>${escapeHTML(item.역할)}</span></div>`).join('');}
    if(a.documents.length)html+='<div class="detail-label">읽은 자료</div>'+a.documents.map(d=>`<div class="doc-entry">${state.run?.domain==='planetary'?`<button class="source-link" data-source="${escapeHTML(d)}">✧ ${escapeHTML(d)}</button>`:`✧ ${escapeHTML(d)}`}</div>`).join('');
    if(a.review)html+=box('원고 점검 · 재조사 / 보존',`${a.review.redispatch?'부족 절 재조사':a.review.accepted?'이번 원고 채택':'이전 원고 보존'} · ${({'valid nonregressing draft':'분량·인용 검사 충족; 인용 자료 수 유지','provisional draft with validation warnings':'분량 또는 인용 경보가 남은 임시 채택본','kept previous draft; revision lost validity or cited-source breadth':'수정본의 분량·인용 조건 또는 인용 자료 수가 줄어 이전 원고 보존'})[a.review.reason]||a.review.reason}`);
    if(a.section)html+=box('이번 조사 원고 · 최종 채택 여부는 점검 기록 참고',a.section.본문);
    if(!agentEvents.length)html+='<p class="detail-hint"><span class="moon-quote">작은 빛도, 함께 모이면 반짝여요.</span>캐릭터를 클릭해 연구원의 활동을 살펴보세요. 프롬프트와 응답은 선택한 재생 시점을 따라 표시돼요.</p>';
    html+=`<div class="detail-label">이 시점까지 모델 호출</div><span class="step-pill">${state.run?.mode==='planetary_trace'?'호출 기록 미복원':a.calls+'회'}</span>`;
    $('detail').innerHTML=html;
    for(const b of $('detail').querySelectorAll('[data-source]'))b.onclick=()=>window.dispatchEvent(new CustomEvent('planetary-document',{detail:b.dataset.source}));
  }
}
function renderLogs(snap){
  if(!state.run){$('logs').innerHTML='<div class="empty-diary"><span>☾</span><p>새로운 연구를 준비했어요.<br>질문을 입력하고 시작해 보세요.</p></div>';return;}
  $('logs').innerHTML=snap.events.map((e,i)=>{const a=AGENTS.find(a=>a.id===e.agent)||AGENTS[0];const sub=e.kind==='call_start'?`입력 ${e.input_chars.toLocaleString()}자`:e.kind==='call_end'?`응답 ${e.output_chars.toLocaleString()}자`:e.task?.절||e.summary||'';return `<button class="log-item ${i===state.index?'active':''}" data-event="${i}" style="--agent-color:${a.color}"><time title="원본 기록 ${e.t}초 · ${['replay','planetary_trace'].includes(state.run.mode)?'순서 연출':'실제'} 재생 시각">${e.displayTime.toFixed(1)}s</time><span><strong>${escapeHTML(a.name)}</strong> · ${escapeHTML(e.label)}<span class="log-sub">${escapeHTML(sub)}</span></span></button>`;}).join('');
  for(const button of $('logs').querySelectorAll('button'))button.onclick=()=>{pause();state.selected=state.view[+button.dataset.event].agent;seek(+button.dataset.event);};
  if(!state.playing||state.index%2===0)$('logs').scrollTop=$('logs').scrollHeight;
}
function renderClock(){
  const seconds=state.time;
  $('timeline').max=Math.max(0,Math.round((state.view.at(-1)?.displayTime||0)*1000));$('timeline').value=Math.round(seconds*1000);
  $('elapsed').textContent=`${['replay','planetary_trace'].includes(state.run?.mode)?'연출':'기록'} ${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toFixed(1).padStart(4,'0')}`;
  const snap=snapshot();scene?.update(snap,state.selected);
  const trans=snap.agents[state.selected]?.transformation;
  if(trans){
    const note=$('detail').querySelector('.transformation-note');
    if(note){note.querySelector('b').textContent=`${Math.round(trans.progress*100)}%`;note.querySelector('i').style.width=`${trans.progress*100}%`;note.querySelector('span').textContent=`${AGENTS.find(a=>a.id===state.selected).symbol} ${trans.phase}`;}
  }
  $('agent-status').textContent=snap.agents[state.selected].workStatus;
}
function render(){
  const count=teamSize(state.run,$('sections').value);
  if(state.selected.startsWith('researcher-')&&Number(state.selected.split('-')[1])>=count)state.selected='moon';
  const snap=snapshot(),total=state.view.length,current=state.view[state.index];
  $('event-count').textContent=total;renderClock();
  $('progress').textContent=`${total?state.index+1:0} / ${total} 단계`;
  $('play-label').textContent=current?`${AGENTS.find(a=>a.id===current.agent)?.name||''} · ${current.label}`:'시간을 따라 연구를 살펴보세요';
  const running=state.run?.status==='running';
  $('run').disabled=running;$('stop').classList.toggle('hidden',!running);$('status-dot').classList.toggle('live',running);
  const reviewing=state.run?.status==='complete'&&state.time<(state.view.at(-1)?.displayTime||0);
  const status=running?'행성 연구원들이 조사하고 있어요':reviewing?(state.playing?'병렬 연구 흐름을 재생해요':'연구 기록을 살펴보고 있어요'):state.run?.status==='complete'?'오늘의 연구를 마쳤어요':state.run?.status==='stopped'?'연구를 멈췄어요':state.run?.status==='error'?'연구 중 오류가 발생했어요':'새로운 연구를 기다려요';
  const concurrent=Object.entries(snap.agents).filter(([id,a])=>id.startsWith('researcher-')&&a.pending).length;
  $('status-text').textContent=status;$('stage-state').textContent=concurrent?`${concurrent}명 ${concurrent>1?'동시 ':''}조사 중`:running?'별빛을 모으는 중':state.playing?'연구 기록을 따라가는 중':snap.report?'보고서 완성':'연구 준비 완료';
  $('mode-badge').textContent=state.run?(state.run.mode==='planetary_trace'?'저장 진단 · 순서 연출 · 실제 시간 아님':state.run.mode==='replay'?'연출 시간 · 무료':state.run.domain==='planetary'?'행성 탐사 · 기능 진단':'역사 자료 · 기록 시간'):'READY';
  const calls=snap.events.filter(e=>e.kind==='call_start'),ends=snap.events.filter(e=>e.kind==='call_end');
  $('metric-calls').textContent=calls.length;$('metric-chars').textContent=`${calls.reduce((n,e)=>n+e.input_chars,0).toLocaleString()} / ${ends.reduce((n,e)=>n+e.output_chars,0).toLocaleString()}`;
  if(state.run?.mode==='planetary_trace'){$('metric-calls').textContent='미복원';$('metric-chars').textContent='미복원';}
  $('metric-cost').textContent=state.run&&['live','planetary'].includes(state.run.mode)?(state.run.free_only?'무료 모델':'제공자 내역에서 확인'):'발생 없음';
  $('report-open').disabled=!snap.report;$('report-status').textContent=snap.report?`${snap.report.length.toLocaleString()}자 · ${state.run?.quality_warnings?.length?'내용 검토 필요':'보고서 도착'}`:'이야기가 모이면 여기에 도착해요';
  $('export').disabled=!state.run;
  for(const b of $('agent-picker').children){b.classList.toggle('active',b.dataset.agent===state.selected);b.hidden=b.dataset.agent.startsWith('researcher-')&&Number(b.dataset.agent.split('-')[1])>=count;}
  const budget=state.run?.settings?.budget||+$('budget').value;
  $('team-summary').textContent=`${state.run?'이 기록의':'준비된'} 리서처 ${count}명 · 회당 1인 최대 ${budget}문서`;
  $('team-summary').title='리서처 수는 최대 인원이며 실제 목차에 따라 줄어들 수 있습니다.'+(state.legacy?.team_note||'');
  document.querySelector('.stage').classList.toggle('expanded-team',count>4);
  renderLogs(snap);renderDetails(snap);scene?.update(snap,state.selected);
}
function seekTime(seconds){state.time=Math.max(0,Math.min(seconds,state.view.at(-1)?.displayTime||0));state.index=indexAtTime(state.view,state.time);render();}
function seek(index){const target=state.view[Math.max(0,Math.min(index,state.view.length-1))];seekTime(target?.displayTime||0);}
function setPlayIcon(playing){const label=playing?'일시정지':'재생';$('play-icon-path').setAttribute('d',playing?'M8 5v14M16 5v14':'m8 5 10 7-10 7V5Z');$('play').setAttribute('aria-label',label);$('play').title=label;}
function pause(){state.playing=false;clearTimeout(timer);setPlayIcon(false);}
function play(){
  if(!state.view.length)return;
  if(state.time>=state.view.at(-1).displayTime){state.time=0;state.index=indexAtTime(state.view,0);}
  state.playing=true;setPlayIcon(true);
  let previous=performance.now();render();
  function tick(){if(!state.playing)return;const now=performance.now();state.time=Math.min(state.view.at(-1).displayTime,state.time+(now-previous)/1000*+$('speed').value);previous=now;const index=indexAtTime(state.view,state.time);if(index!==state.index){state.index=index;render();}else renderClock();if(state.time>=state.view.at(-1).displayTime){pause();render();return;}timer=setTimeout(tick,40);}
  tick();
}
async function refreshHistory(){const runs=await api('/api/runs');$('history').innerHTML='<option value="">이번 연구의 발자취</option>'+runs.map(r=>`<option value="${r.id}">${escapeHTML(new Date(r.created).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}))} · ${r.mode==='planetary'?'행성 탐사 진단':(state.legacy?.history?.[r.mode]||'이전 기록')} · ${escapeHTML(r.question)}</option>`).join('');if(state.run)$('history').value=state.run.id;return runs;}
async function poll(id){
  clearTimeout(pollTimer);
  try{state.run=await api(`/api/runs/${id}`);state.view=buildPlayback(state.run);seek(state.view.length-1);
    if(state.run.status==='running'){pollTimer=setTimeout(()=>poll(id),450);}else{await refreshHistory();if(state.run.error&&shownError!==id){shownError=id;toast(state.run.error);}if(state.run.save_error)toast(state.run.save_error);if(state.run.mode==='replay'&&state.run.status==='complete'){seek(0);play();}}
  }catch(e){toast(e.message);pollTimer=setTimeout(()=>poll(id),2500);}
}
$('run').onclick=async()=>{if($('mode').value!=='replay'&&!$('question').value.trim()){toast('연구 질문을 입력해 주세요.');$('question').focus();return;}pause();try{const payload={question:$('question').value,mode:$('mode').value,settings:{max_sections:+$('sections').value,budget:+$('budget').value,use_roles:$('roles').checked,assign_seeds:$('seeds').checked,respect_zones:$('zones').checked,rounds:+$('rounds').value}};const result=await api('/api/run',payload);state.selected='moon';await poll(result.id);}catch(e){toast(e.message);}};
$('stop').onclick=async()=>{try{await api('/api/stop',{});toast('중지를 요청했어요. 진행 중인 API 호출이 끝나면 다음 작업 전에 멈춰요.');}catch(e){toast(e.message);}};
$('mode').onchange=()=>{
  const replay=$('mode').value==='replay',planetary=$('mode').value==='planetary';
  const wasReadOnly=$('question').readOnly;
  $('question').readOnly=replay;
  const legacyNote=id=>(state.legacy?.modes||[]).find(m=>m.id===id)?.note?.replace('{model}',state.apiModel||'무료 모델')||'';
  $('mode-note').textContent=planetary?'새 실행은 OpenRouter 키가 필요하며, 질문과 관련 원문이 OpenRouter로 전송됩니다.':legacyNote($('mode').value);
  $('run').innerHTML=replay?'저장 흐름 재생 <span>↗</span>':'새 연구 시작 <span>↗</span>';
  if(replay&&state.defaultQuestion)$('question').value=state.defaultQuestion;
  else if(wasReadOnly&&$('question').value===state.defaultQuestion)$('question').value='';
};
window.addEventListener('planetary-playback',e=>{pause();clearTimeout(pollTimer);state.run=e.detail;state.view=buildPlayback(state.run);state.selected='moon';$('history').value='';$('mode').value='planetary';$('mode').onchange();$('question').value=state.run.question;seek(0);toast('실제 진단의 이벤트 순서를 연출합니다. 실제 처리 시간과 호출 프롬프트를 복원한 기록은 아닙니다.');});
window.addEventListener('planetary-question',e=>{$('mode').value='planetary';$('mode').onchange();$('question').value=e.detail;$('question').focus();});
$('settings-open').onclick=()=>$('settings').showModal();
function prepareTeam(){
  if(state.run?.status==='running'){toast('변경한 설정은 다음 연구에 적용돼요. 진행 중인 연구의 인원은 유지합니다.');return;}
  pause();clearTimeout(pollTimer);state.run=null;state.view=[];state.time=0;state.index=-1;
  $('history').value='';render();
}
$('sections').onchange=prepareTeam;$('budget').onchange=prepareTeam;
$('first').onclick=()=>{pause();seek(0);};$('prev').onclick=()=>{pause();let i=state.index;while(i>=0&&state.view[i]?.displayTime>=state.time-.000001)i--;seek(i);};$('next').onclick=()=>{pause();seek(state.index+1);};$('last').onclick=()=>{pause();seek(state.view.length-1);};$('play').onclick=()=>{if(state.playing){pause();render();}else play();};$('timeline').oninput=()=>{pause();seekTime(+$('timeline').value/1000);};
$('history').onchange=async()=>{if(!$('history').value)return;pause();clearTimeout(pollTimer);try{state.run=await api(`/api/runs/${$('history').value}`);$('question').value=state.run.question;state.view=buildPlayback(state.run);state.selected='moon';seek(state.view.length-1);if(state.run.status==='running')poll(state.run.id);}catch(e){toast(e.message);}};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;for(const tab of document.querySelectorAll('[data-tab]')){tab.classList.toggle('active',tab===b);tab.setAttribute('aria-selected',String(tab===b));}renderDetails(snapshot());});
function download(content,name,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export').onclick=()=>download(JSON.stringify(state.run,null,2),`moonlight-${state.run.id}.json`,'application/json;charset=utf-8');
$('report-open').onclick=()=>{const snap=snapshot();$('report-content').replaceChildren(reportView(snap.report,'report-modal-body'));const meta=state.run.mode!=='replay'?`${state.run.domain==='planetary'?'행성 탐사 기능 진단 · 내용 미검증':'역사 자료 실제 API'} · ${state.run.question}`:(state.legacy?.report_meta_replay||'');$('report-meta').textContent=meta+(state.run.quality_warnings?.length?` · 내용 검토 필요: ${state.run.quality_warnings.join(' / ')}`:'');$('report-modal').showModal();};
$('report-close').onclick=()=>$('report-modal').close();$('report-download').onclick=()=>download(snapshot().report,'달빛_연구보고서.md','text/markdown;charset=utf-8');
$('reset-camera').onclick=()=>scene?.reset();
try{const {createUniverse}=await import('./scene.js?v=20261108-heart3');scene=createUniverse($('universe'),$('labels'),AGENTS,chooseAgent);}catch(e){$('scene-error').classList.remove('hidden');console.error('3D initialization:',e);}
try{const info=await api('/api/status');state.docs=info.docs;state.defaultQuestion=info.default_question;state.planetaryQuestion=info.planetary_question;state.apiModel=info.model;state.legacy=info.legacy;for(const m of [...(info.legacy?.modes||[])].reverse()){const o=document.createElement('option');o.value=m.id;o.textContent=m.label;$('mode').prepend(o);}$('mode').value='planetary';$('settings-note').textContent=info.legacy?.settings_note||'';$('mode').onchange();$('key-state').textContent=info.api_configured?`✓ ${info.provider} 설정됨 · ${info.model}`:(info.legacy?.key_hint||'무료 API 키 미설정 · 프로젝트 폴더의 .env에 OPENROUTER_API_KEY를 넣어 주세요');const runs=await refreshHistory();if(info.active){await poll(info.active);}else if(runs.length){state.run=await api(`/api/runs/${runs[0].id}`);state.view=buildPlayback(state.run);$('history').value=state.run.id;seek(0);}render();}catch(e){toast(e.message);render();}
