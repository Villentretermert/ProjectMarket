import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function sharingAcceptance(browser,config,check){
  const author=await browser.newContext({viewport:{width:1440,height:1000}}),reader=await browser.newContext(),page=await author.newPage(),other=await reader.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));other.on('pageerror',e=>errors.push(e.message));
  const username='import_'+randomUUID().slice(0,8);let csrf,personal,code,copyID,userID;
  const go=async(p,route)=>p.goto(config.origin+'/app/#/'+route);
  const manage=async(method,route,data)=>{const r=await author.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':csrf,'Idempotency-Key':'acceptance_'+randomUUID()},data});assert.ok(r.ok(),'setup '+r.status());return r.status()===204?null:r.json();};
  const saved=async(p)=>p.locator('.space [role="status"]').filter({hasText:/^Saved · v/}).waitFor();
  try{
    await check('Sharing: lost create response replays one immutable link',async()=>{
      await go(page,'login');await page.getByLabel('Username',{exact:true}).fill(config.credentials.username);await page.getByLabel('Password',{exact:true}).fill(config.credentials.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
      csrf=(await(await author.request.get(config.origin+'/v1/auth/session')).json()).csrf_token;
      const source=await manage('GET','/channels/'+config.channels.catalog.slug),block=source.channel.layout.blocks.find(b=>b.block_id==='soap');
      personal=await manage('POST','/personal-pages',{title:'Shared everyday space',expected_template_version:0,layout:{schema_version:'1.0',template_version:1,theme:'ink',density:'comfortable',blocks:[block]}});
      await go(page,'space/'+personal.page_id);await saved(page);await page.getByRole('button',{name:'Share',exact:true}).click();
      const pattern='**/v1/personal-pages/'+personal.page_id+'/shares';let posts=0;
      await page.route(pattern,async route=>{if(route.request().method()!=='POST')return route.continue();const response=await route.fetch();posts++;if(posts===1)await route.abort();else await route.fulfill({response});});
      await page.getByRole('button',{name:'Create link',exact:true}).click();await page.getByRole('button',{name:'Retry create link',exact:true}).click();
      await page.getByLabel('Template code',{exact:true}).waitFor();code=await page.getByLabel('Template code',{exact:true}).inputValue();assert.equal(posts,2);
      assert.equal((await manage('GET','/personal-pages/'+personal.page_id+'/shares')).items.length,1);
      await page.screenshot({path:path.join(config.output,'share-dialog.png'),fullPage:true,mask:[page.getByLabel('Template code',{exact:true}),page.getByLabel('Template link',{exact:true})]});await page.unroute(pattern);
      await page.getByRole('button',{name:'Cancel',exact:true}).click();
    });
    await check('Sharing: import link survives registration and previews unavailable source',async()=>{
      await go(other,'import/'+code);await other.getByRole('link',{name:'New here? Create an account'}).click();
      await other.getByLabel('Display name',{exact:true}).fill('Import reader');await other.getByLabel('Username',{exact:true}).fill(username);await other.getByLabel('Password',{exact:true}).fill(config.credentials.password);await other.getByRole('button',{name:'Create account',exact:true}).click();
      await other.getByRole('heading',{name:'Import template',exact:true}).waitFor();assert.equal(await other.getByLabel('Template link or code',{exact:true}).inputValue(),code);
      await other.getByRole('button',{name:'Preview template',exact:true}).click();await other.getByRole('listitem').filter({hasText:'Source unavailable'}).waitFor();
      assert.equal(await other.getByText('Hand soap',{exact:true}).count(),0);
      await other.screenshot({path:path.join(config.output,'import-preview.png'),fullPage:true,mask:[other.getByLabel('Template link or code',{exact:true})]});
    });
    await check('Sharing: lost import response creates one independent owned page',async()=>{
      let posts=0;const pattern='**/v1/template-imports';
      await other.route(pattern,async route=>{const response=await route.fetch();posts++;if(posts===1)await route.abort();else await route.fulfill({response});});
      await other.getByRole('button',{name:'Import as new page',exact:true}).click();await other.getByText('Retry recovers the same imported page.',{exact:true}).waitFor();assert.equal(await other.getByLabel('Template link or code',{exact:true}).isDisabled(),true);await other.getByRole('button',{name:'Import as new page',exact:true}).click();await saved(other);
      copyID=new URL(other.url()).hash.split('/').at(-1);assert.equal(posts,2);await other.unroute(pattern);
      assert.equal(await other.getByLabel('Space title',{exact:true}).inputValue(),'Shared everyday space (copy)');await other.getByRole('heading',{name:'Source unavailable',exact:true}).waitFor();
      const pages=await(await reader.request.get(config.origin+'/v1/personal-pages')).json();assert.equal(pages.items.length,1);
    });
    await check('Sharing: new source grant reveals data without changing copied appearance',async()=>{
      userID=(await(await reader.request.get(config.origin+'/v1/auth/session')).json()).user.user_id;
      await manage('PUT','/owner/channels/'+config.channels.catalog.channel_id+'/grants/'+userID,{});
      await page.getByLabel('Theme',{exact:true}).selectOption('blue');await saved(page);
      await other.getByRole('button',{name:'Refresh',exact:true}).click();await saved(other);await other.getByRole('heading',{name:'Hand soap',exact:true}).waitFor();assert.equal(await other.getByLabel('Theme',{exact:true}).inputValue(),'ink');
      await other.setViewportSize({width:360,height:800});assert.equal(await other.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await other.screenshot({path:path.join(config.output,'import-phone.png'),fullPage:true});
    });
    await check('Sharing: revoke stops new previews while copied page remains',async()=>{
      await page.getByRole('button',{name:'Share',exact:true}).click();await page.getByRole('button',{name:'Revoke',exact:true}).click();await page.getByText('No active links.',{exact:true}).waitFor();
      await go(other,'import/'+code);await other.getByRole('button',{name:'Preview template',exact:true}).click();await other.getByText('This template is unavailable or expired.',{exact:true}).waitFor();
      await go(other,'space/'+copyID);await saved(other);await other.getByRole('heading',{name:'Hand soap',exact:true}).waitFor();
      await go(other,'import');await other.getByLabel('Template link or code',{exact:true}).fill('https://other.invalid/app/#/import/'+code);await other.getByRole('button',{name:'Preview template',exact:true}).click();await other.getByText('Use a link from this MarkeTOB server.',{exact:true}).waitFor();
    });
    assert.deepEqual(errors,[]);
  }finally{await author.close();await reader.close();}
}
