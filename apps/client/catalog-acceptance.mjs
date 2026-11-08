import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function catalogAcceptance(browser,config,check){
  const owner=await browser.newContext(),reader=await browser.newContext({viewport:{width:1440,height:1080}}),page=await reader.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const login=await owner.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  const csrf=(await login.json()).csrf_token;
  const manage=async(method,route,data)=>{
    const r=await owner.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':csrf},data});
    assert.ok(r.ok(),'Owner setup '+r.status());return r.status()===204?null:r.json();
  };
  const auth=await reader.request.post(config.origin+'/v1/auth/register',{headers:{Origin:config.origin},data:{username:'catalog_'+randomUUID().slice(0,10),password:config.credentials.password,display_name:'Alex · Catalog demo'}});
  assert.equal(auth.status(),201);const session=await auth.json();
  const userID=(await (await reader.request.get(config.origin+'/v1/auth/session')).json()).user.user_id;
  const {catalog,news}=config.channels;
  for(const channel of [catalog,news]){
    await manage('PUT','/owner/channels/'+channel.channel_id+'/grants/'+userID,{});
    const r=await reader.request.put(config.origin+'/v1/favorites/'+channel.channel_id,{headers:{Origin:config.origin,'X-CSRF-Token':session.csrf_token},data:{}});assert.ok(r.ok());
  }
  const grid=page.getByRole('region',{name:'Block catalog',exact:true});
  const source=page.getByLabel('Source channel',{exact:true});
  const saved=async()=>page.locator('.space>p[role="status"]').filter({hasText:/^Saved · v/}).waitFor();
  const add=async id=>{await page.locator('[data-catalog-block="'+id+'"]').getByRole('button',{name:'Add to My Space',exact:true}).click();await saved();};
  const shot=async name=>page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});
  let pageID;
  try{
    await page.goto(config.origin+'/app/#/space');await page.getByRole('button',{name:'Create My Space',exact:true}).click();
    await page.getByLabel('New page title',{exact:true}).fill('My catalog space');await page.getByRole('button',{name:'Create page',exact:true}).click();await saved();
    pageID=new URL(page.url()).hash.split('/').at(-1);
    await check('Block catalog: real previews, search and types never expose purchase controls',async()=>{
      await source.selectOption(catalog.slug);await page.locator('[data-catalog-block="soap"]').waitFor();
      assert.equal(await grid.locator('[data-catalog-block]').count(),4);assert.equal(await grid.getByText('€2.50',{exact:true}).count(),1);
      assert.equal(await grid.getByRole('button',{name:'Request purchase',exact:true}).count(),0);
      await page.getByLabel('Search blocks',{exact:true}).fill('pantry');assert.equal(await grid.locator('[data-catalog-block]').count(),1);
      await grid.getByRole('heading',{name:'Rice, 1 kg',exact:true}).waitFor();
      await page.getByLabel('Block type',{exact:true}).selectOption('news');await grid.getByText('No blocks match your filters.',{exact:true}).waitFor();
      await grid.getByRole('button',{name:'Clear filters',exact:true}).click();assert.equal(await page.getByLabel('Search blocks',{exact:true}).inputValue(),'');
      assert.equal(await grid.locator('[data-catalog-block]').count(),4);await shot('catalog-desktop');
    });
    await check('Block catalog: keyboard addition, autosave and Undo preserve source references',async()=>{
      const addButton=page.locator('[data-catalog-block="soap"]').getByRole('button',{name:'Add to My Space',exact:true});
      await addButton.focus();await page.keyboard.press('Enter');await saved();
      await page.waitForFunction(()=>document.activeElement?.closest('[data-catalog-block]')?.dataset.catalogBlock==='soap');
      await page.locator('[data-space-block]').waitFor();assert.equal(await page.locator('[data-space-block]').count(),1);
      await page.getByRole('button',{name:'Undo',exact:true}).focus();await page.keyboard.press('Enter');await saved();
      assert.equal(await page.locator('[data-space-block]').count(),0);await add('soap');
      await source.selectOption(news.slug);await add('news_2');assert.equal(await page.locator('[data-space-block]').count(),2);
      await page.getByLabel('Block type',{exact:true}).selectOption('chart');await grid.getByRole('img').waitFor();assert.equal(await grid.locator('[data-catalog-block]').count(),1);
      await page.getByLabel('Block type',{exact:true}).selectOption('all');
    });
    await check('Block catalog: a source with no personal block still loses access live',async()=>{
      // Remove the news block temporarily: the catalog itself must watch its source.
      await page.locator('[data-space-block]').nth(1).getByRole('button',{name:'Remove block',exact:true}).click();await saved();
      await source.selectOption(news.slug);await page.locator('[data-catalog-block="news_2"]').waitFor();
      await manage('DELETE','/owner/channels/'+news.channel_id+'/grants/'+userID);
      await page.locator('[data-catalog-block="news_2"]').waitFor({state:'hidden',timeout:15000});
      assert.equal(await source.getByRole('option',{name:news.title,exact:true}).count(),0);
      await manage('PUT','/owner/channels/'+news.channel_id+'/grants/'+userID,{});
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await saved();
      await source.selectOption(news.slug);await add('news_2');
    });
    await check('Block catalog: 360px, empty filters and text-only previews',async()=>{
      await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await shot('catalog-phone');
      await page.setViewportSize({width:1440,height:1080});
      const pattern='**/v1/channels/'+news.slug;
      await page.route(pattern,async route=>{const response=await route.fetch(),body=await response.json();for(const record of body.records)if(record.kind==='text'||record.content.body!==undefined){record.content.title='<img src=x onerror=alert(1)>';record.content.body='javascript:alert(1) https://example.com/test';}await route.fulfill({response,json:body});});
      await source.selectOption(news.slug);await grid.getByRole('heading',{name:'<img src=x onerror=alert(1)>',exact:true}).first().waitFor();
      assert.equal(await grid.locator('img,iframe,a').count(),0);await page.unroute(pattern);
    });
    await check('Block catalog: a late source response cannot replace the selected channel',async()=>{
      let release,started;const gate=new Promise(r=>release=r),waiting=new Promise(r=>started=r),pattern='**/v1/channels/'+news.slug;
      await page.route(pattern,async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response});});
      await source.selectOption(news.slug);await waiting;await source.selectOption(catalog.slug);
      await grid.getByRole('heading',{name:'Hand soap',exact:true}).waitFor();release();await page.unrouteAll({behavior:'wait'});
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      assert.equal(await source.inputValue(),catalog.slug);assert.equal(await grid.locator('[data-catalog-block="news_2"]').count(),0);
    });
    await check('Block catalog: network retry rechecks data without losing layout',async()=>{
      const before=await (await reader.request.get(config.origin+'/v1/personal-pages/'+pageID)).json();
      const pattern='**/v1/channels/'+news.slug;await page.route(pattern,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Service temporarily unavailable.'})}));
      await source.selectOption(news.slug);await page.getByText('Service temporarily unavailable.',{exact:true}).waitFor();assert.equal(await grid.locator('[data-catalog-block]').count(),0);
      await page.unroute(pattern);await page.getByRole('button',{name:'Check again',exact:true}).first().click();await page.locator('[data-catalog-block="news_2"]').waitFor();
      const after=await (await reader.request.get(config.origin+'/v1/personal-pages/'+pageID)).json();assert.deepEqual(after,before);
    });
    await check('Block catalog: real revoke clears preview and Check again restores only authorized data',async()=>{
      const before=await (await reader.request.get(config.origin+'/v1/personal-pages/'+pageID)).json();
      await manage('DELETE','/owner/channels/'+news.channel_id+'/grants/'+userID);
      await page.locator('.space>.blocks').getByRole('heading',{name:'Source unavailable',exact:true}).waitFor({timeout:15000});
      assert.equal(await grid.locator('[data-catalog-block="news_2"]').count(),0);
      assert.equal(await source.getByRole('option',{name:news.title,exact:true}).count(),0);
      await shot('catalog-source-unavailable');
      await manage('PUT','/owner/channels/'+news.channel_id+'/grants/'+userID,{});
      await page.locator('.space>.blocks').getByRole('button',{name:'Check again',exact:true}).click();
      await page.locator('.space>.blocks [data-space-block]').nth(1).getByRole('heading',{level:2}).waitFor();
      assert.deepEqual(await (await reader.request.get(config.origin+'/v1/personal-pages/'+pageID)).json(),before);
    });
    await check('Block catalog: offline hides previews and reconnect reads authorized data',async()=>{
      await reader.setOffline(true);await page.getByRole('heading',{name:'You are offline',exact:true}).waitFor();assert.equal(await page.locator('[data-catalog-block]').count(),0);
      await reader.setOffline(false);await saved();await page.locator('[data-catalog-block]').first().waitFor();
      assert.equal(await page.locator('[data-space-block]').count(),2);
    });
    await check('Block catalog: empty publication and the 50-block limit are explicit',async()=>{
      const pattern='**/v1/channels/'+catalog.slug;
      await page.route(pattern,async route=>{const response=await route.fetch(),body=await response.json();body.channel.layout.blocks=[];body.records=[];await route.fulfill({response,json:body});});
      await source.selectOption(catalog.slug);await grid.getByText('This channel has no available published blocks.',{exact:true}).waitFor();await page.unroute(pattern);
      const current=await (await reader.request.get(config.origin+'/v1/personal-pages/'+pageID)).json();
      const full={title:current.title,expected_template_version:current.layout.template_version,layout:{...current.layout,template_version:current.layout.template_version+1,blocks:Array.from({length:50},(_,n)=>({...current.layout.blocks[0],block_id:'limit_'+n}))}};
      const r=await reader.request.put(config.origin+'/v1/personal-pages/'+pageID,{headers:{Origin:config.origin,'X-CSRF-Token':session.csrf_token},data:full});assert.ok(r.ok());
      await page.reload();await saved();await grid.getByText('Your space has 50 blocks. Remove one to add another.',{exact:true}).waitFor();
      for(const add of await grid.getByRole('button',{name:'Add to My Space',exact:true}).all())assert.equal(await add.isDisabled(),true);
      await page.locator('[data-space-block]').last().getByRole('button',{name:'Remove block',exact:true}).click();await saved();
      await page.waitForFunction(()=>document.querySelector('.catalog-card>button')?.disabled===false);
      assert.equal(await page.locator('[data-space-block]').count(),49);
    });
    assert.deepEqual(errors,[]);
  }catch(error){await shot('catalog-failure');throw error;}
  finally{await owner.close();await reader.close();}
}
