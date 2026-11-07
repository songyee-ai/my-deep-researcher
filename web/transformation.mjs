const clamp = n => Math.max(0, Math.min(1, n));

// Derive the costume from the playback clock, never from an animation timeout.
// Rewinding, pausing, and selecting another researcher therefore preserve it.
export function transformationAt(events, time, agent, budget=3) {
  const lane = events.filter(e => e.agent === agent);
  const past = lane.filter(e => e.displayTime <= time + .000001);
  const completed = past.find(e => e.kind === (agent === 'moon' ? 'plan' : 'section'));
  const first = past.find(e => e.kind === 'call_start' || e.kind === 'assignment');
  if (!first) return {progress:0, outfit:'school', phase:'교복', active:false, completedAt:null};
  if (completed) return {progress:1, outfit:'guardian', phase:'변신 완료', active:false, completedAt:completed.displayTime};
  const call = past.findLast(e => e.kind === 'call_start');
  const end = call && lane.find(e => e.call_id === call.call_id && (e.kind === 'call_end' || e.kind === 'call_error'));
  const fraction = call ? (end ? clamp((time-call.displayTime)/Math.max(.001,end.displayTime-call.displayTime)) : 1-Math.exp(-Math.max(0,time-call.displayTime)/4)) : 0;
  const readDone = past.filter(e => e.kind === 'call_end' && e.step === 'read').length;
  let progress = .08;
  if (agent === 'moon') progress = .08 + fraction*.88;
  else if (call?.step === 'write') progress = .64 + fraction*.34;
  else progress = .10 + Math.min(1,(readDone + (call?.step==='read' && !past.some(e=>e.call_id===call.call_id && e.kind==='call_end') ? fraction : 0))/Math.max(1,budget))*.50;
  progress = clamp(progress);
  return {progress, outfit:progress>=.72?'guardian':'school', phase:progress<.35?'별빛 수집':progress<.93?'리본 변신':'완성 포즈', active:true, completedAt:null};
}
