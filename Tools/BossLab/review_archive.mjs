import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const dir=path.join(root,'Documentation','影之刃零复刻项目档案_2026-11-13');
const title='影之刃零复刻项目完整记录与通用流程';
const meta=JSON.parse(fs.readFileSync(path.join(dir,'归档说明.json'),'utf8'));
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'boss-archive-preview-'));
const browser=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
 '--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'
],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(r=>setTimeout(r,ms));let ws,id=0;const pending=new Map(),errors=[];
function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;const timer=setTimeout(()=>{pending.delete(key);reject(new Error('CDP timeout '+method))},30000);pending.set(key,{resolve:v=>{clearTimeout(timer);resolve(v)},reject});ws.send(JSON.stringify({id:key,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
try{
 let port;
 for(let t=0;t<150;t++){const p=path.join(temp,'DevToolsActivePort');if(fs.existsSync(p)){port=fs.readFileSync(p,'utf8').split('\n')[0];break;}await delay(100);}
 assert(port,'No Edge debugging port');
 const page=(await(await fetch('http://127.0.0.1:'+port+'/json/list')).json()).find(t=>t.type==='page');
 ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);};
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:pathToFileURL(path.join(dir,title+'.html')).href});
 for(let t=0;t<100;t++){if(await evaluate('document.readyState === "complete" && Boolean(document.getElementById("query"))'))break;await delay(100);}
 await evaluate('document.fonts.ready.then(()=>true)');
 assert.equal(await evaluate('document.querySelectorAll(".message").length'),meta.total_messages);
 assert.equal(await evaluate('document.querySelectorAll(".message.user").length'),meta.counts.user);
 await evaluate('document.getElementById("query").value="没有自然回气";document.getElementById("query").dispatchEvent(new Event("input"))');
 const search=await evaluate('({shown:[...document.querySelectorAll(".message")].filter(x=>!x.hidden).length,open:[...document.querySelectorAll(".message")].filter(x=>!x.hidden&&x.open).length})');
 assert(search.shown>0&&search.open===search.shown);
 await evaluate('document.getElementById("query").value="";document.getElementById("query").dispatchEvent(new Event("input"));document.getElementById("expand").click()');
 assert.equal(await evaluate('document.querySelectorAll("details[open]").length'),meta.total_messages);
 await evaluate('document.getElementById("collapse").click()');assert.equal(await evaluate('document.querySelectorAll("details[open]").length'),0);
 const images=await evaluate('Promise.all([...document.querySelectorAll("#guide img")].map(im=>im.decode().then(()=>({src:im.getAttribute("src"),width:im.naturalWidth}))))');assert(images.every(x=>x.width>0));
 const links=await evaluate('[...document.querySelectorAll("nav a")].map(a=>a.getAttribute("href"))');
 for(const link of links)if(!link.startsWith('#'))assert(fs.existsSync(path.join(dir,link)),link);
 const preview=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(dir,'图片','文档阅读预览.png'),Buffer.from(preview.data,'base64'));
 // PDF is the printable copy of exactly the same document, with all dialogue expanded.
 await evaluate('document.getElementById("expand").click()');
 const pdf=await send('Page.printToPDF',{printBackground:true,preferCSSPageSize:false,paperWidth:8.27,paperHeight:11.69,marginTop:.5,marginBottom:.5,marginLeft:.5,marginRight:.5});
 fs.writeFileSync(path.join(dir,title+'.pdf'),Buffer.from(pdf.data,'base64'));
 assert.equal(errors.length,0);
 fs.writeFileSync(path.join(dir,'浏览器校验报告.json'),JSON.stringify({browser:'headless Edge',messages:meta.total_messages,user_prompts:meta.counts.user,search,expand_collapse:true,images,local_navigation_links_valid:true,javascript_errors:errors,pdf_generated:true,word_visual_reviewed:false},null,2));
 const manifest=[];
 function visit(folder){for(const e of fs.readdirSync(folder,{withFileTypes:true})){const p=path.join(folder,e.name);if(e.isDirectory())visit(p);else if(e.name!=='文件校验清单.json'){const b=fs.readFileSync(p);manifest.push({path:path.relative(dir,p).split(path.sep).join('/'),bytes:b.length,sha256:crypto.createHash('sha256').update(b).digest('hex')});}}}
 visit(dir);fs.writeFileSync(path.join(dir,'文件校验清单.json'),JSON.stringify(manifest,null,2));
 console.log(JSON.stringify({ok:true,folder:dir,messages:meta.total_messages,search,images:images.length,pdf_bytes:Buffer.from(pdf.data,'base64').length,files:manifest.length+1}));
}finally{if(ws)ws.close();browser.kill();}
