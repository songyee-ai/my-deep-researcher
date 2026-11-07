export const RESEARCHERS = [
  {name:'머큐리',symbol:'☿',color:'#6eafcf',kind:'mercury'},
  {name:'마스',symbol:'♂',color:'#d183a4',kind:'mars'},
  {name:'주피터',symbol:'♃',color:'#7eaf9e',kind:'jupiter'},
  {name:'비너스',symbol:'♀',color:'#ccaa67',kind:'venus'},
  {name:'우라누스',symbol:'♅',color:'#8c9bc8',kind:'uranus'},
  {name:'넵튠',symbol:'♆',color:'#6faaa9',kind:'neptune'},
  {name:'플루토',symbol:'♇',color:'#987d9f',kind:'pluto'},
  {name:'새턴',symbol:'♄',color:'#a99bc5',kind:'saturn'}
].map((a,i)=>({...a,id:`researcher-${i}`,role:`리서처 ${i+1} · 자료 조사`,pos:[0,0,0]}));

export const AGENTS = [
  {id:'moon',name:'세일러문',role:'코디네이터 · 목차와 조사 배치',symbol:'☾',color:'#b18ac8',kind:'moon',pos:[0,2.3,-2.5]},
  ...RESEARCHERS,
  {id:'crystal',name:'문 크리스털',role:'편집자 · 보고서 엮기',symbol:'♢',color:'#c394c0',kind:'crystal',pos:[0,.35,1.4]}
];

export function researcherPositions(count){
  const n=Math.max(1,Math.min(8,Number(count)||4));
  if(n===1)return [[0,0,3.2]];
  if(n===2)return [[-3,0,2.2],[3,0,2.2]];
  if(n===3)return [[-4,0,.4],[0,0,3.3],[4,0,.4]];
  if(n===4)return [[-4,0,0],[-1.7,0,3],[2.2,0,3],[4,0,0]];
  if(n===8)return [[-4.4,0,3.9],[-1.5,0,3.9],[1.5,0,3.9],[4.4,0,3.9],[-4.4,0,-2.3],[-1.5,0,-2.3],[1.5,0,-2.3],[4.4,0,-2.3]];
  return Array.from({length:n},(_,i)=>{const a=Math.PI*2*i/n+(n===6?Math.PI/12:Math.PI/n);return [Math.cos(a)*4.8,0,Math.sin(a)*3.3+.7];});
}

export function teamSize(run, configured=4){
  if(!run)return Math.max(1,Math.min(8,Number(configured)||4));
  const plan=run.events?.find(e=>e.kind==='plan')?.plan;
  if(plan?.목차?.length)return Math.min(8,plan.목차.length);
  const assigned=(run.events||[]).filter(e=>e.kind==='assignment').map(e=>Number(e.agent.split('-')[1])+1);
  return Math.max(1,Math.min(8,assigned.length?Math.max(...assigned):run.settings?.max_sections||configured));
}
