// Offline regression for zoom anchors, middle-button capture and filtered navigation.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=new Map();
function element(id){if(!elements.has(id)){
  const classes=new Set(),listeners={};
  elements.set(id,{id,value:'',open:false,style:{},listeners,clientWidth:1028,clientHeight:700,
    classList:{add(c){classes.add(c)},remove(c){classes.delete(c)},toggle(c,on){on?classes.add(c):classes.delete(c)},contains(c){return classes.has(c)}},
    addEventListener(name,fn){listeners[name]=fn},setAttribute(){},append(){},
    showModal(){this.open=true},close(){this.open=false},
    focus(){},querySelector(){return element('structure-settings')},
    getBoundingClientRect(){return {left:10,top:20,right:1010,bottom:720,width:1000,height:700}},
    setPointerCapture(id){this.capture=id},hasPointerCapture(id){return this.capture===id},releasePointerCapture(){this.capture=null}});
}return elements.get(id)}
const sandbox={console,setTimeout(){return 1},clearTimeout(){},
  document:{getElementById:element,body:{classList:{add(){},remove(){}}}},
  fetch:async path=>({ok:true,json:async()=>path==='/api/jobs'?[]:{logged_in:false}}),
  addEventListener(){}};
sandbox.window=sandbox;vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('web/app.js','utf8'),sandbox);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`render=()=>{};image=()=>{};overlay=()=>{};grid=()=>{};crop=()=>{};`,sandbox);
  element('imageViewer').open=true;element('viewerScale').value=100;
  vm.runInContext(`viewerScale(200,{x:110,y:70})`,sandbox);
  assert.equal(element('imageWrap').style.width,'2000px');
  assert.equal(element('imageWrap').style.transform,'translate(-100px,-50px)');
  vm.runInContext(`viewerScale(999);`,sandbox);assert.equal(element('viewerScale').value,400);
  vm.runInContext(`resetViewer();`,sandbox);assert.equal(element('viewerScale').value,100);
  let prevented=false;
  element('stage').listeners.wheel({deltaY:-120,deltaMode:0,clientX:110,clientY:70,preventDefault(){prevented=true}});
  assert(prevented);assert(Number(element('viewerScale').value)>100);
  element('proof').open=true;const before=element('viewerScale').value;
  element('stage').listeners.wheel({deltaY:120});assert.equal(element('viewerScale').value,before);
  element('proof').open=false;vm.runInContext(`resetViewer()`,sandbox);
  const down={button:1,pointerId:7,clientX:100,clientY:200,preventDefault(){},stopPropagation(){}};
  element('stage').listeners.pointerdown(down);
  assert.equal(element('stage').capture,7);
  element('stage').listeners.pointermove({pointerId:7,clientX:180,clientY:170,preventDefault(){}});
  assert.equal(element('imageWrap').style.transform,'translate(80px,-30px)');
  element('stage').listeners.pointerup({pointerId:7});assert.equal(element('stage').capture,null);
  assert(!element('stage').classList.contains('panning'));
  vm.runInContext(`job={cells:[
    {id:'red1',row:1,col:1,text:'错',score:.6,rowspan:1,colspan:1,confirmed:false},
    {id:'yellow1',row:1,col:2,text:'对',score:.99,rowspan:1,colspan:1,confirmed:false},
    {id:'red2',row:2,col:1,text:'错2',score:.8,rowspan:1,colspan:1,confirmed:false},
    {id:'empty1',row:2,col:2,text:'',score:null,rowspan:1,colspan:1,confirmed:false},
    {id:'empty2',row:3,col:1,text:' ',score:null,rowspan:1,colspan:1,confirmed:false}
  ]}; save=async()=>{}; filter='all';`,sandbox);
  vm.runInContext(`selectFilter('red');openCell('red1')`,sandbox);
  await vm.runInContext(`advance(true)`,sandbox);
  assert.equal(vm.runInContext('selected',sandbox),'red2');
  assert(vm.runInContext(`job.cells[0].confirmed`,sandbox));
  vm.runInContext(`selectFilter('gray')`,sandbox);
  assert.equal(vm.runInContext('selected',sandbox),'empty1');
  await vm.runInContext(`advance(false)`,sandbox);
  assert.equal(vm.runInContext('selected',sandbox),'empty2');
  await vm.runInContext(`advance(false)`,sandbox);assert(!element('proof').open);
  vm.runInContext(`selectFilter('gray')`,sandbox);assert.equal(vm.runInContext('filter',sandbox),'all');
  vm.runInContext(`selectFilter('yellow');openCell('red2')`,sandbox);
  assert.equal(vm.runInContext('selected',sandbox),null);
  vm.runInContext(`openCell('yellow1')`,sandbox);assert.equal(vm.runInContext('selected',sandbox),'yellow1');
  vm.runInContext(`save=async()=>{throw Error('模拟保存失败')}`,sandbox);
  await vm.runInContext(`run(saveProofAndClose)`,sandbox);
  assert(element('proof').open,'save failure must keep the editor open');
  assert.equal(element('toast').textContent,'模拟保存失败');
  vm.runInContext(`save=async()=>{}`,sandbox);
  const outside={button:0,target:element('proof'),clientX:5,clientY:30,preventDefault(){},stopPropagation(){}};
  element('proof').listeners.pointerdown({...outside,clientX:50});
  element('proof').listeners.click(outside);
  assert(element('proof').open,'dragging from inside must not dismiss');
  element('proof').listeners.pointerdown(outside);
  element('proof').listeners.click(outside);
  await new Promise(resolve=>setImmediate(resolve));
  assert(!element('proof').open,'outside click saves and closes');
  vm.runInContext(`displayAuth({logged_in:true})`,sandbox);assert(element('configNotice').hidden);
  vm.runInContext(`displayAuth({logged_in:false})`,sandbox);assert(!element('configNotice').hidden);
  element('image').naturalWidth=1000;element('image').naturalHeight=700;
  vm.runInContext(`job.cells=[{id:'blank',row:1,col:1,rowspan:1,colspan:1,text:'',confirmed:false,score:null,polygon:[50,50,400,50,400,400,50,400]}];filter='all';startSelection('new')`,sandbox);
  const selectStart={button:0,pointerId:12,clientX:110,clientY:120,preventDefault(){},stopPropagation(){}};
  element('imageWrap').onpointerdown(selectStart);
  element('imageWrap').onpointermove({...selectStart,clientX:310,clientY:320});
  assert.equal(element('selectionRect').style.width,'20%');
  assert(!element('selectionRect').hidden,'purple rectangle must update during drag');
  element('stage').listeners.contextmenu({preventDefault(){},stopPropagation(){}});
  assert(element('selectionRect').hidden);assert(!vm.runInContext('binding',sandbox));
  assert.equal(vm.runInContext('job.cells.length',sandbox),1);
  vm.runInContext(`startSelection('new')`,sandbox);
  element('imageWrap').onpointerdown(selectStart);
  element('imageWrap').onpointerup({...selectStart,clientX:310,clientY:320});
  assert.equal(vm.runInContext('selected',sandbox),'blank');
  assert.equal(vm.runInContext('job.cells.length',sandbox),1,'existing blank cell must be reused');
  assert(element('proof').open);assert(!vm.runInContext('binding',sandbox));
  element('proof').close();vm.runInContext(`startSelection('new')`,sandbox);
  const newStart={...selectStart,clientX:610,clientY:520};
  sandbox.crypto={randomUUID:()=> 'new-region'};
  element('imageWrap').onpointerdown(newStart);
  element('imageWrap').onpointerup({...newStart,clientX:810,clientY:620});
  assert.equal(vm.runInContext('job.cells.length',sandbox),2);
  assert.equal(vm.runInContext('selected',sandbox),'new-region');
  assert(element('structure-settings').open,'new cell must ask for row/column review');
  vm.runInContext(`job.id='filename-demo'`,sandbox);
  element('exportName').value='10月接收表';
  assert.equal(vm.runInContext('exportFilename()',sandbox),'10月接收表.xlsx');
  element('exportName').value='10月接收表.xlsx';
  assert.equal(vm.runInContext('exportFilename()',sandbox),'10月接收表.xlsx');
  element('exportName').value='CON';
  assert.equal(vm.runInContext('exportFilename()',sandbox),'_CON.xlsx');
  element('exportName').value='';
  assert.equal(vm.runInContext('exportFilename()',sandbox),'表格-filename.xlsx');
  vm.runInContext(`save=async()=>{};autoConfirmClose=true`,sandbox);
  await vm.runInContext(`saveProofAndClose()`,sandbox);
  assert(vm.runInContext(`job.cells.find(c=>c.id===selected).confirmed`,sandbox));
  vm.runInContext(`openCell('new-region');job.cells.find(c=>c.id===selected).confirmed=false;save=async()=>{throw Error('save failed')}`,sandbox);
  await vm.runInContext(`run(saveProofAndClose)`,sandbox);
  assert(element('proof').open);
  assert(!vm.runInContext(`job.cells.find(c=>c.id===selected).confirmed`,sandbox),'failed save must not leave confirmation enabled');
  console.log('PASS: anchored wheel zoom, limits, middle-button pan/release, filtered next/confirm-next, end and cancellation');
})().catch(e=>{console.error(e);process.exitCode=1});
