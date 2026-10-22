import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function studioAcceptance(browser,config,check){
  const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
  const editorContext=await browser.newContext(),editor=await editorContext.newPage();
  const suffix=randomUUID().slice(0,8),username='studio_'+suffix,editorName='editor_'+suffix;
  let botID,operational,channelID,orgID;
  const base=()=>'/studio/'+orgID;
  const go=async route=>{await page.goto(config.origin+'/app/#'+route);};
  const shot=async name=>{
    await page.locator('#sidebar').getByRole('link',{name:'＋ Open a channel',exact:true}).waitFor();
    await page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});
  };
  const send=async(method,route,body,key)=>{
    const response=await fetch(config.origin+'/v1'+route,{method,headers:{'Content-Type':'application/json',Origin:config.origin,...(key?{Authorization:'Bearer '+key}:{})},body:body===undefined?undefined:JSON.stringify(body)});
    assert.ok(response.ok,'HTTP service operation: '+response.status);return response.status===204?null:response.json();
  };
  const registerUI=async(p,name)=>{
    await p.goto(config.origin+'/app/#/register');await p.getByLabel('Display name',{exact:true}).fill(name);
    await p.getByLabel('Username',{exact:true}).fill(name);await p.getByLabel('Password',{exact:true}).fill(config.credentials.password);
    await p.getByRole('button',{name:'Create account',exact:true}).click();await p.getByRole('heading',{name:'My Space',exact:true}).waitFor();
  };
  try{
    await check('Studio: new owner creates workspace and registers bot in Web',async()=>{
      await registerUI(page,username);await page.getByRole('link',{name:'Studio',exact:true}).click();
      await page.getByLabel('Workspace name',{exact:true}).fill('Everyday Studio');await page.getByRole('button',{name:'Create workspace',exact:true}).click();
      await page.getByRole('heading',{name:'Bots',exact:true}).waitFor();orgID=new URL(page.url()).hash.split('/')[2];
      await page.getByLabel('Bot name',{exact:true}).fill('My HTTP catalog');await page.getByRole('button',{name:'Register bot',exact:true}).click();
      const credential=await page.getByLabel('One-time credential',{exact:true}).inputValue();
      const issued=await send('POST','/bot-registrations/exchange',{},credential);botID=issued.bot_id;operational=issued.api_key;
      await page.getByRole('button',{name:'I have saved it',exact:true}).click();await page.getByRole('heading',{name:'My HTTP catalog',exact:true}).waitFor();
      assert.equal((await page.locator('body').innerText()).includes(credential),false);
      assert.equal((await page.locator('body').innerText()).includes(operational),false);
      await shot('studio-bot');
    });
    await check('Studio: rotate key once; old credential rejected',async()=>{
      await page.getByRole('button',{name:'Rotate key',exact:true}).first().click();await page.getByRole('button',{name:'Rotate now',exact:true}).click();
      const replacement=await page.getByLabel('One-time credential',{exact:true}).inputValue();
      await page.getByRole('button',{name:'I have saved it',exact:true}).click();
      const old=await fetch(config.origin+'/v1/bot/identity',{headers:{Authorization:'Bearer '+operational}});assert.equal(old.status,401);operational=replacement;
      await page.reload();await page.getByRole('heading',{name:'Key inventory',exact:true}).waitFor();
      assert.equal((await page.locator('body').innerText()).includes(operational),false);
      assert.equal(await page.evaluate(()=>Object.values(localStorage).concat(Object.values(sessionStorage)).some(v=>v.includes('mb_')||v.includes('mr_'))),false);
    });
    await check('Studio: real HTTP data becomes saved blocks and published page',async()=>{
      await go(base());await page.getByLabel('Page title',{exact:true}).fill('Daily essentials');await page.getByLabel('Page slug',{exact:true}).fill('daily-'+suffix);
      await page.getByRole('button',{name:'Create page',exact:true}).click();await page.getByRole('heading',{name:'Page editor',exact:true}).waitFor();
      channelID=new URL(page.url()).hash.split('/')[4];assert.equal(await page.getByLabel('Audience',{exact:true}).inputValue(),'selected');
      const records=[['news','news',{title:'Studio daily news',body:'A local update. <img src=x onerror=alert(1)> javascript:alert(1) https://example.com/story'}],
        ['soap','product',{title:'Daily soap',description:'Everyday essential',price:{amount_minor:250,currency:'EUR'},availability:'in_stock'}],
        ['activity','chart',{title:'Requests this week',x_label:'Day',x_kind:'number',y_label:'Requests',unit:'requests',series:[{name:'Requests',points:[{x:1,y:3},{x:2,y:6}]}]}]];
      for(const [resource,type,payload]of records)await send('POST','/bot/messages',{schema_version:'1.0',message_id:randomUUID(),channel_id:channelID,resource_id:resource,source_revision:1,occurred_at:new Date().toISOString(),kind:'data',content_type:type,payload},operational);
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByLabel('Source to add',{exact:true}).waitFor();
      for(const resource of ['news','soap','activity']){await page.getByLabel('Source to add',{exact:true}).selectOption(resource);await page.getByRole('button',{name:'Add block',exact:true}).click();}
      await page.getByLabel('Allow Request purchase for Daily soap',{exact:true}).check();
      assert.equal(await page.getByRole('button',{name:'Publish',exact:true}).isDisabled(),true);
      await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByText('Draft v2 · Not published',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Preview saved draft',exact:true}).click();await page.getByRole('dialog').getByRole('heading',{name:'Studio daily news',exact:true}).waitFor();
      assert.equal(await page.getByRole('dialog').locator('img').count(),0);assert.equal(await page.getByRole('dialog').getByRole('button',{name:'Request purchase',exact:true}).count(),0);
      await page.getByRole('button',{name:'Close preview',exact:true}).click();await page.getByRole('button',{name:'Publish',exact:true}).click();await page.getByRole('button',{name:'Publish now',exact:true}).click();
      await page.getByText('Draft v2 · Live version v2',{exact:true}).waitFor();await shot('studio-editor');
    });
    await check('Studio: version conflict preserves local edits',async()=>{
      await page.getByLabel('Page title',{exact:true}).fill('Local unsaved title');
      const ownerRoute=config.origin+'/v1/owner/channels/'+channelID;
      const current=await (await context.request.get(ownerRoute)).json();const auth=await (await context.request.get(config.origin+'/v1/auth/session')).json();
      const update=await context.request.put(ownerRoute,{headers:{Origin:config.origin,'X-CSRF-Token':auth.csrf_token},data:{title:'Other editor title',visibility:current.visibility,actions:current.actions,expected_template_version:2,layout:{...current.layout,template_version:3}}});assert.equal(update.status(),200);
      await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByLabel('Page title',{exact:true}).inputValue(),'Local unsaved title');
      await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByText('Draft v3 · Live version v2',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Restore version',exact:true}).click();await page.getByRole('button',{name:'Restore and publish',exact:true}).click();await page.getByText('Draft v4 · Live version v4',{exact:true}).waitFor();
    });
    await check('Studio: Owner adds Editor; Editor publishes but cannot manage keys',async()=>{
      await registerUI(editor,editorName);await go(base()+'/team');await page.getByLabel('Registered username',{exact:true}).fill(editorName);
      await page.getByRole('button',{name:'Add or update member',exact:true}).click();await page.getByText('@'+editorName+' · editor',{exact:true}).waitFor();await shot('studio-team');
      await editor.goto(config.origin+'/app/#'+base()+'/bot/'+botID);await editor.getByRole('heading',{name:'My HTTP catalog',exact:true}).waitFor();assert.equal(await editor.getByRole('button',{name:'Issue operational key',exact:true}).count(),0);
      await editor.goto(config.origin+'/app/#'+base()+'/channel/'+channelID);await editor.getByRole('heading',{name:'Page editor',exact:true}).waitFor();assert.equal(await editor.getByLabel('Audience',{exact:true}).isDisabled(),true);
      assert.equal(await editor.getByRole('button',{name:'Grant read access',exact:true}).count(),0);
      await editor.getByLabel('Page title',{exact:true}).fill('Edited by team');await editor.getByRole('button',{name:'Save draft',exact:true}).click();await editor.getByText('Draft v5 · Live version v4',{exact:true}).waitFor();
      await editor.getByRole('button',{name:'Publish',exact:true}).click();await editor.getByRole('button',{name:'Publish now',exact:true}).click();await editor.getByText('Draft v5 · Live version v5',{exact:true}).waitFor();
    });
    await check('Studio: Admin sees key controls but cannot manage team; demotion refreshes permissions',async()=>{
      await page.getByLabel('Role for '+editorName,{exact:true}).selectOption('admin');await page.getByRole('button',{name:'Save role',exact:true}).click();await page.getByText('@'+editorName+' · admin',{exact:true}).waitFor();
      await editor.goto(config.origin+'/app/#'+base()+'/bot/'+botID);await editor.getByRole('button',{name:'Issue operational key',exact:true}).waitFor();
      await editor.goto(config.origin+'/app/#'+base()+'/team');await editor.getByRole('heading',{name:'Workspace team',exact:true}).waitFor();assert.equal(await editor.getByRole('button',{name:'Add or update member',exact:true}).count(),0);
      await page.getByLabel('Role for '+editorName,{exact:true}).selectOption('editor');await page.getByRole('button',{name:'Save role',exact:true}).click();await page.getByText('@'+editorName+' · editor',{exact:true}).waitFor();
      await editor.goto(config.origin+'/app/#'+base()+'/bot/'+botID);await editor.getByRole('heading',{name:'My HTTP catalog',exact:true}).waitFor();assert.equal(await editor.getByRole('button',{name:'Issue operational key',exact:true}).count(),0);
    });
    await check('Studio: removing a member immediately denies workspace reload',async()=>{
      await page.getByRole('button',{name:'Remove member',exact:true}).click();await page.getByRole('button',{name:'Remove',exact:true}).click();
      await page.getByText('@'+editorName+' · editor',{exact:true}).waitFor({state:'detached'});
      await page.getByRole('heading',{name:'Workspace team',exact:true}).waitFor();
      await editor.getByRole('button',{name:'Refresh',exact:true}).click();await editor.getByRole('heading',{name:'Workspace unavailable',exact:true}).waitFor();
    });
    await check('Studio: independent read grant and revocation via username',async()=>{
      await go(base()+'/channel/'+channelID);await page.getByLabel('Username to grant access',{exact:true}).fill(editorName);await page.getByRole('button',{name:'Grant read access',exact:true}).click();
      await page.getByText(editorName+' · @'+editorName,{exact:true}).waitFor();
      await editor.goto(config.origin+'/app/#/channel/daily-'+suffix);await editor.getByRole('heading',{name:'Edited by team',exact:true}).waitFor();
      await page.getByRole('button',{name:'Revoke read access',exact:true}).click();await page.getByRole('heading',{name:'Selected users',exact:true}).waitFor();
      await page.getByText(editorName+' · @'+editorName,{exact:true}).waitFor({state:'detached'});
      await editor.getByRole('button',{name:'Refresh',exact:true}).click();await editor.getByRole('heading',{name:'Channel unavailable',exact:true}).waitFor();
      await page.setViewportSize({width:360,height:800});await page.getByRole('heading',{name:'Page editor',exact:true}).waitFor();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await shot('studio-phone');
    });
    await check('Studio: saved page survives login; audience changes publish separately',async()=>{
      // Separate user journey: retain normal per-session read quotas during rapid automation.
      await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByLabel('Username',{exact:true}).fill(username);await page.getByLabel('Password',{exact:true}).fill(config.credentials.password);
      await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
      await go(base()+'/channel/'+channelID);await page.getByText('Draft v5 · Live version v5',{exact:true}).waitFor();
      await page.getByLabel('Audience',{exact:true}).selectOption('public');await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByText('Draft v6 · Live version v5',{exact:true}).waitFor();
      assert.equal((await fetch(config.origin+'/v1/channels/daily-'+suffix)).status,404);
      await page.getByRole('button',{name:'Publish',exact:true}).click();await page.getByRole('button',{name:'Publish now',exact:true}).click();await page.getByText('Draft v6 · Live version v6',{exact:true}).waitFor();
      assert.equal((await fetch(config.origin+'/v1/channels/daily-'+suffix)).status,200);
      await page.getByLabel('Audience',{exact:true}).selectOption('selected');await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByText('Draft v7 · Live version v6',{exact:true}).waitFor();
      await page.getByRole('button',{name:'Publish',exact:true}).click();await page.getByRole('button',{name:'Publish now',exact:true}).click();await page.getByText('Draft v7 · Live version v7',{exact:true}).waitFor();
      assert.equal((await fetch(config.origin+'/v1/channels/daily-'+suffix)).status,404);
    });
    await check('Studio: both key expiry reminders from actual server metadata',async()=>{
      await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByLabel('Username',{exact:true}).fill(config.credentials.username);await page.getByLabel('Password',{exact:true}).fill(config.credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
      const spaces=await (await context.request.get(config.origin+'/v1/workspaces')).json();const ownerOrg=spaces.items[0].org_id;
      await go('/studio/'+ownerOrg+'/bot/'+config.channels.catalog.bot_id);await page.getByText('Expires within 7 days',{exact:true}).waitFor();await shot('studio-expiring-key');
      await go('/studio/'+ownerOrg+'/bot/'+config.channels.news.bot_id);await page.getByText('Expired',{exact:true}).waitFor();await shot('studio-expired-key');
    });
  }catch(error){
    await page.screenshot({path:path.join(config.output,'studio-failure.png'),fullPage:true,mask:[page.getByLabel('One-time credential',{exact:true})]});
    throw error;
  }finally{await editorContext.close();await context.close();}
}
