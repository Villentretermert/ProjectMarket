import assert from 'node:assert/strict';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

export async function favoritesAcceptance(browser,config,check){
  const owner=await browser.newContext(), first=await browser.newContext({viewport:{width:1440,height:1000}}),second=await browser.newContext();
  const page=await first.newPage(),other=await second.newPage(),username='reader_'+randomUUID().slice(0,8);
  const channels=config.channels;let userID,csrf,newsDraft;
  const login=await owner.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  csrf=(await login.json()).csrf_token;
  const manage=async(method,route,data)=>{
    const r=await owner.request.fetch(config.origin+'/v1'+route,{method,headers:{Origin:config.origin,'X-CSRF-Token':csrf},data});
    assert.ok(r.ok(),'Owner setup '+r.status());return r.status()===204?null:r.json();
  };
  const publishNews=async visibility=>{
    const id=channels.news.channel_id;newsDraft=await manage('GET','/owner/channels/'+id);
    const v=newsDraft.layout.template_version;
    await manage('PUT','/owner/channels/'+id,{title:newsDraft.title,visibility,layout:{...newsDraft.layout,template_version:v+1},actions:newsDraft.actions,expected_template_version:v});
    await manage('POST','/owner/channels/'+id+'/publish',{expected_template_version:v+1});
  };
  const go=async(p,route)=>{const url=config.origin+'/app/#/'+route;if(p.url()===url)await p.reload();else await p.goto(url);};
  const favoriteRows=p=>p.locator('#main [data-favorite]');
  const shot=async name=>{await page.locator('#sidebar').getByRole('link',{name:'＋ Open a channel',exact:true}).waitFor();await page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});};
  try{
    await check('Favorites: public preview and sign-up return to original channel',async()=>{
      await publishNews('public');await go(page,'channel/'+channels.news.slug);
      await page.locator('[data-block="news_1"]').waitFor();await page.getByRole('link',{name:'Sign in to save',exact:true}).click();
      await page.getByRole('link',{name:'New here? Create an account',exact:true}).click();
      await page.getByLabel('Display name',{exact:true}).fill('Sam · Reader');await page.getByLabel('Username',{exact:true}).fill(username);
      await page.getByLabel('Password',{exact:true}).fill(config.credentials.password);await page.getByRole('button',{name:'Create account',exact:true}).click();
      await page.locator('[data-block="news_1"]').waitFor();assert.ok(page.url().endsWith('/channel/'+channels.news.slug));
      userID=(await (await first.request.get(config.origin+'/v1/auth/session')).json()).user.user_id;
      await page.getByRole('button',{name:'Add to favorites',exact:true}).click();await page.getByRole('button',{name:'Remove from favorites',exact:true}).waitFor();
    });
    await check('Favorites: manual order, search and second account session synchronization',async()=>{
      await manage('PUT','/owner/channels/'+channels.catalog.channel_id+'/grants/'+userID,{});
      await go(page,'channel/'+channels.catalog.slug);await page.getByRole('button',{name:'Add to favorites',exact:true}).click();await page.getByRole('button',{name:'Remove from favorites',exact:true}).waitFor();
      await go(page,'channels');await favoriteRows(page).nth(1).getByRole('button',{name:'Move up',exact:true}).click();
      await page.waitForFunction(id=>document.querySelector('[data-favorite]')?.dataset.favorite===id,channels.catalog.channel_id);
      await page.getByLabel('Search favorites',{exact:true}).fill('Everyday');assert.equal(await favoriteRows(page).count(),1);
      await page.getByLabel('Search favorites',{exact:true}).fill('no-match');await page.getByText('No favorites match your search.',{exact:true}).waitFor();
      await page.getByLabel('Search favorites',{exact:true}).fill('');await shot('favorites-desktop');
      await go(other,'login');await other.getByLabel('Username',{exact:true}).fill(username);await other.getByLabel('Password',{exact:true}).fill(config.credentials.password);await other.getByRole('button',{name:'Sign in',exact:true}).click();await other.getByRole('heading',{name:'My Space',exact:true}).waitFor();
      await go(other,'channels');await favoriteRows(other).nth(1).waitFor();
      assert.deepEqual(await favoriteRows(other).evaluateAll(rows=>rows.map(r=>r.dataset.favorite)),[channels.catalog.channel_id,channels.news.channel_id]);
      await page.setViewportSize({width:360,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await shot('favorites-phone');
    });
    await check('Favorites: new marker is cleared only after reading the published revision',async()=>{
      await publishNews('public');await go(page,'channels');const news=page.locator('[data-favorite="'+channels.news.channel_id+'"]');await news.getByText('New',{exact:true}).waitFor();
      await news.getByRole('link').click();await page.locator('[data-block="news_1"]').waitFor();await page.locator('#sidebar').getByRole('link',{name:'＋ Open a channel',exact:true}).waitFor();
      await go(page,'channels');await page.locator('[data-favorite="'+channels.news.channel_id+'"]').waitFor();
      assert.equal(await page.locator('[data-favorite="'+channels.news.channel_id+'"]').getByText('New',{exact:true}).count(),0);
    });
    await check('Favorites: real revocation removes titles and content from both clients',async()=>{
      await go(other,'channel/'+channels.news.slug);await other.locator('[data-block="news_1"]').waitFor();
      await publishNews('selected');await other.getByRole('button',{name:'Refresh',exact:true}).click();await other.getByRole('heading',{name:'Channel unavailable',exact:true}).waitFor();
      assert.equal(await other.locator('[data-block]').count(),0);
      await go(page,'channels');await page.locator('[data-favorite="'+channels.news.channel_id+'"]').getByText('Channel unavailable',{exact:true}).waitFor();
      assert.equal(await page.getByText(newsDraft.title,{exact:true}).count(),0);await shot('favorites-unavailable');
      const state=await page.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}));assert.ok(!state.includes(newsDraft.title));
    });
    await check('Favorites: removal does not delete publisher channel',async()=>{
      await page.locator('[data-favorite="'+channels.catalog.channel_id+'"]').getByRole('button',{name:'Remove',exact:true}).click();
      await page.locator('[data-favorite="'+channels.catalog.channel_id+'"]').waitFor({state:'detached'});
      await go(page,'channel/'+channels.catalog.slug);await page.locator('[data-block="soap"]').waitFor();await page.getByRole('button',{name:'Add to favorites',exact:true}).waitFor();
    });
  }catch(error){await shot('favorites-failure');throw error;}
  finally{await owner.close();await first.close();await second.close();}
}
