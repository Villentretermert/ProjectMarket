import assert from 'node:assert/strict';
import path from 'node:path';
import {readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';

export async function privacyAcceptance(browser,config,check){
  const owner=await browser.newContext({viewport:{width:1440,height:1000}}),admin=await browser.newContext();
  const page=await owner.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  const suffix=randomUUID().slice(0,8),username='privacy_'+suffix,successor='successor_'+suffix,password=config.credentials.password;
  const register=async(context,name)=>{
    const r=await context.request.post(config.origin+'/v1/auth/register',{headers:{Origin:config.origin},data:{username:name,password,display_name:name===username?'Alex · Privacy demo':'Sam · New owner'}});
    assert.equal(r.status(),201);return r.json();
  };
  const account=await register(owner,username),next=await register(admin,successor);
  const call=async(method,route,data)=>{
    const r=await owner.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':account.csrf_token,'Idempotency-Key':'privacy_'+randomUUID()},data});
    assert.ok(r.ok(),'privacy setup '+r.status());return r.status()===204?null:r.json();
  };
  const org=await call('PUT','/account/business-profile',{name:'Everyday goods'});
  await call('PUT','/workspaces/'+org.org_id+'/members',{username:successor,role:'admin'});
  const bot=await call('POST','/bots',{name:'Privacy demo bot'});
  await call('POST','/personal-pages',{title:'My daily view',expected_template_version:0,layout:{schema_version:'1.0',template_version:1,theme:'blue',density:'compact',blocks:[]}});
  try{
    await check('Privacy: owner sees transfer guard; JSON contains only personal projections',async()=>{
      await page.goto(config.origin+'/app/#/privacy');await page.getByRole('heading',{name:'Data & privacy',exact:true}).waitFor();
      await page.getByRole('heading',{name:'Transfer ownership first',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Review deletion',exact:true}).count(),0);
      const saved=page.waitForEvent('download');await page.getByRole('button',{name:'Download JSON',exact:true}).click();
      const download=await saved,file=path.join(config.output,'personal-export.json');await download.saveAs(file);
      const raw=await readFile(file,'utf8'),data=JSON.parse(raw);
      assert.equal(data.profile[0].user_id,account.user.user_id);assert.equal(data.spaces[0].title,'My daily view');assert.deepEqual(data.requests,[]);
      for(const forbidden of [password,bot.registration_credential,next.user.user_id,'csrf_token','password_hash','api_key'])assert.ok(!raw.includes(forbidden));
      await page.screenshot({path:path.join(config.output,'privacy-owner.png'),fullPage:true});
      await page.setViewportSize({width:360,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(config.output,'privacy-owner-phone.png'),fullPage:true});await page.setViewportSize({width:1440,height:1000});
    });
    await check('Privacy: interrupted export shows failure and never downloads a partial file',async()=>{
      let downloads=0;const observe=()=>downloads++;page.on('download',observe);
      await page.route('**/v1/account/export?section=requests',route=>route.abort());
      await page.getByRole('button',{name:'Download JSON',exact:true}).click();await page.getByText('Export was not completed. No partial file was downloaded.',{exact:true}).waitFor();
      assert.equal(downloads,0);assert.equal(await page.getByRole('button',{name:'Download JSON',exact:true}).isEnabled(),true);
      await page.unroute('**/v1/account/export?section=requests');page.off('download',observe);
    });
    await check('Privacy: Studio transfers ownership after password confirmation',async()=>{
      await page.getByRole('link',{name:'Open team: Everyday goods',exact:true}).click();
      await page.getByLabel('Current password for transfer',{exact:true}).fill(password);
      await page.getByRole('button',{name:'Review transfer',exact:true}).click();
      await page.getByRole('dialog').waitFor();await page.screenshot({path:path.join(config.output,'privacy-transfer.png'),fullPage:true});
      await page.getByRole('button',{name:'Transfer ownership now',exact:true}).click();
      await page.locator('.page-head p').filter({hasText:'Everyday goods · admin'}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Review transfer',exact:true}).count(),0);
      const result=await admin.request.get(config.origin+'/v1/account/business-profile',{headers:{Origin:config.origin}});
      assert.equal((await result.json()).org_id,org.org_id);
    });
    await check('Privacy: password and DELETE guard deletion; cancel preserves account',async()=>{
      await page.getByRole('link',{name:'Data & privacy',exact:true}).click();
      await page.getByLabel('Current password',{exact:true}).fill(password);await page.getByLabel('Type DELETE to confirm',{exact:true}).fill('delete');
      await page.getByRole('button',{name:'Review deletion',exact:true}).click();assert.equal(await page.getByRole('dialog').count(),0);
      await page.getByLabel('Type DELETE to confirm',{exact:true}).fill('DELETE');await page.getByLabel('Current password',{exact:true}).fill('wrong-password');
      await page.getByRole('button',{name:'Review deletion',exact:true}).click();await page.getByRole('button',{name:'Delete account permanently',exact:true}).click();
      await page.getByText('Password verification failed.',{exact:true}).waitFor();assert.equal(await page.getByLabel('Current password',{exact:true}).inputValue(),'');
      await page.getByLabel('Current password',{exact:true}).fill(password);await page.getByRole('button',{name:'Review deletion',exact:true}).click();
      await page.getByRole('button',{name:'Cancel',exact:true}).click();await page.waitForFunction(()=>document.querySelector('input[type=password]')?.value==='');
      assert.equal((await owner.request.get(config.origin+'/v1/auth/session',{headers:{Origin:config.origin}})).status(),200);
    });
    await check('Privacy: confirmed deletion clears local state; successor keeps workspace',async()=>{
      await page.getByLabel('Current password',{exact:true}).fill(password);await page.getByRole('button',{name:'Review deletion',exact:true}).click();
      await page.getByRole('dialog').waitFor();await page.screenshot({path:path.join(config.output,'privacy-delete.png'),fullPage:true});
      await page.getByRole('button',{name:'Delete account permanently',exact:true}).click();await page.getByLabel('Username',{exact:true}).waitFor();
      assert.equal((await owner.request.get(config.origin+'/v1/account/export',{headers:{Origin:config.origin}})).status(),401);
      assert.equal(await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('marketob-request:')).length),0);
      assert.equal((await admin.request.get(config.origin+'/v1/bots/'+bot.bot.bot_id,{headers:{Origin:config.origin}})).status(),200);
    });
    assert.deepEqual(errors,[]);
  }catch(error){await page.screenshot({path:path.join(config.output,'privacy-failure.png'),fullPage:true});throw error;}
  finally{await owner.close();await admin.close();}
}
