import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function liveAcceptance(browser,config,check){
  const owner=await browser.newContext(),reader=await browser.newContext({viewport:{width:1440,height:1000}});
  await reader.addInitScript(()=>{if(window.Notification)Object.defineProperty(Notification,'permission',{get:()=> 'denied'});});
  const page=await reader.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const auth=await owner.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  const csrf=(await auth.json()).csrf_token;
  const manage=async(method,route,data)=>{const r=await owner.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':csrf},data});assert.ok(r.ok(),'owner setup '+r.status());return r.status()===204?null:r.json();};
  const registered=await reader.request.post(config.origin+'/v1/auth/register',{headers:{Origin:config.origin},data:{username:'live_'+randomUUID().slice(0,8),display_name:'Live reader',password:config.credentials.password}});
  const account=await registered.json(),user=account.user.user_id;
  const customer=async(method,route,data)=>{const r=await reader.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':account.csrf_token,'Idempotency-Key':'live_'+randomUUID()},data});assert.ok(r.ok(),'reader setup '+r.status());return r.status()===204?null:r.json();};
  const source=await manage('POST','/channels',{bot_id:config.channels.news.bot_id,slug:'live-'+randomUUID().slice(0,12),title:'Local live news'});
  const key=(await manage('POST','/bots/'+config.channels.news.bot_id+'/keys',{scopes:['messages:write']})).api_key;
  let revision=0,personal;const metrics={};
  const publish=async title=>{
    const r=await fetch(config.origin+'/v1/bot/messages',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+key},body:JSON.stringify({schema_version:'1.0',message_id:'live_'+randomUUID(),channel_id:source.channel_id,resource_id:'live_news',source_revision:++revision,occurred_at:new Date().toISOString(),kind:'text',payload:{title,body:'Synthetic news for automatic update verification.'}})});
    assert.equal(r.status,200);return Date.now();
  };
  const go=async route=>page.goto(config.origin+'/app/#/'+route);
  const shown=title=>page.getByRole('heading',{name:title,exact:true}).waitFor({timeout:10000});
  try{
    await publish('First live headline');
    const current=await manage('GET','/owner/channels/'+source.channel_id),version=current.layout.template_version;
    const block={block_id:'live_news',source:{channel_id:source.channel_id,resource_id:'live_news'},content_type:'news',view:'article',action_ids:[]};
    await manage('PUT','/owner/channels/'+source.channel_id,{title:current.title,visibility:'selected',expected_template_version:version,layout:{...current.layout,template_version:version+1,blocks:[block]},actions:[]});
    await manage('POST','/owner/channels/'+source.channel_id+'/publish',{expected_template_version:version+1});
    await manage('PUT','/owner/channels/'+source.channel_id+'/grants/'+user,{});
    await customer('PUT','/favorites/'+source.channel_id,{});
    personal=await customer('POST','/personal-pages',{title:'Live personal space',expected_template_version:0,layout:{schema_version:'1.0',template_version:1,theme:'blue',density:'compact',blocks:[block]}});
    await check('Live: automatic source updates preserve a focused title and layout',async()=>{
      await go('space/'+personal.page_id);await shown('First live headline');
      await page.getByLabel('Space title',{exact:true}).fill('Still typing this title');
      await publish('Second live headline');await shown('Second live headline');
      assert.equal(await page.getByLabel('Space title',{exact:true}).inputValue(),'Still typing this title');
      assert.equal((await customer('GET','/personal-pages/'+personal.page_id)).layout.template_version,1);
      await page.getByLabel('Space title',{exact:true}).press('Enter');await page.getByText('Saved · v2',{exact:true}).waitFor();
      await page.screenshot({path:path.join(config.output,'live-space.png'),fullPage:true});
    });
    await check('Live: opt-in events work when OS notifications are denied',async()=>{
      await go('channel/'+source.slug);await shown('Second live headline');
      assert.equal(await page.evaluate(()=>Notification.permission),'denied');
      await page.getByRole('button',{name:'Events',exact:true}).click();
      await page.waitForFunction(()=>document.querySelector('input[aria-label="My request status"]')?.checked);
      assert.equal(await page.getByLabel('News updates',{exact:true}).isChecked(),false);
      await page.getByLabel('News updates',{exact:true}).check();await page.getByLabel('My request status',{exact:true}).uncheck();
      await page.screenshot({path:path.join(config.output,'live-events.png'),fullPage:true});
      await page.getByRole('button',{name:'Save',exact:true}).click();
      await publish('Selected event headline');await shown('Selected event headline');await page.getByText('News updated',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Events',exact:true}).click();await page.getByLabel('News updates',{exact:true}).uncheck();await page.getByRole('button',{name:'Save',exact:true}).click();
      await publish('Silent update headline');await shown('Silent update headline');
      assert.deepEqual((await customer('GET','/preferences/'+source.channel_id)).events,[]);
    });
    await check('Live: repeated delivery does not repeat the selected toast',async()=>{
      await customer('PUT','/preferences/'+source.channel_id,{channel_id:source.channel_id,events:['news.published']});
      await page.evaluate(()=>{window.liveToastCount=0;new MutationObserver(()=>{if(document.querySelector('#toast').textContent==='News updated')window.liveToastCount++;}).observe(document.querySelector('#toast'),{childList:true,subtree:true});});
      const pattern='**/v1/updates?*';let replay=null,repeated=false,done;const completed=new Promise(resolve=>{done=resolve;});
      await page.route(pattern,async route=>{
        if(replay){const value=replay;replay=null;repeated=true;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(value)});done();return;}
        const response=await route.fetch(),value=await response.json();
        if(!repeated&&value.items?.some(i=>i.notify))replay=value;
        await route.fulfill({response});
      });
      await publish('Replay-safe headline');await shown('Replay-safe headline');await completed;
      await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>window.liveToastCount),1);
      await page.unroute(pattern);await customer('PUT','/preferences/'+source.channel_id,{channel_id:source.channel_id,events:[]});
    });
    await check('Live: lost connection and expired cursor resync without refresh',async()=>{
      const pattern='**/v1/updates?*';await page.route(pattern,route=>route.abort());
      await page.getByText('Reconnecting · Content hidden',{exact:true}).waitFor();assert.equal(await page.getByText('Replay-safe headline',{exact:true}).count(),0);
      await publish('Recovered live headline');const start=Date.now();await page.unroute(pattern);await shown('Recovered live headline');metrics.lost_reply_recovery_ms=Date.now()-start;assert.ok(metrics.lost_reply_recovery_ms<10000);
      let expired=false;await page.route(pattern,async route=>{if(!expired){expired=true;return route.fulfill({status:410,contentType:'application/json',body:JSON.stringify({code:'cursor_expired',message:'Refresh snapshots.'})});}await route.continue();});
      await page.getByText('Reconnecting · Content hidden',{exact:true}).waitFor();await publish('After cursor expiry');await shown('After cursor expiry');await page.unroute(pattern);
      await reader.setOffline(true);await page.getByRole('heading',{name:'You are offline',exact:true}).waitFor();
      await publish('After network recovery');const online=Date.now();await reader.setOffline(false);await shown('After network recovery');metrics.offline_recovery_ms=Date.now()-online;assert.ok(metrics.offline_recovery_ms<10000);
    });
    await check('Live: real revocation, restoration and second revocation clear private content',async()=>{
      await go('space/'+personal.page_id);await shown('After network recovery');
      for(let n=0;n<2;n++){
        await manage('DELETE','/owner/channels/'+source.channel_id+'/grants/'+user);await shown('Source unavailable');
        assert.equal(await page.getByText('After network recovery',{exact:true}).count(),0);
        if(n===0){await manage('PUT','/owner/channels/'+source.channel_id+'/grants/'+user,{});await shown('After network recovery');}
      }
      await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(config.output,'live-revoked-phone.png'),fullPage:true});
    });
    await check('Live: own purchase status arrives automatically from the real bot',async()=>{
      await manage('PUT','/owner/channels/'+config.channels.catalog.channel_id+'/grants/'+user,{});
      await go('channel/'+config.channels.catalog.slug);await shown('Hand soap');
      await page.locator('[data-block="soap"]').getByRole('button',{name:'Request purchase',exact:true}).click();
      await page.getByRole('button',{name:'Send request',exact:true}).click();
      await page.getByText('Confirmed',{exact:true}).waitFor({timeout:10000});
      await page.getByText('Request status updated',{exact:true}).waitFor();
    });
    assert.deepEqual(errors,[]);config.liveMetrics=metrics;
  }catch(error){await page.screenshot({path:path.join(config.output,'live-failure.png'),fullPage:true});throw error;}
  finally{await owner.close();await reader.close();}
}
