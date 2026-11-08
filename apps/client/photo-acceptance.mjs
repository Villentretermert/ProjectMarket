import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function photoAcceptance(browser,config,check){
  const owner=await browser.newContext(),reader=await browser.newContext({viewport:{width:1440,height:1000}}),outsider=await browser.newContext(),page=await reader.newPage();
  const errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(config.origin+'/'))external.push(r.url());});
  const login=await owner.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  assert.ok(login.ok());const ownerSession=await login.json();
  const register=async(context)=>{const r=await context.request.post(config.origin+'/v1/auth/register',{headers:{Origin:config.origin},data:{username:'photo_'+randomUUID().slice(0,10),password:config.credentials.password,display_name:'Photo demo'}});assert.equal(r.status(),201);return r.json();};
  const user=await register(reader),other=await register(outsider),catalog=config.channels.catalog;
  const call=async(context,session,method,route,data)=>{const r=await context.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':session.csrf_token,'Idempotency-Key':randomUUID()},data});assert.ok(r.ok(),'Photo setup '+r.status());return r.status()===204?null:r.json();};
  const grant='/owner/channels/'+catalog.channel_id+'/grants/'+user.user.user_id;
  const imageReady=async(selector)=>page.waitForFunction(s=>{const i=document.querySelector(s);return i?.complete&&i.naturalWidth===160;},selector);
  let personal;
  try{
    await call(owner,ownerSession,'PUT',grant,{});
    await check('Photos: real bot PNG and old products coexist without external requests',async()=>{
      await page.goto(config.origin+'/app/#/channel/'+catalog.slug);await imageReady('[data-block="soap"] img');
      assert.equal(await page.locator('[data-block="rice"] img').count(),0);
      assert.equal(await page.locator('[data-block="soap"] img').getAttribute('alt'),'Demo illustration: a teal hand soap bottle');
      await page.locator('[data-block="soap"]').getByRole('button',{name:'Request purchase',exact:true}).click();
      await page.getByRole('dialog',{name:'Confirm purchase request'}).press('Escape');
      await page.screenshot({path:path.join(config.output,'photos-list.png'),fullPage:true});
    });
    await check('Photos: Card retains the full image at desktop and 360px',async()=>{
      await page.locator('[data-block="soap"]').getByRole('combobox').selectOption('card');await imageReady('[data-block="soap"] img');
      assert.equal(await page.locator('[data-block="soap"] img').evaluate(i=>getComputedStyle(i).objectFit),'contain');
      assert.ok(await page.locator('[data-block="soap"] img').evaluate(i=>i.offsetHeight<=i.parentElement.clientHeight&&i.offsetWidth<=i.parentElement.clientWidth));
      await page.screenshot({path:path.join(config.output,'photos-card.png'),fullPage:true});
      await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      assert.ok(await page.locator('[data-block="soap"] img').evaluate(i=>i.offsetHeight<=i.parentElement.clientHeight&&i.offsetWidth<=i.parentElement.clientWidth));
      await page.screenshot({path:path.join(config.output,'photos-phone.png'),fullPage:true});
      await page.locator('[data-block="soap"]').getByRole('combobox').selectOption('list');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.setViewportSize({width:1440,height:1000});
    });
    await check('Photos: My Space and the block catalog render authorized source bytes',async()=>{
      await call(reader,user,'PUT','/favorites/'+catalog.channel_id,{});
      const snapshot=await call(reader,user,'GET','/channels/'+catalog.slug);
      const block=snapshot.channel.layout.blocks.find(b=>b.block_id==='soap');
      personal=await call(reader,user,'POST','/personal-pages',{title:'Product photos demo',expected_template_version:0,layout:{schema_version:'1.0',template_version:1,theme:'blue',density:'compact',blocks:[{...block,view:'card'}]}});
      await page.goto(config.origin+'/app/#/space/'+personal.page_id);await imageReady('[data-space-block] img');
      await page.getByLabel('Source channel',{exact:true}).selectOption(catalog.slug);await imageReady('[data-catalog-block="soap"] img');
      assert.equal(await page.locator('[data-catalog-block="soap"]').getByRole('button',{name:'Request purchase',exact:true}).count(),0);
      await page.screenshot({path:path.join(config.output,'photos-space.png'),fullPage:true});
    });
    await check('Photos: shared layout contains no photo bytes or source access',async()=>{
      const share=await call(reader,user,'POST','/personal-pages/'+personal.page_id+'/shares',{expected_template_version:personal.layout.template_version});
      const preview=await call(outsider,other,'POST','/template-imports/preview',{code:share.code});
      assert.deepEqual(preview.unavailable_blocks,['soap']);assert.ok(!JSON.stringify(preview).includes('data_base64'));
      const denied=await outsider.request.get(config.origin+'/v1/channels/'+catalog.slug);assert.equal(denied.status(),404);assert.ok(!await denied.text().then(s=>s.includes('data_base64')));
    });
    await check('Photos: malformed, URL and SVG fixtures fail closed with readable product details',async()=>{
      await page.evaluate(async()=>{
        const {renderBlock}=await import('/app/render.js');const host=document.createElement('section');host.id='photo-errors';document.querySelector('main').prepend(host);
        for(const [id,image] of Object.entries({broken:{media_type:'image/png',data_base64:'iVBORw0KGgo=',alt:'Broken'},url:{media_type:'image/png',data_base64:'https://example.com/tracker.png',alt:'URL'},svg:{media_type:'image/svg+xml',data_base64:'PHN2Zz4=',alt:'SVG'}})){
          const block={block_id:id,content_type:'product',view:'list',action_ids:[]};
          host.append(renderBlock(block,{source:{resource_id:id},content:{title:'Fixture '+id,description:'Details remain available',price:{amount_minor:250,currency:'EUR'},availability:'in_stock',image}},{actions:[]}));
        }
      });
      await page.waitForFunction(()=>document.querySelectorAll('#photo-errors img').length===0);
      assert.equal(await page.locator('#photo-errors').getByText('Photo unavailable',{exact:true}).count(),3);
      assert.equal(await page.locator('#photo-errors').getByText('Details remain available',{exact:true}).count(),3);
      await page.locator('#photo-errors').evaluate(n=>n.remove());
    });
    await check('Photos: revoking source access clears both personal and catalog images',async()=>{
      await call(owner,ownerSession,'DELETE',grant);
      await page.waitForFunction(()=>document.querySelectorAll('main img').length===0,null,{timeout:15000});
      await page.getByRole('heading',{name:'Source unavailable',exact:true}).waitFor();
      assert.equal(await page.getByRole('heading',{name:'Hand soap',exact:true}).count(),0);
      assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
    });
  }finally{await owner.close();await reader.close();await outsider.close();}
}
