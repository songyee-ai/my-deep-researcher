// Playback is a clock, not a delay between adjacent log lines.
// Class replay has instant stub responses: give each researcher an independent
// illustrative lane. Raw timestamps and exported records are never rewritten.
export function buildPlayback(run) {
  const source = run?.events || [];
  if (run?.mode !== 'replay') {
    return source.map((e, sourceIndex) => ({...e, sourceIndex, displayTime: e.t}))
      .sort((a,b) => a.displayTime-b.displayTime || a.sourceIndex-b.sourceIndex);
  }
  const lanes = new Map(), callEnds = new Map();
  let planningEnd = 0, researchEnd = 0;
  const duration = e => {
    if (e.step === 'plan') return 1.7;
    if (e.step === 'read') return 1.5 + Math.min(1.8, (e.input_chars || 0)/15000);
    if (e.step === 'pick') return .8;
    if (e.step === 'write') return 2.5;
    return 1.8;
  };
  const events = source.map((e, sourceIndex) => {
    let t = lanes.get(e.agent) || 0;
    if (e.agent === 'moon') {
      if (e.kind === 'call_start') {t = .4; callEnds.set(e.call_id, t+duration(e));}
      else if (e.kind === 'call_end' || e.kind === 'call_error') t = callEnds.get(e.call_id) ?? t;
      else if (e.kind === 'plan') {t += .15; planningEnd = t;}
    } else if (e.agent?.startsWith('researcher-')) {
      if (e.kind === 'assignment') t = planningEnd + .6;
      else if (e.kind === 'call_start') {t += .15; callEnds.set(e.call_id, t+duration(e));}
      else if (e.kind === 'call_end' || e.kind === 'call_error') t = callEnds.get(e.call_id) ?? t;
      else if (e.kind === 'section') {t += .2; researchEnd = Math.max(researchEnd,t);}
    } else if (e.agent === 'crystal') {
      if (e.kind === 'call_start') {t = researchEnd + .6; callEnds.set(e.call_id,t+duration(e));}
      else if (e.kind === 'call_end' || e.kind === 'call_error') t = callEnds.get(e.call_id) ?? t;
      else if (e.kind === 'report') t += .25;
    }
    lanes.set(e.agent,t);
    return {...e, sourceIndex, displayTime: Math.round(t*1000)/1000};
  });
  return events.sort((a,b) => a.displayTime-b.displayTime || a.sourceIndex-b.sourceIndex);
}

export function indexAtTime(events, seconds) {
  let lo = 0, hi = events.length;
  while (lo < hi) {
    const mid = (lo+hi) >>> 1;
    if (events[mid].displayTime <= seconds + .000001) lo=mid+1;
    else hi=mid;
  }
  return lo-1;
}

export function callIntervals(events) {
  const starts = new Map(), result = [];
  for (const e of events) {
    if (e.kind === 'call_start') starts.set(e.call_id,e);
    else if ((e.kind === 'call_end' || e.kind === 'call_error') && starts.has(e.call_id)) {
      const start = starts.get(e.call_id);
      result.push({agent:e.agent,step:start.step,callId:e.call_id,start:start.displayTime,end:e.displayTime});
    }
  }
  return result;
}
