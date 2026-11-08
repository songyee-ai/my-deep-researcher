const clamp = n => Math.max(0, Math.min(1, n));

// Work labels follow recorded events, independently of the costume animation.
export function workStatusAt(events,time,agent){
  let status='대기 중';
  const starting={plan:'기획 중',read:'자료 읽는 중',pick:'다음 자료 선택 중',write:'원고 작성 중',edit:'보고서 정리 중'};
  const arrived={plan:'기획 확인 중',read:'자료 읽음',pick:'자료 선택 확인 중',write:'원고 확인 중',edit:'보고서 확인 중'};
  for(const event of events){
    if(event.agent!==agent||!(event.displayTime<=time+.000001))continue;
    if(event.kind==='call_start')status=starting[event.step]||'작업 중';
    else if(event.kind==='call_end')status=arrived[event.step]||'응답 도착';
    else if(event.kind==='call_error')status='오류';
    else if(event.kind==='assignment')status='조사 중';
    else if(event.kind==='read')status='자료 읽음';
    else if(event.kind==='plan')status='기획 완료';
    else if(event.kind==='section')status='원고 제출';
    else if(event.kind==='report')status='보고서 완성';
  }
  return status;
}

// Derive the costume from the playback clock, never from an animation timeout.
// Rewinding, pausing, and selecting another researcher therefore preserve it.
export function transformationAt(events, time, agent, budget=3) {
  const lane = events.filter(e => e.agent === agent);
  const past = lane.filter(e => e.displayTime <= time + .000001);
  const completed = past.find(e => e.kind === (agent === 'moon' ? 'plan' : 'section'));
  const first = past.find(e => e.kind === 'call_start' || e.kind === 'assignment');
  if (!first) return {progress:0, outfit:'school', phase:'대기 중', active:false, completedAt:null};
  if (completed) return {progress:1, outfit:'guardian', phase:'조사 완료', active:false, completedAt:completed.displayTime};
  const call = past.findLast(e => e.kind === 'call_start');
  const end = call && lane.find(e => e.call_id === call.call_id && (e.kind === 'call_end' || e.kind === 'call_error'));
  const fraction = call ? (end ? clamp((time-call.displayTime)/Math.max(.001,end.displayTime-call.displayTime)) : 1-Math.exp(-Math.max(0,time-call.displayTime)/4)) : 0;
  const readDone = past.filter(e => e.kind === 'call_end' && e.step === 'read').length;
  let progress = .08;
  if (agent === 'moon') progress = .08 + fraction*.88;
  else if (call?.step === 'write') progress = .64 + fraction*.34;
  else progress = .10 + Math.min(1,(readDone + (call?.step==='read' && !past.some(e=>e.call_id===call.call_id && e.kind==='call_end') ? fraction : 0))/Math.max(1,budget))*.50;
  progress = clamp(progress);
  return {progress, outfit:progress>=.72?'guardian':'school', phase:progress<.35?'자료 모으는 중':progress<.93?'원고 쓰는 중':'마무리 중', active:true, completedAt:null};
}
