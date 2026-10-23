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
const count=config.sources.length;
let phase='setup';
try{
  for(const source of config.sources){
    const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',async r=>{
      if(r.url().includes('/v1/')&&r.status()>=400)httpErrors.push({phase,status:r.status()});
      if(phase==='steady'&&r.url().includes('/v1/channels/')&&r.request().method()==='GET'){
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
    if(clients.length%10===0)console.log('Prepared '+clients.length+'/'+count+' real browser clients');
  }
  const ingest=[],sizes=[],chains=Array.from({length:count},()=>Promise.resolve()),revisions=Array(count).fill(1);
  const actionMinute=Array(count).fill(-1),quotas={burst:0,recovery:0,steady:0},failures=[];
  const transportRetries={burst:0,recovery:0,steady:0};
  async function purchase(index,revision,n){
    const actor=clients[index],item=config.sources[index],queuedAt=Date.now();
    const result=await actor.context.request.post(config.origin+'/v1/channels/'+item.channel_id+'/actions',{headers:{Origin:config.origin,'X-CSRF-Token':actor.csrf,'Idempotency-Key':'load_action_'+n},data:{action_id:'purchase',resource_id:'sample',observed_source_revision:revision,quantity:1}});assert.equal(result.status(),202);
    const request=await result.json(),events=await fetch(config.origin+'/v1/bot/events',{headers:{Authorization:'Bearer '+item.key}}),event=(await events.json()).items.find(e=>e.action_request_id===request.action_request_id);assert.ok(event);actions.push(Date.now()-queuedAt);
    for(const [operation,payload] of [['ack',{}],['result',{result_id:'load_result_'+n,result_revision:1,state:'confirmed',summary:'Synthetic load confirmation.'}]]){
      const response=await fetch(config.origin+'/v1/bot/events/'+event.event_id+'/'+operation,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+item.key},body:JSON.stringify(payload)});assert.equal(response.status,200);
    }
  }
  async function send(n,label,deadline){
    const source=config.sources[n%count],revision=++revisions[source.index];
    const message={...source.message,message_id:label+'_'+n,source_revision:revision,occurred_at:new Date().toISOString(),payload:{...source.message.payload,title:label+' '+source.index+' revision '+revision}};
    const body=JSON.stringify(message);
    while(true){
      const before=Date.now();
      let response,receipt;
      try{
        response=await fetch(config.origin+'/v1/bot/messages',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+source.key},body,signal:AbortSignal.timeout(10000)});
        receipt=await response.json();
      }catch(error){
        // A lost response may already have committed. Repeat the identical ID/body.
        if(label!=='burst'||Date.now()>=deadline||!['TimeoutError','AbortError','TypeError'].includes(error.name))throw error;
        transportRetries[phase]++;await wait(250+Math.random()*250);continue;
      }
      const after=Date.now();
      if(response.status===429&&label==='burst'){
        quotas[phase]++;assert.ok(Number(response.headers.get('Retry-After'))>0);
        assert.ok(Date.now()<deadline,'Burst recovery exceeded three minutes');
        await wait(Number(response.headers.get('Retry-After'))*1000);continue;
      }
      assert.equal(response.status,200,'Ingestion must acknowledge durably');
      if(label==='steady'){ingest.push(after-before);sizes.push(Buffer.byteLength(body));}
      accepted.push({id:source.index+':'+receipt.data_revision,at:after,title:message.payload.title,phase:label});
      const minute=Math.floor(n/config.rate);
      if(label==='steady'&&source.index%10===4&&actionMinute[source.index]!==minute){
        actionMinute[source.index]=minute;await purchase(source.index,revision,n);
      }
      break;
    }
  }
  const start=Date.now(),total=Math.floor(config.seconds*config.rate/60);phase='steady';
  for(let n=0;n<total;n++){
    await wait(Math.max(0,start+n*60000/config.rate-Date.now()));
    const i=n%count;chains[i]=chains[i].then(()=>send(n,'steady',0)).catch(e=>{failures.push(String(e));});
    if(n%config.rate===config.rate-1)console.log('Steady scheduled '+(n+1)+'/'+total+', accepted '+accepted.length);
  }
  await Promise.all(chains);const sentAt=Date.now();await wait(10000);
  const missing=[],latencies=[];
  for(const receipt of accepted){const view=rendered.get(receipt.id);if(!view||view.title!==receipt.title)missing.push(receipt.id);else latencies.push(Math.max(0,view.at-receipt.at));}
  const report={profile:count===100?'L2':'L1',duration_seconds:config.seconds,steady_started_at:new Date(start).toISOString(),steady_finished_at:new Date(sentAt).toISOString(),send_elapsed_seconds:(sentAt-start)/1000,bots:count,active_clients:count,messages_per_minute:config.rate,steady_accepted:accepted.length,rendered:latencies.length,missing,live:stats(latencies),ingest_http:stats(ingest),read_http:stats(reads),action_available_http:stats(actions),message_bytes:{min:Math.min(...sizes),max:Math.max(...sizes)},browser:browser.version(),node:process.version};
  phase='reconnect';const offline=clients[0];await offline.context.setOffline(true);await wait(2500);
  const recoveryStart=Date.now();await offline.context.setOffline(false);
  await offline.page.locator('[data-live-revision="'+revisions[0]+'"]').waitFor({timeout:15000});await offline.page.getByText('Live',{exact:true}).waitFor({timeout:15000});
  report.reconnect_ms=Date.now()-recoveryStart;
  if(config.burst){
    phase='burst';const burstStart=Date.now(),burstCount=count*30;
    for(let n=0;n<burstCount;n++){
      await wait(Math.max(0,burstStart+n*60000/burstCount-Date.now()));
      const i=n%count;chains[i]=chains[i].then(()=>send(n,'burst',burstStart+240000)).catch(e=>failures.push(String(e)));
    }
    await wait(Math.max(0,burstStart+60000-Date.now()));
    report.burst={offered:burstCount,offered_seconds:60,accepted_during_minute:accepted.length-report.steady_accepted};phase='recovery';
    await Promise.all(chains);report.burst.recovery_seconds=(Date.now()-burstStart-60000)/1000;
    await wait(10000);report.burst.final_snapshots=0;
    for(const source of config.sources){
      const last=rendered.get(source.index+':'+revisions[source.index]);
      if(last?.title==='burst '+source.index+' revision '+revisions[source.index])report.burst.final_snapshots++;
    }
    report.burst.accepted=accepted.length-report.steady_accepted;report.burst.quotas=quotas;
  }
  Object.assign(report,{accepted:accepted.length,page_errors:errors,http_errors:httpErrors,failures,transport_retries:transportRetries});
  await writeFile(path.join(config.output,'live-load.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({accepted:report.accepted,rendered:report.rendered,live:report.live,burst:report.burst,errors:failures.length}));
  assert.equal(missing.length,0);assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);assert.deepEqual(httpErrors.filter(e=>e.phase==='steady'),[]);
  assert.ok(report.live.p95_ms<=3000&&report.live.p99_ms<=10000);assert.ok(report.ingest_http.p95_ms<=500&&report.ingest_http.p99_ms<=2000);
  assert.ok(report.action_available_http.p95_ms<=3000);assert.ok(report.reconnect_ms<=10000);
  if(report.burst){assert.equal(report.burst.accepted,count*30);assert.equal(report.burst.final_snapshots,count);assert.ok(quotas.burst>0);}
}finally{await browser.close();}
