import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import {studioAcceptance} from './studio-acceptance.mjs';
import {favoritesAcceptance} from './favorites-acceptance.mjs';
import {spaceAcceptance} from './space-acceptance.mjs';
let input=''; for await (const part of process.stdin) input+=part;
const config=JSON.parse(input), checks=[];
const browser=await chromium.launch({channel:process.env.MARKETOB_BROWSER_CHANNEL || undefined, headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}}), page=await context.newPage();
const errors=[]; page.on('pageerror',error=>errors.push(error.message));
const check=async(name,fn)=>{await fn(); checks.push(name); console.log('PASS: '+name);};
const waitText=async(text)=>page.getByText(text,{exact:true}).first().waitFor();
const go=async route=>{await page.goto(config.origin+'/app/#/'+route);};
const save=async name=>{
  if(name!=='failure')await page.locator('#sidebar').getByRole('link',{name:'＋ Open a channel',exact:true}).waitFor();
  await mkdir(config.output,{recursive:true}); await page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});
};
const overflow=async()=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
try {
  await check('Private channel does not leak anonymously',async()=>{
    await go('channel/'+config.channels.catalog.slug); await waitText('Channel unavailable');
    assert.equal(await page.getByText('Hand soap',{exact:true}).count(),0);
  });
  await check('Keyboard login opens My Space',async()=>{
    await go('login'); await page.getByLabel('Username',{exact:true}).fill(config.credentials.username);
    await page.getByLabel('Password',{exact:true}).fill(config.credentials.password); await page.getByLabel('Password',{exact:true}).press('Enter');
    await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
  });
  await check('Catalog renders actual bot data and confirmed request',async()=>{
    await go('channel/'+config.channels.catalog.slug); await page.locator('[data-block="soap"]').waitFor();
    assert.equal(await page.locator('[data-block="soap"]').getByRole('combobox').inputValue(),'list');
    const soap=page.locator('[data-block="soap"]');
    await soap.getByRole('button',{name:'Request purchase',exact:true}).click();
    await page.getByRole('dialog',{name:'Confirm purchase request'}).press('Escape');
    assert.equal(await page.getByRole('dialog').count(),0);
    await soap.getByRole('button',{name:'Request purchase',exact:true}).focus();await page.keyboard.press('Enter');
    await waitText('This sends a request to the bot. No money will be charged.');
    await page.getByRole('button',{name:'Send request',exact:true}).click();
    for(let i=0;i<15;i++){await soap.getByRole('button',{name:'Check status'}).click(); if(await soap.getByText('Confirmed',{exact:true}).count())break; await page.waitForTimeout(500);}
    await soap.getByText('Confirmed',{exact:true}).waitFor();
    const count=await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('marketob-request:')).length); assert.equal(count,1);
    await page.waitForFunction(()=>!document.querySelector('[data-block="soap"] button').disabled);
    await overflow(); await save('desktop-catalog');
  });
  await check('Demo supplier decline is shown',async()=>{
    const item=page.locator('[data-block="paper_towels"]'); await item.getByRole('button',{name:'Request purchase',exact:true}).click();
    await page.getByRole('button',{name:'Send request',exact:true}).click();
    for(let i=0;i<15;i++){await item.getByRole('button',{name:'Check status'}).click();if(await item.getByText('Declined',{exact:true}).count())break;await page.waitForTimeout(500);}
    await item.getByText('Declined',{exact:true}).waitFor();
    assert.equal(await page.locator('[data-block="milk"]').getByRole('button',{name:'Request purchase'}).isDisabled(),true);
  });
  await check('Reload recovers existing request by GET',async()=>{
    await page.reload(); const item=page.locator('[data-block="soap"]'); await item.getByRole('button',{name:'Check status'}).click();
    await item.getByText('Confirmed',{exact:true}).waitFor();
  });
  await check('Lost POST response recovers the same request after reload',async()=>{
    let acceptedID, replayID, postCount=0;
    const pattern='**/v1/channels/'+config.channels.catalog.channel_id+'/actions';
    await page.route(pattern,async route=>{
      const response=await route.fetch();const body=await response.json();postCount++;
      if(postCount===1){acceptedID=body.action_request_id;await route.abort();}
      else {replayID=body.action_request_id;await route.fulfill({response});}
    });
    const item=page.locator('[data-block="rice"]');await item.getByRole('button',{name:'Request purchase',exact:true}).click();
    await page.getByRole('button',{name:'Send request',exact:true}).click();
    await item.getByText('Awaiting confirmation',{exact:true}).waitFor();
    await item.getByText('Connection unavailable. Reconnect and try again.',{exact:true}).waitFor();
    assert.ok(acceptedID);await page.reload();await item.getByRole('button',{name:'Check status'}).click();
    await page.waitForFunction(()=>!document.querySelector('[data-block="rice"] button').disabled);
    assert.equal(replayID,acceptedID);assert.equal(postCount,2);await page.unroute(pattern);
  });
  await check('Expanded RSS and accessible chart from second bot',async()=>{
    await go('channel/'+config.channels.news.slug); await page.locator('[data-block="news_1"]').waitFor();
    assert.equal(await page.locator('[data-block="news_1"]').getByRole('combobox').inputValue(),'article');
    await page.getByRole('img').waitFor();
    await page.locator('[data-block="feed_activity"]').getByRole('combobox').selectOption('table');
    await page.getByRole('table').waitFor(); await save('desktop-news');
  });
  await check('360px viewport has no horizontal overflow',async()=>{
    await page.setViewportSize({width:360,height:800}); await overflow(); await save('phone-news');
    await go('channel/'+config.channels.catalog.slug); await page.locator('[data-block="soap"]').waitFor();await overflow();await save('phone-catalog');
  });
  await check('Offline clears private content and recovery revalidates access',async()=>{
    await context.setOffline(true); await waitText('You are offline');assert.equal(await page.locator('[data-block]').count(),0);
    await context.setOffline(false);await page.locator('[data-block="soap"]').waitFor();
  });
  await check('Plain text and unsafe links never execute',async()=>{
    const result=await page.evaluate(async()=>{
      const {plainText,safeURL}=await import('/app/dom.js');const node=plainText('<img src=x onerror=alert(1)> javascript:alert(1) https://example.com/news');
      document.querySelector('#main').append(node);
      return {images:node.querySelectorAll('img').length,links:node.querySelectorAll('a').length,
        bad:safeURL('javascript:alert(1)'),creds:safeURL('https://user:pass@example.com')};
    });assert.deepEqual(result,{images:0,links:1,bad:null,creds:null});
  });
  await check('Server outage clears stale data and offers retry',async()=>{
    const pattern='**/v1/channels/'+config.channels.catalog.slug;
    await page.route(pattern,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({code:'unavailable',message:'Service temporarily unavailable.'})}));
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await waitText('Service temporarily unavailable.');
    assert.equal(await page.locator('[data-block]').count(),0);await page.unroute(pattern);
    await page.getByRole('button',{name:'Try again',exact:true}).click();await page.locator('[data-block="soap"]').waitFor();
  });
  await check('Revoked source clears content instead of showing stale blocks',async()=>{
    const pattern='**/v1/channels/'+config.channels.catalog.slug;
    await page.route(pattern,route=>route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({code:'source_unavailable',message:'Unavailable.'})}));
    await page.getByRole('button',{name:'Refresh',exact:true}).click();await waitText('Channel unavailable');
    assert.equal(await page.locator('[data-block]').count(),0);await page.unroute(pattern);
  });
  await check('Loading and empty response states are explicit',async()=>{
    const pattern='**/v1/channels/'+config.channels.catalog.slug;
    let release;const held=new Promise(resolve=>{release=resolve;});
    await page.route(pattern,async route=>{
      const response=await route.fetch(),snapshot=await response.json();snapshot.channel.layout.blocks=[];snapshot.records=[];
      await held;await route.fulfill({response,json:snapshot});
    });
    await page.getByRole('button',{name:'Check access',exact:true}).click();await waitText('Loading…');
    release();await waitText('No published blocks yet');await page.unroute(pattern);
  });
  await check('Sign out clears request references and private UI',async()=>{
    await page.getByRole('button',{name:'Sign out'}).click();await page.getByLabel('Username',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>Object.keys(sessionStorage).filter(k=>k.startsWith('marketob-request:')).length),0);
    assert.equal(await page.locator('[data-block]').count(),0);
  });
  assert.deepEqual(errors,[]);
  await studioAcceptance(browser,config,check);
  await favoritesAcceptance(browser,config,check);
  await spaceAcceptance(browser,config,check);
  await writeFile(path.join(config.output,'browser-results.json'),JSON.stringify({checks,browser:browser.version(),viewport:[1440,1000,360,800],page_errors:errors},null,2)+'\n');
} catch(error) {await save('failure');throw error;} finally {await browser.close();}
