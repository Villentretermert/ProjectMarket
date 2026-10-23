import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function spaceAcceptance(browser,config,check){
  const owner=await browser.newContext(),first=await browser.newContext({viewport:{width:1440,height:1000}}),second=await browser.newContext();
  const page=await first.newPage(),other=await second.newPage(),username='space_'+randomUUID().slice(0,8),errors=[];
  page.on('pageerror',e=>errors.push(e.message));other.on('pageerror',e=>errors.push(e.message));
  const auth=await owner.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  const csrf=(await auth.json()).csrf_token,channels=config.channels;let pageID,userID,newsRecord,newsKey,initialPublisher;
  const manage=async(method,route,data)=>{const r=await owner.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':csrf},data});assert.ok(r.ok(),'Owner setup '+r.status());return r.status()===204?null:r.json();};
  const go=async(p,route)=>{const url=config.origin+'/app/#/'+route;if(p.url()===url)await p.reload();else await p.goto(url);};
  const saved=async(p=page)=>{await p.locator('.space [role="status"]').filter({hasText:/^Saved · v/}).waitFor();await p.getByRole('button',{name:'Preview',exact:true}).waitFor({state:'visible'});};
  const shot=async name=>{await page.locator('#sidebar').getByRole('link',{name:'＋ Open a channel',exact:true}).waitFor();await page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});};
  const loginUI=async(p)=>{await go(p,'login');await p.getByLabel('Username',{exact:true}).fill(username);await p.getByLabel('Password',{exact:true}).fill(config.credentials.password);await p.getByRole('button',{name:'Sign in',exact:true}).click();await p.getByRole('heading',{name:'My Space',exact:true}).waitFor();};
  const add=async(slug,block)=>{await page.getByLabel('Source channel',{exact:true}).selectOption(slug);await page.getByLabel('Block to add',{exact:true}).selectOption(block);await page.getByRole('button',{name:'Add block',exact:true}).click();await saved();};
  try{
    await check('My Space: build three live blocks from two favorite channels',async()=>{
      await go(page,'register');await page.getByLabel('Display name',{exact:true}).fill('Sam · My Space');await page.getByLabel('Username',{exact:true}).fill(username);await page.getByLabel('Password',{exact:true}).fill(config.credentials.password);await page.getByRole('button',{name:'Create account',exact:true}).click();await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
      userID=(await (await first.request.get(config.origin+'/v1/auth/session')).json()).user.user_id;
      for(const kind of ['catalog','news']){
        await manage('PUT','/owner/channels/'+channels[kind].channel_id+'/grants/'+userID,{});
        await go(page,'channel/'+channels[kind].slug);await page.getByRole('button',{name:'Add to favorites',exact:true}).click();await page.getByRole('button',{name:'Remove from favorites',exact:true}).waitFor();
      }
      initialPublisher=await manage('GET','/owner/channels/'+channels.catalog.channel_id);
      const news=await manage('GET','/channels/'+channels.news.slug);newsRecord=news.records.find(r=>r.source.resource_id===news.channel.layout.blocks.find(b=>b.block_id==='news_1').source.resource_id);
      await go(page,'space');await page.getByRole('button',{name:'Create My Space',exact:true}).click();await page.getByLabel('New page title',{exact:true}).fill('My daily space');await page.getByRole('button',{name:'Create page',exact:true}).click();await saved();
      pageID=new URL(page.url()).hash.split('/').at(-1);
      await add(channels.catalog.slug,'soap');await add(channels.news.slug,'news_1');await add(channels.news.slug,'feed_activity');
      assert.equal(await page.locator('[data-space-block]').count(),3);
      assert.equal(await page.locator('[data-space-block]').nth(1).locator('.body-text').isVisible(),true);
      await page.getByRole('img').waitFor();await shot('space-desktop');
    });
    await check('My Space: compatible views, appearance, order and Undo autosave independently',async()=>{
      await page.getByLabel('View for Hand soap',{exact:true}).selectOption('card');await saved();
      await page.getByLabel('Theme',{exact:true}).selectOption('ink');await saved();
      await page.getByLabel('Density',{exact:true}).selectOption('comfortable');await saved();
      const before=await page.locator('[data-space-block]').evaluateAll(rows=>rows.map(r=>r.dataset.spaceBlock));
      await page.locator('[data-space-block]').nth(2).getByRole('button',{name:'Move up',exact:true}).click();await saved();
      const reordered=await page.locator('[data-space-block]').evaluateAll(rows=>rows.map(r=>r.dataset.spaceBlock));assert.notDeepEqual(reordered,before);
      await page.getByRole('button',{name:'Undo',exact:true}).click();await saved();
      assert.deepEqual(await page.locator('[data-space-block]').evaluateAll(rows=>rows.map(r=>r.dataset.spaceBlock)),before);
      assert.deepEqual(await manage('GET','/owner/channels/'+channels.catalog.channel_id),initialPublisher);
      const newsSelect=page.getByLabel('View for '+newsRecord.content.title,{exact:true});assert.deepEqual(await newsSelect.locator('option').evaluateAll(os=>os.map(o=>o.value)),['article','compact']);
      await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await shot('space-phone');await page.setViewportSize({width:1440,height:1000});
    });
    await check('My Space: another session restores the saved layout and updated source revision',async()=>{
      await loginUI(other);await saved(other);assert.equal(await other.getByLabel('Space title',{exact:true}).inputValue(),'My daily space');assert.equal(await other.getByLabel('View for Hand soap',{exact:true}).inputValue(),'card');
      newsKey=(await manage('POST','/bots/'+channels.news.bot_id+'/keys',{scopes:['messages:write']})).api_key;
      const body={schema_version:'1.0',message_id:'space_news_'+randomUUID(),channel_id:channels.news.channel_id,resource_id:newsRecord.source.resource_id,source_revision:newsRecord.source_revision+1,occurred_at:new Date().toISOString(),kind:'text',payload:{title:'Updated pilot headline',body:'Source data changed. The personal layout is unchanged.'}};
      const response=await fetch(config.origin+'/v1/bot/messages',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+newsKey},body:JSON.stringify(body)});assert.equal(response.status,200);
      await other.getByRole('button',{name:'Refresh',exact:true}).click();await other.getByRole('heading',{name:'Updated pilot headline',exact:true}).waitFor();await saved(other);
    });
    await check('My Space: Request purchase reaches the original bot and returns its status',async()=>{
      await page.getByRole('button',{name:'Preview',exact:true}).click();await page.getByRole('button',{name:'Edit layout',exact:true}).waitFor();
      await page.getByRole('button',{name:'Request purchase',exact:true}).click();await page.getByRole('button',{name:'Send request',exact:true}).click();
      for(let i=0;i<15;i++){await page.getByRole('button',{name:'Check status',exact:true}).click();if(await page.getByText('Confirmed',{exact:true}).count())break;await page.waitForTimeout(500);}
      await page.getByText('Confirmed',{exact:true}).waitFor();await shot('space-preview');await page.getByRole('button',{name:'Edit layout',exact:true}).click();await saved();
    });
    await check('My Space: stale client keeps its edit; Reload saved resolves conflict explicitly',async()=>{
      await other.getByLabel('Space title',{exact:true}).fill('From second client');await other.getByLabel('Space title',{exact:true}).press('Enter');await saved(other);
      await page.getByLabel('Space title',{exact:true}).fill('Local conflicting title');await page.getByLabel('Space title',{exact:true}).press('Enter');await page.getByText('Not saved · Conflict with another client',{exact:true}).waitFor();
      assert.equal(await page.getByLabel('Space title',{exact:true}).inputValue(),'Local conflicting title');await shot('space-conflict');
      await page.getByRole('button',{name:'Reload saved',exact:true}).click();await saved();assert.equal(await page.getByLabel('Space title',{exact:true}).inputValue(),'From second client');
    });
    await check('My Space: lost autosave response replays the same version without another change',async()=>{
      let posts=0,firstVersion,replayVersion;const pattern='**/v1/personal-pages/'+pageID;
      await page.route(pattern,async route=>{
        if(route.request().method()!=='PUT'){await route.continue();return;}
        const response=await route.fetch(),body=await response.json();posts++;
        if(posts===1){firstVersion=body.layout.template_version;await route.abort();}else {replayVersion=body.layout.template_version;await route.fulfill({response});}
      });
      // Hold the source-picker response so its repaint happens during title entry.
      let release,started;const gate=new Promise(resolve=>{release=resolve;}),waiting=new Promise(resolve=>{started=resolve;});
      const sourcePattern='**/v1/channels/'+await page.getByLabel('Source channel',{exact:true}).inputValue();
      await page.route(sourcePattern,async route=>{started();await gate;await route.continue();});
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await waiting;
      await page.getByLabel('Space title',{exact:true}).fill('My daily space');release();
      await page.getByLabel('Block to add',{exact:true}).getByRole('option').first().waitFor({state:'attached'});
      assert.equal(await page.getByLabel('Space title',{exact:true}).inputValue(),'My daily space');await page.unroute(sourcePattern);
      await page.getByLabel('Space title',{exact:true}).press('Enter');await page.getByText('Save not confirmed',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Retry save',exact:true}).click();await saved();assert.equal(posts,2);assert.equal(firstVersion,replayVersion);await page.unroute(pattern);
    });
    await check('My Space: real revocation and deletion hide only affected sources and picker titles',async()=>{
      const newsTitle=(await manage('GET','/owner/channels/'+channels.news.channel_id)).title;
      await manage('DELETE','/owner/channels/'+channels.news.channel_id+'/grants/'+userID);
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByRole('heading',{name:'Source unavailable',exact:true}).first().waitFor();await saved();
      assert.equal(await page.getByRole('heading',{name:'Hand soap',exact:true}).count(),1);assert.equal(await page.getByText('Updated pilot headline',{exact:true}).count(),0);
      assert.equal(await page.getByLabel('Source channel',{exact:true}).getByRole('option',{name:newsTitle,exact:true}).count(),0);
      await shot('space-revoked');
      await page.locator('[data-space-block]').nth(1).getByRole('button',{name:'Move down',exact:true}).click();await saved();
      await manage('PUT','/owner/channels/'+channels.news.channel_id+'/grants/'+userID,{});
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByRole('heading',{name:'Updated pilot headline',exact:true}).waitFor();await saved();
      const deletion={schema_version:'1.0',message_id:'space_delete_'+randomUUID(),channel_id:channels.news.channel_id,resource_id:newsRecord.source.resource_id,source_revision:newsRecord.source_revision+2,occurred_at:new Date().toISOString(),kind:'delete'};
      const response=await fetch(config.origin+'/v1/bot/messages',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+newsKey},body:JSON.stringify(deletion)});assert.equal(response.status,200);
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await saved();await page.getByRole('heading',{name:'Source unavailable',exact:true}).waitFor();
      assert.equal(await page.getByRole('heading',{name:'Hand soap',exact:true}).count(),1);assert.equal(await page.getByRole('img').count(),1);
      const stored=await page.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}));assert.ok(!stored.includes('Updated pilot headline')&&!stored.includes(newsKey));
    });
    assert.deepEqual(errors,[]);
  }catch(error){await page.screenshot({path:path.join(config.output,'space-failure.png'),fullPage:true});throw error;}
  finally{await owner.close();await first.close();await second.close();}
}
