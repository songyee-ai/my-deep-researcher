const clamp=n=>Math.max(0,Math.min(1,n));

// Visual progress follows the playback clock. Only a nonempty report completes it.
export function crystalAt(events,time){
  const past=events.filter(e=>e.displayTime<=time+.000001);
  const report=past.find(e=>e.kind==='report'&&e.report?.trim());
  if(report)return {progress:1,complete:true,active:false};
  const call=past.findLast(e=>e.agent==='crystal'&&e.kind==='call_start'&&e.step==='edit');
  // Older illustrative traces have no call intervals. Animate between the last
  // selected section and synthesis, without claiming measured editing progress.
  const recordedReport=events.find(e=>e.agent==='crystal'&&e.kind==='report'&&e.report?.trim());
  const hasEditCalls=events.some(e=>e.agent==='crystal'&&e.kind==='call_start'&&e.step==='edit');
  const lastSection=!hasEditCalls&&recordedReport&&events.filter(e=>e.kind==='section'&&e.displayTime<recordedReport.displayTime).at(-1);
  const start=call?.displayTime??lastSection?.displayTime;
  if(start==null||time<start)return {progress:0,complete:false,active:false};
  const stop=call&&past.find(e=>e.call_id===call.call_id&&['call_end','call_error'].includes(e.kind));
  const end=call?events.find(e=>e.call_id===call.call_id&&['call_end','call_error'].includes(e.kind)):recordedReport;
  const now=stop?.displayTime??time;
  const fraction=end?clamp((now-start)/Math.max(.001,end.displayTime-start)):1-Math.exp(-Math.max(0,now-start)/5);
  return {progress:.08+.88*fraction,complete:false,active:!stop};
}

// One connected faceted surface morphs from a diamond into a heart.
export function crystalVertices(progress){
  const p=clamp(progress),points=32,vertices=[];
  const boundary=(i,scale,z)=>{
    const t=i/points*Math.PI*2,s=Math.sin(t),c=Math.cos(t);
    const r=.58/(Math.abs(s)+Math.abs(c));
    const diamond=[s*r,c*r*1.5,z*.75];
    const heart=[16*s*s*s/18,(13*c-5*Math.cos(2*t)-2*Math.cos(3*t)-Math.cos(4*t))/18+.12,z];
    return diamond.map((v,j)=>(v+(heart[j]-v)*p)*scale);
  };
  const triangle=(a,b,c)=>vertices.push(...a,...b,...c);
  for(let i=0;i<points;i++){
    const a=boundary(i,1,0),b=boundary(i+1,1,0);
    for(const side of [1,-1]){
      const innerA=boundary(i,.55,side*.48),innerB=boundary(i+1,.55,side*.48),center=[0,0,side*.36];
      if(side===1){triangle(center,innerA,innerB);triangle(innerA,a,b);triangle(innerA,b,innerB);}
      else{triangle(center,innerB,innerA);triangle(innerA,b,a);triangle(innerA,innerB,b);}
    }
  }
  return new Float32Array(vertices);
}
