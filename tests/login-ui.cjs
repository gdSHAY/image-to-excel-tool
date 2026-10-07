// Regression: clicking login before uploading an image must reach OAuth,
// without the proofreader overriding the browser's native window.open.
const vm=require('node:vm');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const elements=new Map(),calls=[];
const url='https://www.camscanner.com/agent-auth?from=test';
const popup={location:{href:'about:blank'},close(){}};
const sandbox={console,setTimeout(){return 1},clearTimeout(){},
  document:{getElementById(id){if(!elements.has(id))elements.set(id,{style:{},classList:{toggle(){}},value:'',textContent:'',hidden:false,disabled:false,addEventListener(){},setAttribute(){}});return elements.get(id)}},
  fetch:async(path,options={})=>{calls.push([path,options.method||'GET']);return {ok:true,json:async()=>path==='/api/jobs'?[]:path==='/api/auth/login'?{login_in_progress:true,login_url:url,message:'ready'}:{login_in_progress:false,logged_in:false,message:'not logged in'}}},
  open(){return popup},addEventListener(){}};
sandbox.window=sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('web/app.js','utf8'),sandbox);
(async()=>{await new Promise(resolve=>setImmediate(resolve));await elements.get('login').onclick();
assert(calls.some(([path,method])=>path==='/api/auth/login'&&method==='POST'));
assert.equal(popup.location.href,url);
assert.equal(elements.get('authLink').href,url);
assert.equal(typeof sandbox.open,'function');
console.log('PASS: login without an uploaded job reaches OAuth and opens official URL');
})().catch(e=>{console.error(e);process.exitCode=1});
