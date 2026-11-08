// Presentation only: keep every character of the saved report, including source IDs.
export function reportParts(value){
  const text=String(value??''),parts=[];
  let start=0;
  for(const match of text.matchAll(/(?<![A-Za-z0-9_/])D[0-9]+(?![A-Za-z0-9_])/g)){
    if(match.index>start)parts.push({text:text.slice(start,match.index),source:false});
    parts.push({text:match[0],source:true});start=match.index+match[0].length;
  }
  if(start<text.length)parts.push({text:text.slice(start),source:false});
  return parts;
}

let sequence=0;
export function reportView(text,bodyClass='library-body'){
  const wrapper=document.createElement('div');wrapper.className='annotated-report';
  const body=document.createElement('pre');body.className=bodyClass+' report-prose';
  const parts=reportParts(text),hasSources=parts.some(part=>part.source);
  let tooltip,active=null;
  if(hasSources){
    const notice=document.createElement('p');notice.className='internal-source-notice';
    notice.textContent='보고서에 내부 출처 표기가 남아 있어요. 저장된 본문은 그대로 표시합니다.';
    wrapper.append(notice);
    tooltip=document.createElement('div');tooltip.className='internal-source-tooltip';
    tooltip.id=`internal-source-tooltip-${++sequence}`;tooltip.role='tooltip';tooltip.hidden=true;
    tooltip.textContent='내부 출처 표기입니다. 원문 링크를 뜻하지 않습니다.';
  }
  function hide(){if(active)active.setAttribute('aria-expanded','false');active=null;if(tooltip)tooltip.hidden=true;}
  function show(button){
    if(active&&active!==button)active.setAttribute('aria-expanded','false');
    active=button;button.setAttribute('aria-expanded','true');tooltip.hidden=false;
    const root=wrapper.getBoundingClientRect(),rect=button.getBoundingClientRect();
    tooltip.style.left=`${Math.max(0,Math.min(rect.left-root.left,root.width-tooltip.offsetWidth))}px`;
    tooltip.style.top=`${rect.bottom-root.top+6}px`;
  }
  for(const part of parts){
    if(!part.source){body.append(document.createTextNode(part.text));continue;}
    const button=document.createElement('button');button.type='button';button.className='internal-source-mark';button.textContent=part.text;
    button.setAttribute('aria-label',`${part.text} 내부 출처 표기`);button.setAttribute('aria-describedby',tooltip.id);button.setAttribute('aria-expanded','false');
    button.addEventListener('pointerenter',()=>show(button));button.addEventListener('pointerleave',()=>{if(document.activeElement!==button)hide();});
    button.addEventListener('focus',()=>show(button));button.addEventListener('blur',hide);
    // Focus may have opened the balloon before the first touch/click arrives.
    button.addEventListener('click',()=>show(button));
    button.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();hide();}});
    body.append(button);
  }
  wrapper.append(body);if(tooltip)wrapper.append(tooltip);
  return wrapper;
}
