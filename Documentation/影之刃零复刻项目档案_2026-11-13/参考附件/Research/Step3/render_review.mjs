// Headless Edge smoke checks + screenshots. Uses only Node built-ins.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const dir=path.dirname(fileURLToPath(import.meta.url));
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'boss-fsm-preview-'));
const browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
 '--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'
],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let ws,id=0;const pending=new Map(),errors=[];
function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;const timer=setTimeout(()=>{pending.delete(key);reject(new Error('CDP timeout: '+method))},30000);pending.set(key,{resolve:v=>{clearTimeout(timer);resolve(v)},reject:e=>{clearTimeout(timer);reject(e)}});ws.send(JSON.stringify({id:key,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
try{
 let port;
 for(let t=0;t<150;t++){const p=path.join(temp,'DevToolsActivePort');if(fs.existsSync(p)){port=fs.readFileSync(p,'utf8').split('\n')[0];break}await delay(100)}
 assert(port,'Edge debugging port did not start');
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 const page=targets.find(t=>t.type==='page');assert(page);
 ws=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params)};
 await send('Page.enable');await send('Runtime.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1920,height:1200,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:pathToFileURL(path.join(dir,'Boss全量分层状态机.html')).href});
 for(let t=0;t<100;t++){if(await evaluate('Boolean(window.FSM)'))break;await delay(100)}
 await evaluate('document.fonts.ready.then(()=>true)');await delay(150);
 const audit=await evaluate('({nodes:document.querySelectorAll(".state").length,edges:document.querySelectorAll(".wire").length,groups:document.querySelectorAll(".region").length,model:FSM.graph.audit})');
 assert.equal(audit.nodes,audit.model.nodes);assert.equal(audit.edges,audit.model.edges);assert.equal(audit.groups,audit.model.groups);
 const uiChecks=[];
 for(const g of await evaluate('FSM.graph.groups.map(g=>g.id)')){
  await evaluate(`document.querySelector('[data-group="${g}"].nav-item').click()`);
  const v=await evaluate('FSM.getView()');assert(v.w>0&&v.h>0);uiChecks.push(g);
 }
 await evaluate('document.getElementById("search").value="M2-05-F";document.getElementById("search").dispatchEvent(new Event("input"))');
 assert((await evaluate('document.querySelectorAll("#results .result").length'))>0);
 await evaluate('FSM.select("M2_05_F_BRANCH",false)');
 assert((await evaluate('document.getElementById("detail").textContent')).includes('sigmoid'));
 await evaluate('document.getElementById("showGlobals").click()');
 assert.equal(await evaluate('document.querySelectorAll(".wire.global.hide-wire").length'),audit.model.inherited_edges);
 await evaluate('document.getElementById("showGlobals").click();FSM.reset();document.getElementById("search").value="";document.getElementById("search").dispatchEvent(new Event("input"));FSM.focusGroup("phase")');
 const before=await evaluate('FSM.getView().w');
 await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:800,y:500,deltaX:0,deltaY:-100});await delay(80);
 assert((await evaluate('FSM.getView().w'))<before);
 await evaluate('FSM.focusGroup("phase")');await delay(80);
 async function shot(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(dir,name),Buffer.from(r.data,'base64'))}
 await shot('阶段总控预览.png');
 await evaluate('FSM.focusGroup("m2fixed")');await delay(80);await shot('连招状态与连线预览.png');
 await evaluate('FSM.select("M2_05_F_BRANCH",true)');await delay(80);await shot('变招条件详情预览.png');
 await evaluate('FSM.reset();FSM.presentation();document.querySelector(".minimap").style.display="none";document.querySelector(".legend").style.display="none"');
 const fullHeight=Math.round(3600*audit.model.canvas_height/audit.model.canvas_width);
 await send('Emulation.setDeviceMetricsOverride',{width:3600,height:fullHeight,deviceScaleFactor:1,mobile:false});
 await evaluate('FSM.fit({x:0,y:0,width:FSM.graph.width,height:FSM.graph.height},0)');await delay(200);
 await shot('Boss全量分层状态机总览.png');
 assert.equal(errors.length,0,JSON.stringify(errors));
 fs.writeFileSync(path.join(dir,'browser_review.json'),JSON.stringify({engine:'Microsoft Edge headless',nodes:audit.nodes,edges:audit.edges,groups:audit.groups,pan_navigation_checked:uiChecks,search:true,details:true,inherited_wire_toggle:true,wheel_zoom:true,runtime_errors:errors,preview_files:['阶段总控预览.png','连招状态与连线预览.png','变招条件详情预览.png','Boss全量分层状态机总览.png']},null,2));
 console.log(JSON.stringify({nodes:audit.nodes,edges:audit.edges,groups:audit.groups,runtime_errors:errors.length,screenshots:4}));
}finally{
 if(ws?.readyState===1){try{await send('Browser.close')}catch{}ws.close()}
 if(browser.exitCode===null)browser.kill();
 // Only remove the exact unique profile created by this script under the temp root.
 const resolved=path.resolve(temp),root=path.resolve(os.tmpdir())+path.sep;
 if(resolved.startsWith(root)&&path.basename(resolved).startsWith('boss-fsm-preview-')){
  try{fs.rmSync(resolved,{recursive:true,force:true,maxRetries:10,retryDelay:100})}catch{}
 }
}
