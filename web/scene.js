import * as THREE from './vendor/three.module.js';
import {researcherPositions} from './team.mjs';

export function createUniverse(canvas,labelLayer,agents,onSelect){
  const scene=new THREE.Scene();
  const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.setClearColor(0xffffff,0);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.03;
  const camera=new THREE.PerspectiveCamera(36,1,.1,100);
  let azimuth=0,elevation=.49,distance=19,drag=null,moved=false,selected='moon',snap=null;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const mobile=matchMedia('(max-width: 680px)');
  scene.add(new THREE.HemisphereLight(0xffffff,0xc5b7df,2.3));
  const key=new THREE.DirectionalLight(0xfff4eb,2.2);key.position.set(-5,12,8);key.castShadow=true;key.shadow.mapSize.set(2048,2048);key.shadow.camera.left=-12;key.shadow.camera.right=12;key.shadow.camera.top=12;key.shadow.camera.bottom=-12;key.shadow.bias=-.001;scene.add(key);
  const pink=new THREE.PointLight(0xf9bfe1,20,25);pink.position.set(4,5,4);scene.add(pink);
  const group=new THREE.Group();scene.add(group);
  const material=(color,extra={})=>new THREE.MeshStandardMaterial({color,roughness:.55,metalness:.12,...extra});
  const MAT={white:material('#fff9f2'),skin:material('#ffe7d5'),gold:material('#efcc83',{metalness:.45}),eye:material('#59465c'),pink:material('#e2a6c8'),navy:material('#7e83bb')};
  function mesh(geometry,mat,parent,x=0,y=0,z=0){const m=new THREE.Mesh(geometry,mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
  function ball(parent,mat,x,y,z,sx,sy=sx,sz=sx){const m=mesh(new THREE.SphereGeometry(1,32,24),mat,parent,x,y,z);m.scale.set(sx,sy,sz);return m;}
  function torus(parent,r,t,mat,x,y,z,rotation=0){const m=mesh(new THREE.TorusGeometry(r,t,10,90),mat,parent,x,y,z);m.rotation.x=rotation;return m;}
  function starShape(){const s=new THREE.Shape();for(let i=0;i<10;i++){const a=i*Math.PI/5+Math.PI/2,r=i%2?.43:1;const x=Math.cos(a)*r,y=Math.sin(a)*r;i?s.lineTo(x,y):s.moveTo(x,y);}s.closePath();return s;}
  const starGeo=new THREE.ExtrudeGeometry(starShape(),{depth:.09,bevelEnabled:true,bevelSegments:2,steps:1,bevelSize:.06,bevelThickness:.04});
  function star(parent,x,y,z,size,mat=MAT.gold){const m=mesh(starGeo,mat,parent,x,y,z);m.scale.setScalar(size);return m;}
  function crescent(parent,size){const shape=new THREE.Shape();shape.absarc(0,0,1,Math.PI*.31,Math.PI*1.69,false);shape.quadraticCurveTo(-.55,0,Math.cos(Math.PI*.31),Math.sin(Math.PI*.31));const m=mesh(new THREE.ExtrudeGeometry(shape,{depth:.19,bevelEnabled:true,bevelSize:.07,bevelThickness:.06,bevelSegments:3,steps:1}),MAT.gold,parent);m.scale.setScalar(size);m.rotation.z=-.2;return m;}
  // A small porcelain stage and fine rose-gold planetary orbits.
  const base=mesh(new THREE.CylinderGeometry(6.5,6.7,.24,128),material('#eee0f1',{transparent:true,opacity:.78}),group,0,-.65,.7);base.receiveShadow=true;
  torus(group,6.55,.027,material('#dec4dc'),0,-.48,.7,Math.PI/2);
  for(const [r,c] of [[2.2,'#e4c9df'],[4.3,'#d9c5e6'],[5.6,'#d6c5dd']])torus(group,r,.012,material(c),0,-.49,.7,Math.PI/2);
  for(let i=0;i<70;i++){const a=i*2.39996,r=1.6+((i*37)%100)/100*4.5;const s=star(group,Math.cos(a)*r,-.47,Math.sin(a)*r+.7,.025+(i%3)*.012,material('#dfc3da'));s.rotation.x=-Math.PI/2;}
  const backdrop=new THREE.Group();scene.add(backdrop);
  let seed=48;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  const sparkles=[];
  for(let i=0;i<70;i++){const m=star(backdrop,(random()-.5)*19,random()*8-1,-5-random()*6,.025+random()*.055,material(i%2?'#ddc6e3':'#e9c8d4'));m.rotation.z=random()*Math.PI;sparkles.push(m);}
  for(let i=0;i<7;i++){const m=ball(backdrop,material('#ffffff',{transparent:true,opacity:.5}),(random()-.5)*16,random()*6,-6,.12+random()*.22);sparkles.push(m);}
  function bow(parent,color,y,z,size=.18){const mat=material(color);for(const side of [-1,1]){const wing=ball(parent,mat,side*size*.65,y,z,size,size*.64,size*.36);wing.rotation.z=side*-.4;}ball(parent,MAT.gold,0,y,z+.045,size*.27);}
  function doll(parent,kind,color){
    const doll=new THREE.Group();parent.add(doll);
    const school=new THREE.Group(),guardian=new THREE.Group();doll.add(school,guardian);
    guardian.visible=false;
    const isMoon=kind==='moon';const hairColors={moon:'#f0d48b',mercury:'#7a9fca',mars:'#696080',jupiter:'#ad806c',venus:'#efd18c',uranus:'#d8c591',neptune:'#619a96',pluto:'#526c67',saturn:'#665d80'};
    const hair=material(hairColors[kind]),cloth=material(color),red=material(isMoon?'#df98b8':color);
    const uniform={moon:['#344f95','#d66d83','#faf7ed'],mercury:['#344f95','#d66d83','#faf7ed'],venus:['#344f95','#d66d83','#faf7ed'],mars:['#34443f','#bf6375','#d0d6da'],jupiter:['#666852','#f4e7bd','#f3edda'],uranus:['#495379','#c29b76','#f3f0e9'],neptune:['#395b69','#9fbdb6','#f3f0e9'],pluto:['#574b65','#a87991','#eeebf3'],saturn:['#514766','#aea0c8','#f5f0f8']}[kind];
    const schoolSkirt=material(uniform[0]),schoolBow=uniform[1],schoolTop=material(uniform[2]);
    const shoes=material('#4c4554');
    // Shared head/hair keep the character recognizable in both complete outfits.
    ball(doll,hair,0,1.34,-.045,.56,.56,.43);
    if(['mars','venus','neptune','pluto'].includes(kind)){ball(doll,hair,0,.95,-.19,.53,.75,.28);}
    if(kind==='neptune'){for(const side of [-1,1])for(let i=0;i<3;i++)ball(doll,hair,side*(.45+i%2*.04),1.3-i*.25,-.05,.19,.23,.20);}
    if(kind==='pluto'){ball(doll,hair,.1,1.81,-.14,.20);}
    if(kind==='jupiter'){ball(doll,hair,.47,1.48,-.16,.27,.54,.25);ball(doll,MAT.gold,.36,1.71,-.12,.14);}
    if(isMoon){for(const side of [-1,1]){ball(doll,hair,side*.51,1.65,0,.235);ball(guardian,red,side*.57,1.68,.1,.12);ball(doll,hair,side*.57,.92,-.10,.145,.67,.15);ball(doll,hair,side*.59,.37,-.09,.11,.3,.12);}}
    ball(doll,MAT.skin,0,1.30,.12,.48,.45,.37);
    // Sculpted fringe follows the forehead rather than covering the eyes.
    for(let i=-2;i<=2;i++){const b=ball(doll,hair,i*.145,1.67-Math.abs(i)*.025,.30,.15,.15,.13);b.rotation.z=-i*.2;}
    if(['mercury','uranus','saturn'].includes(kind)){ball(doll,hair,-.44,1.26,.04,.16,kind==='saturn'?.42:.32,.24);ball(doll,hair,.44,1.26,.04,.16,kind==='saturn'?.42:.32,.24);}
    if(kind==='venus')bow(doll,'#dc8da3',1.90,-.02,.23);
    const arms=[];
    for(const side of [-1,1]){
      ball(doll,MAT.eye,side*.165,1.32,.453,.042,.077,.02);
      ball(doll,MAT.white,side*.165-.008,1.347,.473,.012,.017,.008);
      ball(doll,material('#efb5bb'),side*.29,1.205,.42,.075,.033,.012);
      ball(doll,MAT.white,side*.13,.18,0,.09,.25,.09);
      ball(guardian,cloth,side*.14,-.03,.06,.12,.19,.15);
      ball(school,shoes,side*.14,-.09,.08,.13,.10,.18);
      // Separate full-length school sleeves and guardian gloves share a pose.
      for(const [outfit,isSchool] of [[school,true],[guardian,false]]){
        const arm=new THREE.Group();arm.position.set(side*.27,.84,.05);outfit.add(arm);
        ball(arm,isSchool?schoolTop:MAT.skin,side*.05,-.13,0,.105,.22,.10);
        ball(arm,isSchool?schoolTop:MAT.white,side*.10,-.30,.03,.11,.14,.11);
        ball(arm,isSchool?MAT.skin:MAT.white,side*.10,-.40,.04,.09,.09,.09);
        if(isSchool)ball(arm,schoolSkirt,side*.10,-.32,.04,.112,.035,.112);
        arms.push({group:arm,side});
      }
    }
    const smile=new THREE.QuadraticBezierCurve3(new THREE.Vector3(-.055,1.19,.477),new THREE.Vector3(0,1.15,.49),new THREE.Vector3(.055,1.19,.477));mesh(new THREE.TubeGeometry(smile,12,.008,5,false),MAT.eye,doll);
    ball(guardian,MAT.white,0,.67,0,.27,.35,.21);
    const skirt=mesh(new THREE.CylinderGeometry(.24,.40,.27,12),cloth,guardian,0,.39,0);skirt.rotation.y=.15;
    ball(school,schoolTop,0,.65,0,.285,.33,.225);
    const schoolHem=mesh(new THREE.CylinderGeometry(.25,.405,.36,16),schoolSkirt,school,0,.30,0);schoolHem.rotation.y=.15;
    // Light seam lines make the longer school skirt read as a pleated uniform.
    for(let i=0;i<12;i++){const a=i*Math.PI/6;const seam=mesh(new THREE.CylinderGeometry(.006,.009,.34,5),material(uniform[0],{roughness:.9}),school,Math.sin(a)*.325,.30,Math.cos(a)*.325);seam.rotation.z=-Math.sin(a)*.35;seam.rotation.x=Math.cos(a)*.35;}
    // Sailor collar, a generous bow, and a gold tiara with a tiny gem.
    for(const side of [-1,1]){
      const collar=mesh(new THREE.BoxGeometry(.20,.07,.24),cloth,guardian,side*.13,.85,.16);collar.rotation.z=side*.48;
      const schoolCollar=mesh(new THREE.BoxGeometry(.23,.055,.27),schoolSkirt,school,side*.135,.85,.16);schoolCollar.rotation.z=side*.45;
      const stripe=mesh(new THREE.BoxGeometry(.19,.012,.28),MAT.white,school,side*.14,.875,.165);stripe.rotation.z=side*.45;
    }
    bow(guardian,isMoon?'#df98b8':kind==='mercury'?'#b7cce8':kind==='mars'?'#b796c5':kind==='jupiter'?'#e2a9bd':'#a8c4da',.72,.26,.15);
    bow(school,schoolBow,.70,.27,kind==='jupiter'?.12:.19);
    if(kind==='mars'){for(const side of [-1,1])ball(school,shoes,side*.095,.55,.215,.021,.021,.012);}
    mesh(new THREE.BoxGeometry(.52,.035,.035),MAT.gold,guardian,0,1.59,.428);
    ball(guardian,red,0,1.59,.46,.048,.065,.022);
    ball(guardian,MAT.gold,-.40,1.12,.18,.025);ball(guardian,MAT.gold,.40,1.12,.18,.025);
    // Small planetary accessories keep the four added guardians distinct.
    if(['uranus','neptune','pluto','saturn'].includes(kind)){
      const charm=new THREE.Group();guardian.add(charm);charm.position.set(.53,.25,.02);charm.rotation.z=-.14;
      mesh(new THREE.CylinderGeometry(.018,.018,.92,8),MAT.gold,charm,0,.5,0);
      if(kind==='uranus'){mesh(new THREE.BoxGeometry(.17,.025,.05),MAT.gold,charm,0,.75,0);mesh(new THREE.ConeGeometry(.07,.45,4),material('#e3e9f3'),charm,0,1,0);}
      if(kind==='neptune'){ball(charm,material('#b8e0df',{metalness:.6,roughness:.18}),0,1,0,.14,.20,.045);const rim=torus(charm,.17,.023,MAT.gold,0,1,0);rim.scale.y=1.25;}
      if(kind==='pluto'){ball(charm,material('#caa2b9'),0,1,0,.13,.15,.07);star(charm,0,1.23,0,.075);}
      if(kind==='saturn'){const hook=torus(charm,.17,.022,material('#cbd0e0'),.1,.98,0);hook.rotation.z=.5;mesh(new THREE.ConeGeometry(.055,.27,4),material('#cbd0e0'),charm,.23,1.07,0).rotation.z=-.9;}
    }
    doll.userData.costumes={school,guardian,arms};
    return doll;
  }
  function magicEffects(anchor,color){
    const effects=new THREE.Group();anchor.add(effects);
    const ribbonMat=material(color,{transparent:true,opacity:.75,emissive:color,emissiveIntensity:.25,side:THREE.DoubleSide});
    const points=[];for(let i=0;i<=120;i++){const f=i/120,a=f*Math.PI*5;points.push(new THREE.Vector3(Math.cos(a)*.70,.03+f*1.95,Math.sin(a)*.70));}
    const ribbon=mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),120,.034,6,false),ribbonMat,effects);
    const halo=torus(effects,.86,.016,MAT.gold,0,.05,0,Math.PI/2);
    const motes=[];for(let i=0;i<12;i++){const m=star(effects,0,0,0,.045+(i%3)*.012,i%2?MAT.gold:material(color,{emissive:color,emissiveIntensity:.3}));motes.push(m);}
    const veil=ball(effects,new THREE.MeshBasicMaterial({color:'#fff5fc',transparent:true,opacity:0,depthWrite:false}),0,1,0,.65,1.10,.65);
    effects.visible=false;return {effects,ribbon,halo,motes,veil};
  }
  const nodes=[],clickTargets=[];
  for(const agent of agents){
    const anchor=new THREE.Group();anchor.position.set(...agent.pos);group.add(anchor);
    const color=material(agent.color);
    const platform=mesh(new THREE.CylinderGeometry(agent.kind==='crystal'?.75:.91,agent.kind==='crystal'?.8:1,.18,64),material('#fff9fe'),anchor,0,-.15,0);
    const ring=torus(anchor,agent.kind==='crystal'?.76:.93,.028,material(agent.color,{metalness:.45}),0,-.04,0,Math.PI/2);
    const aura=mesh(new THREE.CircleGeometry(1.10,64),new THREE.MeshBasicMaterial({color:agent.color,transparent:true,opacity:.08,depthWrite:false,side:THREE.DoubleSide}),anchor,0,-.03,0);aura.rotation.x=-Math.PI/2;
    let figure,magic;
    if(agent.kind==='crystal'){
      figure=new THREE.Group();anchor.add(figure);const crystal=mesh(new THREE.OctahedronGeometry(.58),material('#e9bfe9',{metalness:.38,roughness:.2,transparent:true,opacity:.85}),figure,0,.8,0);crystal.scale.set(1,1.5,1);
      const crown=torus(figure,.64,.025,MAT.gold,0,.45,0,Math.PI/2);crown.rotation.z=.2;star(figure,0,1.8,0,.12);for(let i=0;i<4;i++){const a=i*Math.PI/2;star(figure,Math.cos(a)*.6,.45,Math.sin(a)*.6,.08);}
    }else{
      figure=doll(anchor,agent.kind,agent.color);
      magic=magicEffects(anchor,agent.color);
      if(agent.kind==='moon'){const moon=crescent(anchor,.64);moon.position.set(-.95,1.7,-.4);moon.rotation.y=.15;star(anchor,.9,2.1,-.3,.10);}
      const book=mesh(new THREE.BoxGeometry(.38,.05,.28),material('#fffaf4'),anchor,.55,.12,.48);book.rotation.z=-.1;
      mesh(new THREE.BoxGeometry(.4,.025,.3),color,anchor,.55,.095,.48);
      if(agent.kind!=='moon'){const planet=ball(anchor,material(agent.color,{roughness:.25}),-.7,.65,-.2,.15);if(agent.kind==='jupiter'){const r=torus(anchor,.23,.016,MAT.gold,-.7,.65,-.2,Math.PI/2);r.rotation.z=.3;}}
    }
    // An invisible, generous selection target is easier to click than a small limb.
    const hit=mesh(new THREE.SphereGeometry(1.0,16,12),new THREE.MeshBasicMaterial({visible:false}),anchor,0,.8,0);hit.userData.agent=agent.id;clickTargets.push(hit);
    const label=document.createElement('button');label.className='node-label';label.style.setProperty('--c',agent.color);label.innerHTML=`<b>${agent.symbol} ${agent.name}</b><small class="node-work-state">대기 중</small>`;label.addEventListener('pointerdown',e=>e.stopPropagation());label.onclick=()=>onSelect(agent.id);labelLayer.append(label);
    nodes.push({agent,anchor,figure,ring,aura,label,magic,baseY:agent.pos[1]});
  }
  // Dashed ribbons connect research stations; moving stars carry the current work.
  const routes=[];
  for(const agent of agents.filter(a=>a.id.startsWith('researcher'))){
    const start=new THREE.Vector3(...agents.find(a=>a.id==='moon').pos).add(new THREE.Vector3(0,.7,0));const mid=new THREE.Vector3(...agent.pos).add(new THREE.Vector3(0,.3,0));const end=new THREE.Vector3(...agents.find(a=>a.id==='crystal').pos).add(new THREE.Vector3(0,.7,0));
    for(const [from,to,phase] of [[start,mid,'assign'],[mid,end,'collect']]){
      const control=from.clone().lerp(to,.5).add(new THREE.Vector3(0,.9,0));const curve=new THREE.QuadraticBezierCurve3(from,control,to);const geo=new THREE.BufferGeometry().setFromPoints(curve.getPoints(60));
      const line=new THREE.Line(geo,new THREE.LineDashedMaterial({color:agent.color,dashSize:.05,gapSize:.12,transparent:true,opacity:.24}));line.computeLineDistances();group.add(line);
      const particle=star(group,0,0,0,.08,material(agent.color,{emissive:agent.color,emissiveIntensity:.25}));particle.visible=false;routes.push({agent:agent.id,curve,line,particle,phase});
    }
  }
  let visibleCount=0;
  let mobileArrangement=null;
  function arrange(count){
    if(visibleCount===count&&mobileArrangement===mobile.matches)return;
    visibleCount=count;mobileArrangement=mobile.matches;
    const positions=researcherPositions(count);
    const rows=Math.ceil(count/2);
    if(mobile.matches){
      for(let i=0;i<count;i++)positions[i]=[count===1?0:(i%2?3.1:-3.1),0,(Math.floor(i/2)-(rows-1)/2)*6];
    }
    for(const node of nodes){
      const index=Number(node.agent.id.split('-')[1]),researcher=node.agent.id.startsWith('researcher-');
      node.anchor.visible=!researcher||index<count;node.label.hidden=!node.anchor.visible;
      if(researcher&&index<count){node.anchor.position.set(...positions[index]);node.figure.scale.setScalar(count>4?.85:1);}
      if(!researcher)node.anchor.position.set(...(mobile.matches?[0,node.agent.kind==='moon'?0:.35,(node.agent.kind==='moon'?-1:1)*(rows+1)*3]:node.agent.pos));
    }
    canvas.style.setProperty('--mobile-scene-height',`${340+rows*140}px`);
    labelLayer.style.setProperty('--mobile-scene-height',`${340+rows*140}px`);
    for(const route of routes){
      const n=Number(route.agent.split('-')[1]);route.line.visible=n<count;
      if(n>=count){route.particle.visible=false;continue;}
      const start=nodes.find(n=>n.agent.id==='moon').anchor.position.clone().add(new THREE.Vector3(0,.7,0));
      const mid=new THREE.Vector3(...positions[n]).add(new THREE.Vector3(0,.3,0));
      const end=nodes.find(n=>n.agent.id==='crystal').anchor.position.clone().add(new THREE.Vector3(0,.7,0));
      const from=route.phase==='assign'?start:mid,to=route.phase==='assign'?mid:end;
      route.curve=new THREE.QuadraticBezierCurve3(from,from.clone().lerp(to,.5).add(new THREE.Vector3(0,.9,0)),to);
      route.line.geometry.dispose();route.line.geometry=new THREE.BufferGeometry().setFromPoints(route.curve.getPoints(60));route.line.computeLineDistances();
    }
  }
  const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
  canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,a:azimuth,e:elevation};moved=false;canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>5)moved=true;azimuth=drag.a-dx*.004;elevation=Math.max(.22,Math.min(.9,drag.e+dy*.002));});
  canvas.addEventListener('pointerup',e=>{if(!moved){const rect=canvas.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObjects(clickTargets.filter(target=>target.parent.visible))[0];if(hit)onSelect(hit.object.userData.agent);}drag=null;});
  canvas.addEventListener('pointercancel',()=>drag=null);
  canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(13,Math.min(26,distance+e.deltaY*.008));},{passive:false});
  const size={w:0,h:0};
  const temp=new THREE.Vector3();
  function frame(time){
    if(mobileArrangement!==mobile.matches)arrange(visibleCount||4);
    const w=canvas.clientWidth,h=canvas.clientHeight;if(size.w!==w||size.h!==h){renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();size.w=w;size.h=h;}
    const aspect=w/h;
    const responsiveDistance=Math.max(distance*(aspect<1.1?1.22:1),12.7/(2*Math.tan(Math.PI/10)*aspect));
    const viewingElevation=mobile.matches?Math.min(1.2,elevation+.4):elevation;
    camera.position.set(Math.sin(azimuth)*responsiveDistance,Math.sin(viewingElevation)*responsiveDistance+1,Math.cos(azimuth)*Math.cos(viewingElevation)*responsiveDistance);
    camera.lookAt(0,.7,mobile.matches?0:1.0);
    // Reserve breathing room for the title and playback controls in the composition.
    camera.setViewOffset(w,h,0,h*.035,w,h);camera.updateProjectionMatrix();
    const t=time*.001,clock=snap?.time||0;
    for(const node of nodes){if(!node.anchor.visible)continue;const a=snap?.agents[node.agent.id];const active=a?.pending&&!reduced;
      const trans=a?.transformation,p=trans?.progress||0;
      node.figure.position.y=reduced?0:Math.sin((active?clock*5:t*1.3)+nodes.indexOf(node))*(active ? .07 : .025);
      if(node.agent.kind==='crystal'){
        node.figure.rotation.y=reduced ? .35 : clock*.35;
        const pieces=Object.values(snap?.agents||{}).filter(a=>a.section).length;
        node.figure.scale.setScalar(snap?.report?1.18:.72+pieces*.07);
      }else{
        const costume=node.figure.userData.costumes;
        costume.school.visible=trans?.outfit!=='guardian';costume.guardian.visible=!costume.school.visible;
        const spin=p>.35&&p<.93?(p-.35)/.58:0;
        node.figure.rotation.y=azimuth*.75+(reduced?0:spin*Math.PI*2);
        const pose=p===1 ? .64 : Math.sin(p*Math.PI)*1.15;
        for(const arm of costume.arms)arm.group.rotation.z=arm.side*pose;
        if(!reduced&&trans?.active)node.figure.position.y+=Math.sin(p*Math.PI)*.23;
        const fx=node.magic;
        fx.effects.visible=!!trans?.active&&p>.08;
        fx.ribbon.visible=p>.35&&p<.96;
        fx.ribbon.rotation.y=reduced?0:clock*1.6;
        fx.ribbon.scale.setScalar(.8+Math.sin(p*Math.PI)*.2);
        fx.halo.rotation.z=reduced?0:clock*.6;
        fx.halo.position.y=.05+(p>.35?(p-.35)*1.5:0);
        fx.veil.material.opacity=reduced?0:Math.exp(-(((p-.72)/.09)**2))*.40;
        for(let i=0;i<fx.motes.length;i++){
          const m=fx.motes[i],angle=i*Math.PI/6+(reduced?0:clock*(.8+i%3*.1));
          const radius=.68+Math.sin(p*Math.PI)*.28;
          m.position.set(Math.cos(angle)*radius,.25+(i%4)*.45+Math.sin(angle)*.08,Math.sin(angle)*radius);
          m.rotation.z=reduced?0:clock*.9+i;
          m.scale.setScalar((.04+i%3*.012)*(p<.35 ? .7 : 1));
        }
      }
      node.ring.material.emissive.set(node.agent.id===selected?node.agent.color:'#000000');node.ring.material.emissiveIntensity=node.agent.id===selected ? .20 : 0;
      node.aura.material.opacity=trans?.active ? .13+(Math.sin(clock*2)+1)*.025 : node.agent.id===selected ? .15 : .05;
      node.anchor.getWorldPosition(temp);temp.y-=.40;temp.project(camera);node.label.style.left=`${(temp.x*.5+.5)*w}px`;node.label.style.top=`${(-temp.y*.5+.5)*h}px`;node.label.style.visibility=temp.z>1?'hidden':'visible';
    }
    for(let i=0;i<routes.length;i++){
      const route=routes[i],a=snap?.agents[route.agent];
      route.particle.visible=Number(route.agent.split('-')[1])<visibleCount&&!!a&&(route.phase==='assign'?a.pending:!!a.section&&!snap.report);
      route.line.material.opacity=route.particle.visible ? .46 : .18;
      if(route.particle.visible){
        const section=snap.events.find(e=>e.agent===route.agent&&e.kind==='section');
        const travel=route.phase==='collect'?Math.min(1,Math.max(0,(clock-(section?.displayTime||clock))/1.2)):(clock*.20+i*.13)%1;
        route.particle.position.copy(route.curve.getPoint(reduced ? .5 : travel));route.particle.rotation.z=reduced?0:clock;
      }
    }
    if(!reduced)for(let i=0;i<sparkles.length;i++)sparkles[i].rotation.z=Math.sin(t*.4+i)*.15;
    renderer.render(scene,camera);requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  return {update(next,id){snap=next;selected=id;arrange(next.researcherCount||4);for(const n of nodes){
    const a=snap.agents[n.agent.id],trans=a.transformation;
    n.label.classList.toggle('selected',n.agent.id===selected);n.label.classList.toggle('working',a.pending);
    n.label.classList.toggle('transforming',!!trans?.active);
    n.label.dataset.outfit=trans?.outfit||'crystal';n.label.dataset.phase=trans?.phase||'편집 대기';
    n.label.style.setProperty('--progress',`${(trans?.progress||0)*100}%`);
    n.label.querySelector('.node-work-state').textContent=a.workStatus||a.status;
  }},reset(){azimuth=0;elevation=.49;distance=19;}};
}
