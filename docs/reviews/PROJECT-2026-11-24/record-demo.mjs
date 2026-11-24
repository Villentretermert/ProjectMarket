// Tutorial pacing and captions only: all application data comes from the real API.
import {chromium} from '../../../apps/client/node_modules/playwright/index.mjs';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';

let input='';for await(const part of process.stdin)input+=part;
const config=JSON.parse(input),checks=[],chapters=[],errors=[];
const browser=await chromium.launch({channel:process.env.MARKETOB_BROWSER_CHANNEL||undefined,headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:config.output,size:{width:1440,height:1000}}});
let page,video,started;
const pause=async(seconds=3)=>page.waitForTimeout(seconds*1000);
const caption=async(text)=>{
  chapters.push({seconds:Math.round((Date.now()-started)/1000),text});
  await page.evaluate(text=>{document.querySelector('#video-guide-text').textContent=text;},text);
  console.log('STEP: '+chapters.length);
};
const click=async locator=>{
  await locator.scrollIntoViewIfNeeded();await locator.hover();
  // Highlight the actual control before clicking, without changing its behavior.
  await locator.evaluate(node=>node.style.outline='3px solid #f2b544');
  await pause(0.8);await locator.evaluate(node=>node.style.outline='');await locator.click();
};
const snap=async(name)=>{await page.locator('#video-guide').evaluate(n=>n.style.visibility='hidden');await page.screenshot({path:path.join(config.output,name+'.png')});await page.locator('#video-guide').evaluate(n=>n.style.visibility='');};
const saved=async()=>page.locator('.space [role="status"]').filter({hasText:/^Saved · v/}).waitFor();
const add=async(slug,block)=>{
  await page.getByLabel('Source channel',{exact:true}).selectOption(slug);
  await pause(1);await click(page.locator('[data-catalog-block="'+block+'"]').getByRole('button',{name:'Add to My Space',exact:true}));await saved();
};
try{
  const login=await context.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.credentials});
  assert.equal(login.status(),200);
  // The separate tutorial overlay is not part of the product UI.
  await context.addInitScript(()=>{
    document.addEventListener('DOMContentLoaded',()=>{
      const guide=document.createElement('aside');guide.id='video-guide';
      guide.style.cssText='position:fixed;bottom:20px;left:310px;right:24px;z-index:99999;background:#142333;color:white;padding:16px 24px;border-radius:12px;box-shadow:0 4px 24px #0003;pointer-events:none;font:20px/1.4 system-ui';
      const label=document.createElement('div');label.textContent='VIDEO GUIDE · DEMO DATA';label.style.cssText='font-size:11px;letter-spacing:2px;color:#a9d0f5;margin-bottom:6px';
      const text=document.createElement('div');text.id='video-guide-text';text.textContent='MarkeTOB · My Space';
      guide.append(label,text);document.body.append(guide);
    });
  });
  page=await context.newPage();video=page.video();started=Date.now();
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(config.origin+'/app/#/space');
  await page.getByRole('heading',{name:'My Space',exact:true}).waitFor();
  await caption('Один интерфейс для разных ботов. Соберём товары и новости в My Space.');await pause(5);await snap('01-overview');

  await click(page.getByRole('link',{name:'＋ Open a channel',exact:true}));
  await page.getByLabel('Channel link or slug',{exact:true}).fill(config.origin+'/app/#/channel/'+config.channels.catalog.slug);
  await caption('1. Открываем ссылку на каталог. Доступ к закрытому каналу выдал его владелец.');await pause(3);
  await click(page.getByRole('button',{name:'Open channel',exact:true}));
  await page.getByRole('heading',{name:'Hand soap',exact:true}).waitFor();
  await click(page.getByRole('button',{name:'Add to favorites',exact:true}));
  await page.getByRole('button',{name:'Remove from favorites',exact:true}).waitFor();
  await caption('2. Добавляем канал в избранное — он появляется слева, как контакт.');await pause(4);
  checks.push('B2C reader opens a granted catalog and saves it to favorites');await snap('02-catalog');
  await Promise.all([page.waitForResponse(r=>r.url().includes('/v1/preferences/')&&r.request().method()==='GET'),click(page.getByRole('button',{name:'Events',exact:true}))]);await pause(1);await page.getByLabel('My request status',{exact:true}).check();await caption('Выбираем события: ответы на мои заявки. Уведомления работают в открытом приложении.');await pause(5);await snap('12-events');await click(page.getByRole('button',{name:'Save',exact:true}));

  await click(page.getByRole('link',{name:'＋ Open a channel',exact:true}));
  await page.getByLabel('Channel link or slug',{exact:true}).fill(config.origin+'/app/#/channel/'+config.channels.news.slug);
  await click(page.getByRole('button',{name:'Open channel',exact:true}));
  await page.locator('[data-block="news_1"]').waitFor();
  await click(page.getByRole('button',{name:'Add to favorites',exact:true}));
  await page.getByRole('button',{name:'Remove from favorites',exact:true}).waitFor();
  await caption('3. Так же сохраняем новости. Здесь тестовая RSS-лента, без внешнего сервиса.');await pause(4);
  checks.push('Second Python bot supplies news; reader saves the news channel');await snap('03-news');
  await page.locator('[data-block="feed_activity"]').scrollIntoViewIfNeeded();await caption('Числовые данные бот передаёт как график. Здесь показана активность тестовой ленты.');await pause(5);await snap('04-chart');

  await click(page.getByRole('link',{name:'My Space',exact:true}));
  await click(page.getByRole('button',{name:'Create My Space',exact:true}));
  await page.getByLabel('New page title',{exact:true}).fill('My daily space');
  await caption('4. Создаём личную страницу My daily space.');await pause(2);
  await click(page.getByRole('button',{name:'Create page',exact:true}));await saved();
  await page.getByLabel('Source channel',{exact:true}).selectOption(config.channels.catalog.slug);await pause(2);await snap('06-block-catalog');
  await add(config.channels.catalog.slug,'soap');
  await caption('5. Выбираем товар Hand soap из каталога и добавляем его блок.');await pause(4);
  await add(config.channels.news.slug,'news_1');
  await page.locator('[data-space-block]').first().evaluate(n=>n.scrollIntoView({block:'start'}));
  await caption('6. Добавляем новость из другого канала. Данные остаются связаны с ботами.');await pause(4);await snap('07-space-editor');
  assert.equal(await page.locator('[data-space-block]').count(),2);
  checks.push('My Space combines a product and a news block from different channels');

  await page.getByLabel('View for Hand soap',{exact:true}).scrollIntoViewIfNeeded();
  await page.getByLabel('View for Hand soap',{exact:true}).selectOption('card');await saved();
  await caption('7. Меняем вид товара на карточку. Изменения сохраняются автоматически.');await pause(4);
  await click(page.locator('[data-space-block]').nth(1).getByRole('button',{name:'Move up',exact:true}));await saved();
  await caption('8. Меняем порядок блоков. Undo возвращает предыдущее расположение.');await pause(3);
  await click(page.getByRole('button',{name:'Undo',exact:true}));await saved();
  assert.equal(await page.locator('[data-space-block]').first().getByRole('heading',{name:'Hand soap',exact:true}).count(),1);
  checks.push('Card visualization, autosave, reorder and Undo work');
  await click(page.getByRole('button',{name:'Preview',exact:true}));
  await page.getByRole('button',{name:'Edit layout',exact:true}).waitFor();
  await page.evaluate(()=>window.scrollTo(0,320));
  await caption('9. Preview показывает собранную страницу: товар и новость в одном месте.');await pause(5);await snap('08-space-preview');
  await page.locator('#video-guide').evaluate(node=>node.style.visibility='hidden');
  await page.screenshot({path:path.join(config.output,'my-space.png')});
  await page.locator('#video-guide').evaluate(node=>node.style.visibility='');

  await click(page.getByRole('button',{name:'Request purchase',exact:true}));
  await page.getByText('This sends a request to the bot. No money will be charged.',{exact:true}).waitFor();
  await caption('10. Request purchase: одна единица товара. Перед отправкой есть подтверждение; деньги не списываются.');await pause(6);await snap('09-purchase-confirmation');
  await click(page.getByRole('button',{name:'Send request',exact:true}));
  await caption('11. Заявка уходит исходному боту. Check status проверяет эту же заявку.');await pause(3);
  await click(page.getByRole('button',{name:'Check status',exact:true}));
  await page.getByText('Confirmed',{exact:true}).waitFor({timeout:20000});
  checks.push('Request purchase displays confirmation and receives a real Python bot confirmation');
  await caption('Готово: Confirmed. Бот подтвердил тестовую заявку — без оплаты.');await pause(7);
  await page.locator('#video-guide').evaluate(node=>node.style.visibility='hidden');
  await page.screenshot({path:path.join(config.output,'confirmed.png')});

  await page.locator('#video-guide').evaluate(node=>node.style.visibility='');
  await snap('10-confirmed');
  await click(page.getByRole('button',{name:'Share',exact:true}));
  await click(page.getByRole('button',{name:'Create link',exact:true}));
  await page.getByLabel('Template link',{exact:true}).waitFor();
  await caption('Обмен личной страницей: ссылка передаёт оформление и ссылки на источники. Доступ получателя проверяется отдельно.');await pause(7);await snap('11-share');
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  await page.goto(config.origin+'/app/#/privacy');
  await page.getByRole('heading',{name:'Data & privacy',exact:true}).waitFor();
  await caption('Data & privacy: экспорт личных настроек и удаление аккаунта с подтверждением. Секреты ботов в экспорт не входят.');await pause(7);await snap('13-privacy');
  const mobile=await browser.newContext({viewport:{width:390,height:844},storageState:await context.storageState()});
  const mobilePage=await mobile.newPage();await mobilePage.goto(config.origin+'/app/#/space');await mobilePage.getByRole('heading',{name:'My Space',exact:true}).waitFor();await mobilePage.waitForTimeout(1500);await mobilePage.screenshot({path:path.join(config.output,'14-mobile-web.png')});await mobile.close();
  await caption('Теперь посмотрим Studio со стороны B2B-владельца. Это отдельный демонстрационный аккаунт.');await pause(5);
  await context.clearCookies();
  const ownerLogin=await context.request.post(config.origin+'/v1/auth/login',{headers:{Origin:config.origin},data:config.owner_credentials});assert.equal(ownerLogin.status(),200);
  await page.goto(config.origin+'/app/#/studio');await page.getByRole('heading',{name:'Studio',exact:true}).waitFor();
  await caption('Studio объединяет рабочее пространство, ботов и страницы. Боты подключаются через общий HTTP API.');await pause(7);await snap('15-studio');
  const ws=await context.request.get(config.origin+'/v1/workspaces');const org=(await ws.json()).items[0].org_id;
  await page.goto(config.origin+'/app/#/studio/'+org+'/channel/'+config.channels.catalog.channel_id);
  await page.getByRole('heading',{name:'Page editor',exact:true}).waitFor();
  await caption('Редактор страницы: тип визуализации, доступ, блоки и действия. Черновик и опубликованная версия хранятся отдельно.');await pause(8);await snap('16-studio-editor');
  await page.goto(config.origin+'/app/#/studio/'+org+'/team');await page.getByRole('heading',{name:'Workspace team',exact:true}).waitFor();
  await caption('Командные роли: Owner управляет командой, Admin — ботами и доступом, Editor — оформлением и публикацией.');await pause(7);await snap('17-team');
  await page.goto(config.origin+'/app/#/studio/'+org+'/bot/'+config.channels.catalog.bot_id);
  await page.getByRole('heading',{name:'Everyday goods · demo',exact:true}).waitFor();
  await caption('У каждого бота собственные ключи, сроки действия и права. Секреты показываются только при выдаче.');await pause(7);await snap('18-bot-keys');
  checks.push('Sharing, Events, privacy, mobile Web and B2B Studio screens recorded without displaying secrets');
  await caption('Локальный Web-пилот работает. Android, домашний виджет, облако и Google-вход остаются следующими этапами.');await pause(8);
  assert.deepEqual(errors,[]);
  await context.close();
  await video.saveAs(path.join(config.output,'marketob-project-demo.webm'));await video.delete();
  await writeFile(path.join(config.output,'result.json'),JSON.stringify({checks,page_errors:errors,browser:browser.version(),viewport:[1440,1000],chapters,approximate_seconds:Math.round((Date.now()-started)/1000),caption_overlay:true},null,2)+'\n');
}catch(error){
  if(page&&!page.isClosed())await page.screenshot({path:path.join(config.output,'failure.png')});
  throw error;
}finally{await browser.close();}
