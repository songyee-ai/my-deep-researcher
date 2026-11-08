import {RESEARCHERS} from './team.mjs';
import {reportView} from './report-display.mjs';
const $=id=>document.getElementById(id);
const modal=$('library-modal'), content=$('library-content');
function syncLibraryViewport(){
  const viewport=window.visualViewport;
  modal.style.setProperty('--library-viewport-height',(viewport?.height||window.innerHeight)+'px');
  modal.style.setProperty('--library-viewport-top',(viewport?.offsetTop||0)+'px');
}
syncLibraryViewport();window.addEventListener('resize',syncLibraryViewport);
window.visualViewport?.addEventListener('resize',syncLibraryViewport);window.visualViewport?.addEventListener('scroll',syncLibraryViewport);
let index=null, tab='documents', selectedPlanet='', query='', token=0, activeCorpus='base';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
async function get(path){const r=await fetch(path);const data=await r.json();if(!r.ok)throw Error(data.error||'자료를 열지 못했어요.');return data;}
function button(text,action,cls='library-item'){const b=el('button',text,cls);b.type='button';b.onclick=()=>Promise.resolve(action()).catch(showError);return b;}
function showError(error){content.replaceChildren(el('p',error.message,'library-notice'));}
function sourceButton(title,corpus=activeCorpus){return button(title,()=>openDocument(title,corpus),'source-link');}
function panel(title){const p=el('section',undefined,'library-reading');p.append(el('h3',title));return p;}
function block(title,text,parent,report=false){const d=document.createElement('details');d.append(el('summary',title),report?reportView(text||'기록 없음'):el('pre',text||'기록 없음','library-body'));parent.append(d);}
async function loadCorpus(identifier){
  const current=++token,data=await get('/api/library?corpus='+encodeURIComponent(identifier));
  if(current!==token)return false;
  index=data;activeCorpus=data.corpus_id;
  const versions=data.corpora.map(c=>`${c.id==='base'?'기본':'정식 비교'} ${c.document_count}건`).join(' · ');
  $('library-summary').textContent=`${versions} · 현재 ${data.corpus_label} ${data.document_count}건 · ${data.characters.toLocaleString()}자 · 연결 ${data.links}개 · 모델 호출 없이 열람`;
  return true;
}
async function openDocument(title,corpus=activeCorpus){
  if(!corpus)throw Error('이 실행의 자료 모음을 확인할 수 없어 원문을 연결하지 않았습니다.');
  if(!index||activeCorpus!==corpus){if(!await loadCorpus(corpus))return;}
  query='';selectedPlanet='';setTab('documents');await showDocument(title);
}
async function showDocument(title){
  const current=++token;
  $('library-reader').replaceChildren(el('p','원문을 불러오는 중…'));
  const d=await get('/api/library/document?title='+encodeURIComponent(title)+'&corpus='+encodeURIComponent(activeCorpus));if(current!==token)return;
  const p=panel(d.title);
  p.append(el('p',`${d.corpus_label} · ${d.planet} · ${d.chars.toLocaleString()}자${d.pages?` · PDF ${d.pages}쪽`:''}`,'library-meta'));
  if(d.published_at)p.append(el('p','문서 날짜: '+d.published_at,'library-meta'));
  p.append(el('p','과거 문서의 계획과 실제 관측 결과를 구분해 읽어 주세요.','library-notice'));
  const url=new URL(d.source_url);
  if(['https:','http:'].includes(url.protocol)){const a=el('a','공식 출처에서 열기 ↗','source-link');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';p.append(a);}
  p.append(el('pre',d.body,'library-body'));
  if(d.links.length){p.append(el('h4','이 문서에서 연결된 자료'));for(const title of d.links)p.append(sourceButton(title,d.corpus_id));}
  $('library-reader').replaceChildren(p);
}
function showDocuments(){
  content.replaceChildren();
  const tools=el('div',undefined,'library-tools'), search=el('input');search.type='search';search.placeholder='문서 제목 검색';search.setAttribute('aria-label','자료 제목 검색');search.value=query;
  const corpusField=el('label','열람할 자료 모음','library-corpus-field'),corpusSelect=el('select');
  for(const c of index.corpora){const o=el('option',`${c.label} · ${c.document_count}건`);o.value=c.id;corpusSelect.append(o);}corpusSelect.value=activeCorpus;
  corpusSelect.onchange=()=>{loadCorpus(corpusSelect.value).then(applied=>{if(applied)showDocuments();}).catch(showError);};corpusField.append(corpusSelect);
  const filter=el('select');filter.setAttribute('aria-label','행성 필터');for(const value of ['','수성','금성','화성','목성']){const o=el('option',value||'모든 행성');o.value=value;filter.append(o);}filter.value=selectedPlanet;
  tools.append(corpusField,search,filter);const grid=el('div',undefined,'library-grid'), list=el('div',undefined,'library-list'), reader=el('div');reader.id='library-reader';reader.append(el('p','목록에서 문서를 고르면 원문과 연결 자료가 펼쳐져요.','library-placeholder'));
  function draw(){const rows=index.documents.filter(d=>(!selectedPlanet||d.planet===selectedPlanet)&&d.title.toLowerCase().includes(query.toLowerCase()));list.replaceChildren(el('p',`${rows.length}개 자료`,'library-meta'));for(const d of rows){const b=button('',()=>showDocument(d.title));b.append(el('strong',d.title),el('small',`${d.chars.toLocaleString()}자${d.pages?` · PDF ${d.pages}쪽`:''}`));list.append(b);}}
  search.oninput=()=>{query=search.value;draw();};filter.onchange=()=>{selectedPlanet=filter.value;draw();};draw();grid.append(list,reader);content.append(tools,grid);
}
function showQuestions(){
  content.replaceChildren();const list=el('div',undefined,'library-questions');
  for(const q of index.questions){const p=panel(q.id+' · '+q.kind);p.append(el('h4',q.question),el('p',q.why_divide_or_not),el('p',q.division_expected?'여러 자료를 나눠 조사하는 질문':'한 문서로 답할 수 있는 대조 질문','library-meta'));
    const copy=button('질문 복사',async()=>{await navigator.clipboard.writeText(q.question);copy.textContent='복사했어요';},'source-link');p.append(copy,button('이 질문으로 탐사 준비',()=>{modal.close();window.dispatchEvent(new CustomEvent('planetary-question',{detail:q.question}));},'source-link'));
    const d=el('details');d.append(el('summary','질문 설계에 참고한 자료'));for(const title of q.source_hints)d.append(sourceButton(title,activeCorpus));p.append(d);list.append(p);}
  content.append(el('p','아래는 보유한 행성 탐사 자료 안에서 연구할 질문입니다. 탐사 준비를 누르면 메인 화면에 질문을 옮깁니다. 연구 시작을 눌러야 무료 API를 호출합니다.','library-notice'),list);
}
async function showRun(identifier){
  const current=++token;const run=await get('/api/library/runs/'+identifier);if(current!==token)return;
  const p=panel(run.question);p.append(el('p',`${run.model||'모델 미기록'} · ${run.status==='complete'?'실행 완료 · '+run.quality_status:`실행 미완료${run.http_status?' · HTTP '+run.http_status:''}`}`,'library-meta'),el('p',run.notice,'library-notice'));
  if(run.status==='complete')p.append(button('3D에서 조사 흐름 보기 · 순서 연출',async()=>{try{const record=await get('/api/library/runs/'+identifier+'/playback');modal.close();window.dispatchEvent(new CustomEvent('planetary-playback',{detail:record}));}catch(error){showError(error);}},'source-link'));
  if(run.metrics){const c=run.metrics.counts;p.append(el('p',`읽은 자료 ${c.read_events}건 · 채택 원고 ${c.selected_sections}절 · 보고서 ${c.report_chars.toLocaleString()}자`,'library-meta'));
    block('기계적 경보와 입력량',JSON.stringify({alarms:run.metrics.alarms_expected_zero,contexts:run.metrics.context_by_actor},null,2),p);}
  for(const s of run.sections){const card=panel(`${s.index+1}. ${s.title}`);card.append(el('p',`${RESEARCHERS[s.index]?.name||'연구원 '+(s.index+1)} · ${s.role} · ${s.body.length}자 · ${s.round}차 · 부족 신고 ${s.insufficient?'있음':'없음'}`,'library-meta'),el('p',s.reason));
    card.append(el('h4','실제로 읽은 원문'));for(const title of s.read_documents)card.append(sourceButton(title,'base'));
    block('연구원이 쓴 원고',s.body,card);
    for(const c of s.trace){const names={read:'조사 노트',write:'원고 생성',pick:'다음 자료 선택'};block(names[c.step]+' · 모델 응답',c.response,card);block(names[c.step]+' · 전달한 자료와 지시',c.system+'\n\n'+c.user,card);}
    p.append(card);}
  if(run.review)block('원문까지 추적한 실패 분석',run.review,p);
  if(run.report)block('최종 진단 원고 · 검토 미통과',run.report,p,true);
  $('library-reader').replaceChildren(p);
}
async function showRuns(){
  content.replaceChildren(el('p','저장된 진단 기록을 불러오는 중…'));
  const current=++token,runs=await get('/api/library/runs');if(current!==token)return;
  const grid=el('div',undefined,'library-grid'),list=el('div',undefined,'library-list'),reader=el('div');reader.id='library-reader';reader.append(el('p','기록을 고르면 절마다 읽은 원문·조사 노트·원고를 대조할 수 있어요.','library-placeholder'));
  for(const r of runs){const b=button('',()=>showRun(r.id));b.append(el('strong',r.question),el('small',`${r.id} · ${r.quality_status}${r.http_status?' · HTTP '+r.http_status:''}`));list.append(b);}
  if(!runs.length)list.append(el('p','저장된 진단 기록이 없어요.'));
  grid.append(list,reader);content.replaceChildren(el('p',"이 탭은 기능 진단 기록입니다. 정식 비교 실험은 '비교 실행 결과' 탭에 있어요.",'library-notice'),grid);
}
function setTab(value){
  token++;tab=value;
  for(const b of modal.querySelectorAll('[data-library-tab]')){b.classList.toggle('active',b.dataset.libraryTab===tab);b.setAttribute('aria-selected',String(b.dataset.libraryTab===tab));}
  if(!index&&['documents','questions'].includes(tab)){
    content.replaceChildren(el('p','자료 모음을 불러오는 중…'));
    loadCorpus(activeCorpus).then(applied=>{if(applied&&tab===value)setTab(value);}).catch(showError);return;
  }
  if(tab==='documents')showDocuments();else if(tab==='questions')showQuestions();else if(tab==='comparisons')showComparisons().catch(showError);else showRuns().catch(showError);
}
const statusText={complete:'실행 완료',running:'진행 중',error:'오류',failed:'실패',partial_failure:'일부 실패',stopped:'중단',incomplete:'실행 미완료',unknown:'상태 미확인',aborted:'중단',interrupted:'중단'};
function comparisonState(run){return (statusText[run.status]||'상태 미확인')+(run.stop_reason?' · '+run.stop_reason:'');}
function comparisonCounts(run){return `성공 ${run.completed_rows} · 실패 ${run.errors}${run.expected_rows?' / 예정 '+run.expected_rows+'건':' · 기록 '+run.rows+'건'}`;}
const ALARM_NAMES={unread_document_citations:'읽지 않은 문서 인용',unknown_document_citations:'목록에 없는 문서 인용',attempt_read_budget_excess:'시도별 읽기 예산 초과',total_read_budget_excess:'전체 읽기 예산 초과',missing_planned_sections:'계획한 절 누락',short_selected_sections:'분량 부족 절',synthesis_lost_section_bodies:'종합 중 절 본문 유실'};
function conditionDescription(run,parent){
  if(!run.condition_description)return;
  const d=el('details');d.open=true;d.append(el('summary','이 조건의 의미'),el('p',run.condition_description,'library-meta'));parent.append(d);
}
function manuscriptPreview(text,parent){
  const body=el('pre',text||'기록 없음','library-body manuscript-preview'),toggle=button('펼치기',()=>{
    const expanded=toggle.getAttribute('aria-expanded')!=='true';
    toggle.setAttribute('aria-expanded',String(expanded));toggle.textContent=expanded?'접기':'펼치기';body.classList.toggle('expanded',expanded);
  },'source-link');toggle.setAttribute('aria-expanded','false');parent.append(body,toggle);
}
function stopReason(reason){return {model_stop:'추가 열람 종료',candidate_exhausted:'후보 자료 소진'}[reason]||'사유 확인 필요';}
function conditionColumn(run){
  const col=el('section',undefined,'compare-column'+(run.alarms.length?' has-alarm':''));
  col.append(el('h3',run.condition_label));
  conditionDescription(run,col);
  col.append(el('p',statusText[run.status]||'상태 미확인','library-meta'));
  block('기술 정보',JSON.stringify({실행ID:run.id,엔진:run.engine_class,호출기록:run.transport_stats,오류종류:run.error_type,읽기종료:run.stop_events,예산검증:run.baseline_validation},null,2),col);
  if(run.status!=='complete'){col.append(el('p','이 실행은 완성된 보고서가 없습니다. 오류 종류만 기록되어 있어요.','library-notice'));return col;}
  if(run.alarms.length)col.append(el('p','경보 '+run.alarms.length+'건: '+run.alarms.map(a=>ALARM_NAMES[a]||a).join(', '),'compare-alarm'));
  else col.append(el('span','경보 0','compare-alarm-badge'));
  const bv=run.baseline_validation;
  if(bv){const box=el('div',undefined,'compare-baseline'+(bv.full_budget_used?'':' underused'));
    box.append(el('strong','단일형 읽기 예산 검증'),el('p',`배정 예산 ${bv.granted_read_budget}건 · 열람 ${bv.actual_reads}회 · 예산 ${bv.full_budget_used?'모두 소진':'미소진 (남은 '+bv.unused_budget+'건)'}`),el('p','읽기 종료 사유: '+((bv.stopping_reasons||[]).map(stopReason).join(', ')||'기록 없음')));col.append(box);}
  if(run.plan_title)col.append(el('h4',run.plan_title));
  for(const s of run.sections){const card=el('div',undefined,'compare-section');
    const agent=RESEARCHERS.find(a=>a.id===s.agent)?.name||'연구원 '+(s.index+1);
    card.append(el('strong',`${s.index+1}. ${s.title}`),el('p',`담당 ${agent} · ${s.role||'역할 없음'} · ${(s.body||'').length}자 · ${s.round}차`,'library-meta'),
      el('p',`부족 신고: ${s.insufficient?'있음':'없음'}${s.reason?' — '+s.reason:''}`,s.insufficient?'compare-alarm':'library-meta'));
    card.append(el('h4','읽은 문서'));if(!s.read_documents.length)card.append(el('p','기록 없음','library-meta'));
    for(const title of s.read_documents)card.append(sourceButton(title,run.corpus_id));
    card.append(el('h4','원고 본문 (채택된 절)'));manuscriptPreview(s.body,card);col.append(card);}
  if(run.stop_events.length)col.append(el('p','읽기 종료: '+run.stop_events.map(e=>stopReason(e.reason)).join(' / '),'library-meta'));
  block('최종 보고서',run.report,col,true);
  return col;
}
async function showComparePair(folder,rows,reader,title){
  const p=panel(title);p.append(button('질문별 요약으로',()=>showComparison(folder,reader),'source-link'),el('p','같은 질문·같은 반복의 결과입니다. 기계적 경보 0은 내용 정확성을 보장하지 않습니다. 원문과 원고를 직접 대조해 주세요.','library-notice'));
  const choices=el('fieldset',undefined,'compare-choices');choices.append(el('legend','비교할 조건'));
  const selected=new Set(rows.filter(r=>['basic','single_agent'].includes(r.condition)).map(r=>r.id));
  if(!selected.size)for(const r of rows.slice(0,2))selected.add(r.id);
  const viewport=el('div',undefined,'compare-viewport'),grid=el('div',undefined,'compare-grid'),cache=new Map();viewport.append(grid);
  async function draw(){
    const current=++token,picked=rows.filter(r=>selected.has(r.id));
    if(!picked.length){grid.replaceChildren(el('p','비교할 조건을 하나 이상 선택해 주세요.','library-meta'));return;}
    grid.replaceChildren(el('p','보고서를 불러오는 중…'));grid.style.setProperty('--cols',picked.length);
    try{
      const runs=await Promise.all(picked.map(r=>{if(!cache.has(r.id))cache.set(r.id,get(`/api/library/comparisons/${folder}/${r.id}`).catch(error=>{cache.delete(r.id);throw error;}));return cache.get(r.id);}));
      if(current!==token)return;grid.replaceChildren(...runs.map(conditionColumn));
    }catch(error){if(current===token)grid.replaceChildren(el('p',error.message,'library-notice'));}
  }
  for(const r of rows){const label=el('label'),input=el('input');input.type='checkbox';input.checked=selected.has(r.id);input.onchange=()=>{if(input.checked)selected.add(r.id);else selected.delete(r.id);draw();};label.append(input,el('span',r.condition_label));choices.append(label);}
  p.append(choices,viewport);reader.replaceChildren(p);await draw();
}
async function showComparison(folder,reader){
  const current=++token;const d=await get('/api/library/comparisons/'+folder);if(current!==token)return;
  const p=panel(d.display_title);p.append(el('p',d.id,'library-meta'),el('p',`${d.scope_label} · ${comparisonState(d)} · ${comparisonCounts(d)} · 공통 읽기 예산 ${d.shared_read_budget??'?'}건`,'library-meta'),el('p',d.principle,'library-notice'));
  for(const doc of d.review_documents||[])block(doc.label,doc.body,p);
  if(d.status==='running')p.append(el('p','아직 진행 중인 실행입니다. 끝난 행만 보여요.','library-notice'));
  if(d.status==='stopped')p.append(el('p','전체 실행이 끝나기 전에 중단된 기록입니다. 현재 저장된 성공·실패 행만 표시합니다.','library-notice'));
  if(d.status==='incomplete')p.append(el('p','예정된 결과가 모두 기록되지 않았습니다. 전체 완료로 판단하지 않습니다.','library-notice'));
  if(d.all_failed)p.append(el('p','모든 행이 오류로 끝난 실패 기록입니다.','library-notice'));
  const groups=new Map();for(const r of d.rows_detail){const k=r.question_id+'|'+r.repeat;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
  const q=Object.fromEntries(d.questions.map(x=>[x.id,x.question]));
  for(const [k,rows] of groups){const [qid,rep]=k.split('|');const card=panel(`${qid} · ${rep}번째 반복`);card.append(el('p',q[qid]||'','library-meta'));
    const scroll=el('div',undefined,'comparison-summary-scroll'),table=el('table',undefined,'comparison-summary-table');table.setAttribute('aria-label',`${qid} ${rep}번째 반복 조건별 요약`);
    const head=el('thead'),headRow=el('tr');
    for(const title of ['조건','절 수','보고서 글자','열람 횟수','서로 다른 자료','처음 부족 신고 절','중복 읽기 비율','단일형 예산']){const th=el('th',title);th.scope='col';headRow.append(th);}head.append(headRow);table.append(head);
    const body=el('tbody'),number=v=>v===null||v===undefined?'—':v.toLocaleString();
    for(const r of rows){
      const tr=el('tr'),label=el('th',r.condition_label);label.scope='row';
      label.append(el('div',`${statusText[r.status]||'상태 미확인'}${r.alarms.length?' · 경보 '+r.alarms.length+'건':''}`,r.alarms.length?'compare-alarm':'library-meta'));conditionDescription(r,label);tr.append(label);
      const s=r.statistics||{},budget=r.condition==='single_agent'?(s.baseline_full_budget_used===true?'소진':s.baseline_full_budget_used===false?'미소진':'—'):'—';
      for(const value of [number(s.sections),number(s.report_chars),s.read_events==null?'—':number(s.read_events)+'회',s.unique_read_documents==null?'—':number(s.unique_read_documents)+'건',number(s.initial_insufficient_sections),s.duplicate_read_fraction==null?'—':(s.duplicate_read_fraction*100).toFixed(1)+'%',budget])tr.append(el('td',value));
      body.append(tr);
    }
    table.append(body);scroll.append(table);card.append(scroll,el('p','열람 횟수는 다시 읽은 경우를 포함합니다. 서로 다른 자료 수는 중복을 뺀 수입니다. —는 기록 없음 또는 해당 없음입니다.','library-meta'));
    const done=rows.filter(r=>r.status==='complete');
    if(done.length)card.append(button('조건 선택해 나란히 보기',()=>showComparePair(folder,done,reader,`${qid} · ${rep}번째 반복`),'source-link'));
    else card.append(el('p','완료된 보고서가 없어 나란히 볼 수 없어요.','library-meta'));
    p.append(card);}
  if(!groups.size)p.append(el('p','아직 기록된 행이 없어요.'));
  reader.replaceChildren(p);
}
async function showComparisons(){
  content.replaceChildren(el('p','비교 실행 목록을 불러오는 중…'));
  const current=++token,list=await get('/api/library/comparisons');if(current!==token)return;
  const grid=el('div',undefined,'library-grid'),side=el('div',undefined,'library-list'),reader=el('div');reader.id='library-reader';reader.append(el('p','실행을 고르면 질문·반복별로 조건 결과를 나란히 볼 수 있어요.','library-placeholder'));
  for(const c of list){const b=button('',()=>showComparison(c.id,reader));b.append(el('strong',c.display_title),el('small',c.id),el('small',`${comparisonState(c)} · ${comparisonCounts(c)}`));side.append(b);}
  if(!list.length)side.append(el('p','저장된 비교 실행이 없어요.'));
  grid.append(side,reader);content.replaceChildren(el('p','비교 실행의 성공·실패·진행 중 기록을 모두 보여 줍니다. 지표는 명백한 실패를 거르는 용도이며 순위표가 아니에요.','library-notice'),grid);
}

async function openLibrary(preferredTab){
  if(!modal.open)modal.showModal();
  if(preferredTab){
    tab=preferredTab;
    for(const b of modal.querySelectorAll('[data-library-tab]')){b.classList.toggle('active',b.dataset.libraryTab===tab);b.setAttribute('aria-selected',String(b.dataset.libraryTab===tab));}
  }
  content.replaceChildren(el('p','탐사 자료실을 여는 중…'));
  try{if(await loadCorpus(activeCorpus))setTab(tab);}catch(e){showError(e);}
}
$('library-open').onclick=()=>openLibrary();
$('comparison-open').onclick=()=>openLibrary('comparisons');
get('/api/library/comparisons').then(items=>{
  const complete=items.find(item=>item.scope==='FORMAL_COMPARISON'&&item.status==='complete');
  if(complete)$('saved-comparison-summary').textContent=complete.display_title+' · 키 없이 열람';
}).catch(()=>{});
$('library-close').onclick=()=>{token++;modal.close();};
for(const b of modal.querySelectorAll('[data-library-tab]'))b.onclick=()=>setTab(b.dataset.libraryTab);

window.addEventListener('planetary-document',async e=>{modal.showModal();try{await openDocument(e.detail,'base');}catch(error){showError(error);}});
