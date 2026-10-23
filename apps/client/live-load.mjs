import {chromium} from 'playwright';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
let input='';for await(const part of process.stdin)input+=part;const config=JSON.parse(input);
const browser=await chromium.launch({channel:process.env.MARKETOB_BROWSER_CHANNEL||undefined,headless:true});
const rendered=new Map(),accepted=[],errors=[],httpErrors=[],clients=[],actions=[],reads=[];
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const percentile=(values,p)=>{const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.max(0,Math.ceil(p*sorted.length)-1)]??null;};
const stats=values=>({count:values.length,p95_ms:percentile(values,.95),p99_ms:percentile(values,.99),max_ms:Math.max(0,...values)});
try{
  for(const source of config.sources){
    const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',async r=>{
      if(r.url().includes('/v1/')&&r.status()>=400)httpErrors.push(r.status());
      if(r.url().includes('/v1/channels/')&&r.request().method()==='GET'){
        await r.finished();const timing=r.request().timing();if(timing.responseEnd>=0)reads.push(timing.responseEnd-timing.requestStart);
      }
    });
    const auth=await context.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:source.credentials});assert.ok(auth.ok());
    const csrf=(await auth.json()).csrf_token;
    await page.exposeBinding('observedRevision',(_,revision,at,title)=>{rendered.set(source.index+':'+revision,{at,title});});
    await page.addInitScript(()=>{
      let last;
      new MutationObserver(()=>{
        const node=document.querySelector('[data-live-revision]'),revision=node?.dataset.liveRevision;
        if(revision&&revision!==last){last=revision;requestAnimationFrame(()=>window.observedRevision(Number(revision),Date.now(),node.querySelector('h2')?.textContent));}
      }).observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['data-live-revision']});
    });
    await page.goto(config.origin+'/app/#/channel/'+source.slug);
    await page.locator('[data-live-revision="1"]').waitFor();await page.getByText('Live',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.visibilityState),'visible');clients.push({context,page,csrf});
  }
  const start=Date.now(),total=Math.floor(config.seconds*100/60),ingest=[],sizes=[];
  for(let n=0;n<total;n++){
    await wait(Math.max(0,start+n*600-Date.now()));
    const source=config.sources[n%10],revision=Math.floor(n/10)+2;
    const message={...source.message,message_id:'load_'+n,source_revision:revision,occurred_at:new Date().toISOString(),payload:{...source.message.payload,title:`L1 ${source.index} revision ${revision}`}};
    const body=JSON.stringify(message),before=Date.now();
    const response=await fetch(config.origin+'/v1/bot/messages',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+source.key},body});
    const receipt=await response.json(),after=Date.now();assert.equal(response.status,200);ingest.push(after-before);sizes.push(Buffer.byteLength(body));
    accepted.push({id:source.index+':'+receipt.data_revision,at:after,title:message.payload.title});
    // One of ten clients requests a product once/minute. The independent bot GET sees it.
    if(n%100===4){
      const actor=clients[4],item=config.sources[4],queuedAt=Date.now();
      const result=await actor.context.request.post(config.origin+'/v1/channels/'+item.channel_id+'/actions',{headers:{Origin:config.origin,'X-CSRF-Token':actor.csrf,'Idempotency-Key':'load_action_'+n},data:{action_id:'purchase',resource_id:'sample',observed_source_revision:revision,quantity:1}});assert.equal(result.status(),202);
      const request=await result.json(),events=await fetch(config.origin+'/v1/bot/events',{headers:{Authorization:'Bearer '+item.key}}),event=(await events.json()).items.find(e=>e.action_request_id===request.action_request_id);assert.ok(event);actions.push(Date.now()-queuedAt);
      for(const [operation,payload] of [['ack',{}],['result',{result_id:'load_result_'+n,result_revision:1,state:'confirmed',summary:'Synthetic load confirmation.'}]]){
        const response=await fetch(config.origin+'/v1/bot/events/'+event.event_id+'/'+operation,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+item.key},body:JSON.stringify(payload)});assert.equal(response.status,200);
      }
    }
    if(n%100===99)console.log('L1 accepted '+(n+1)+'/'+total);
  }
  const sentAt=Date.now();await wait(10000);
  const missing=[],latencies=[];
  for(const receipt of accepted){const view=rendered.get(receipt.id);if(!view||view.title!==receipt.title)missing.push(receipt.id);else latencies.push(Math.max(0,view.at-receipt.at));}
  const report={profile:config.seconds===900?'L1':'L1 short rehearsal',duration_seconds:config.seconds,send_elapsed_seconds:(sentAt-start)/1000,bots:10,active_clients:10,messages_per_minute:100,accepted:accepted.length,rendered:latencies.length,missing,live:stats(latencies),ingest_http:stats(ingest),read_http:stats(reads),action_available_http:stats(actions),message_bytes:{min:Math.min(...sizes),max:Math.max(...sizes)},browser:browser.version(),node:process.version,page_errors:errors,http_errors:httpErrors};
  await writeFile(path.join(config.output,'live-load.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({accepted:report.accepted,rendered:report.rendered,live:report.live,http_errors:httpErrors}));
  assert.equal(missing.length,0);assert.deepEqual(errors,[]);assert.deepEqual(httpErrors,[]);assert.ok(report.live.p95_ms<=3000&&report.live.p99_ms<=10000);
}finally{await browser.close();}
