// PM-003 interaction model. Fixtures and simulated results never call a backend.
const main = document.querySelector('#main');
const sidebar = document.querySelector('#sidebar');
const toast = document.querySelector('#toast');
const channels = {
  shop: {title:'Northstar Shop',subtitle:'Catalog · 09:42 UTC',avatar:'N',tone:'',access:'Public'},
  news: {title:'Daily Brief',subtitle:'News · 09:40 UTC',avatar:'D',tone:'green',access:'Public'},
  private: {title:'Team Insights',subtitle:'Selected members only',avatar:'T',tone:'violet',access:'Private'},
};
const state = {saved:new Set(['news']),condition:'normal',chart:'bars',request:null,blocks:['news','chart'],theme:'blue',density:'comfortable',shared:null,importPreview:false,friend:false,bot:false,key:false,data:false,published:false,pageTitle:'Northstar Shop',visibility:'public',widget:'news'};
const escape = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const message = text => {toast.textContent=text;};
const route = () => location.hash.replace(/^#\/?/,'') || 'channels';
const link = (id,small=false) => `<a class="channel-link" href="#/channels/${id}" ${route()===`channels/${id}`?'aria-current="page"':''}><span class="avatar ${channels[id].tone}" aria-hidden="true">${channels[id].avatar}</span><span><strong>${escape(channels[id].title)}</strong><span class="meta">${small?channels[id].subtitle:(state.saved.has(id)?'Saved · ':'')+channels[id].subtitle}</span></span></a>`;
const source = text => `<p class="source">${text} · Sample updated 21 Oct 2026, 09:42 UTC</p>`;
const back = '<a class="back" href="#/channels">← All channels</a>';
const button = (label,action,extra='') => `<button data-action="${action}" ${extra}>${label}</button>`;
function statusCard(title,body,symbol='○',action='Try again') {
  return `<section class="card state-card"><div class="state-symbol" aria-hidden="true">${symbol}</div><h1>${title}</h1><p class="subtle">${body}</p>${action?button(action,'retry','class="primary"'):''}</section>`;
}
function chart(view=state.chart) {
  const values=[42,55,51,68,72,65,84];
  if(view==='table') return `<table><caption>Catalog views · sample data</caption><thead><tr><th scope="col">Day</th><th scope="col">Views</th></tr></thead><tbody>${values.map((x,i)=>`<tr><td>${i+1}</td><td>${x}</td></tr>`).join('')}</tbody></table>`;
  return `<svg class="chart" viewBox="0 0 350 180" role="img" aria-label="Catalog views, day 1 to 7: 42, 55, 51, 68, 72, 65, 84">${values.map((x,i)=>`<rect x="${i*50+12}" y="${155-x*1.4}" width="26" height="${x*1.4}" rx="5"/><text x="${i*50+25}" y="175" text-anchor="middle">${i+1}</text>`).join('')}</svg>`;
}
function block(id,inSpace=false) {
  if(id==='product') return `<div class="product-art" aria-hidden="true">▤</div><h2>Daily notebook</h2><p class="subtle">A5 notebook with dotted pages. Room for your next idea.</p><p class="price">EUR 18.00</p><p class="available">In stock · Demo item</p>${!inSpace?button(state.request?'View request':'Send request',state.request?'view-request':'request',`class="primary" ${state.condition==='offline'&&!state.request?'disabled':''}`):''}${source('Northstar Shop · Catalog bot')}`;
  if(id==='chart') return `<span class="badge">THIS WEEK</span><h2>Catalog views</h2><p class="meta">Views by day · sample series</p>${chart()}${button(state.chart==='bars'?'Show as table':'Show as bars','chart')}${source('Northstar Shop · Catalog bot')}`;
  if(id==='private') return `<span class="badge private">PRIVATE SOURCE</span><h2>Team Insights</h2>${state.friend?'<p>Access required. Importing a layout does not grant access.</p>':'<p>Preview: this sample block is available to Bob.</p><p class="price">84 <small>weekly views</small></p>'}${state.friend?'<p class="meta">No private data or update time loaded.</p>':source('Team Insights · Analytics bot')}`;
  return `<p class="news-number">DAILY BRIEF · SAMPLE STORY</p><h2>A little less scrolling.<br>A little more perspective.</h2><p class="subtle">Your news bot brings a short, useful briefing into one place. This story is a demonstration, not a real report.</p>${source('Daily Brief · News bot')}`;
}
function requestPanel() {
  if(!state.request)return '';
  const descriptions={sent:'Your request is queued for the bot. No payment has been taken.',processing:'The bot received your request and is checking availability.',confirmed:'The demo bot confirmed the request. This is not a payment receipt.',failed:'The demo bot could not fulfil this request. No payment was taken.',unknown:'We could not confirm the latest status. Check this request before sending another.'};
  return `<section class="card full" id="request-panel" tabindex="-1"><h2>Request status</h2><ol class="status-flow">${['sent','processing','confirmed'].map(x=>`<li class="${x===state.request?'active':''}">${{sent:'Request sent',processing:'Processing',confirmed:'Confirmed'}[x]}</li>`).join('')}</ol><p role="status">${descriptions[state.request]}</p><p class="meta">Demo request MK-001 · This panel simulates bot responses.</p><label for="request-status">Preview bot response</label><select id="request-status">${['sent','processing','confirmed','failed','unknown'].map(x=>`<option value="${x}" ${state.request===x?'selected':''}>${x[0].toUpperCase()+x.slice(1)}</option>`).join('')}</select></section>`;
}
function channelScreen(id) {
  if(!channels[id])return statusCard('Channel unavailable','This link does not match an available channel.','○','Back to channels');
  if((id==='private' || (id==='shop' && state.published && state.visibility==='private')) && state.friend)return back+statusCard('Access required','This channel is available to selected members. Ask the channel owner for access.','◇','Back to channels');
  const channel=channels[id];
  const ids=id==='shop'?['product','chart']:id==='private'?['private']:['news'];
  return `${back}<div class="heading"><div><span class="badge ${id==='private'?'private':''}">${channel.access.toUpperCase()} CHANNEL</span><h1>${escape(channel.title)}</h1><p class="meta">${id==='shop'?'Useful everyday essentials.':id==='news'?'A calm place for your daily updates.':'A shared view for your team.'}</p></div>${button(state.saved.has(id)?'Saved':'Save channel','save-channel',`id="save-channel" aria-pressed="${state.saved.has(id)}"`)}</div><div class="cards">${ids.map(x=>`<article class="card ${id==='news'?'full':''}">${block(x)}<div class="actions">${button('Add to My Space','add-block',`data-block="${x}"`)}</div></article>`).join('')}${id==='news'?`<article class="card full"><p class="news-number">SECOND SAMPLE STORY</p><h2>A new collection is ready to explore</h2><p class="subtle">A second headline demonstrates the compact news flow. Open it from your personal page or the future home widget.</p>${source('Daily Brief · News bot')}</article>`:''}${id==='shop'?requestPanel():''}</div>`;
}
function spaceScreen() {
  return `<div class="heading"><div><span class="badge">YOUR PERSONAL PAGE</span><h1>My Space</h1><p class="meta">Your favourite sources, arranged your way.</p></div><div class="actions">${button('Save layout','save-layout')}${button('Share layout','share','class="primary"')}</div></div><div class="card"><div class="form-grid"><div class="field"><label for="block-picker">Add a source block</label><select id="block-picker"><option value="news">Daily Brief · news</option><option value="product">Northstar Shop · product</option><option value="chart">Northstar Shop · chart</option><option value="private">Team Insights · private block</option></select></div><div class="field"><span class="meta">Each source keeps its own permissions.</span>${button('Add block','pick-block')}</div><div class="field"><label for="theme">Page theme</label><select id="theme"><option value="blue" ${state.theme==='blue'?'selected':''}>Blue</option><option value="ink" ${state.theme==='ink'?'selected':''}>Ink</option></select></div><div class="field"><label for="density">Spacing</label><select id="density"><option value="comfortable" ${state.density==='comfortable'?'selected':''}>Comfortable</option><option value="compact" ${state.density==='compact'?'selected':''}>Compact</option></select></div></div></div><hr class="section-rule"><div class="space ${state.theme} ${state.density} stack">${state.blocks.length?state.blocks.map((id,index)=>`<article class="card">${block(id,true)}<div class="block-tools">${button('Move up','move-up',`data-index="${index}" aria-label="Move ${id} block up" ${index===0?'disabled':''}`)}${button('Move down','move-down',`data-index="${index}" aria-label="Move ${id} block down" ${index===state.blocks.length-1?'disabled':''}`)}${button('Remove','remove',`data-index="${index}" aria-label="Remove ${id} block"`)}</div></article>`).join(''):statusCard('Make this space yours','Add a block from a channel to get started.','＋','')}</div>${sharePanel()}`;
}
function sharePanel() {
  return `<hr class="section-rule"><section class="card"><h2>Share a layout. Keep permissions separate.</h2><p class="meta">Only appearance and source references are included. Private data and account access are never part of the code.</p>${state.shared?`<label for="share-code">Demo layout code</label><input id="share-code" value="MT-DEMO-001" readonly><p class="meta">Works inside this design preview only; no public link has been published.</p>`:''}<form id="import-form" class="stack"><div class="field"><label for="import-code">Import a layout code</label><input id="import-code" name="code" placeholder="MT-DEMO-001" maxlength="100" required></div><button type="submit">Preview import</button><p id="import-error" class="form-message" role="alert"></p></form>${state.importPreview?`<div class="banner"><h3>Import preview · as Carol</h3><p>${state.shared.blocks.length} source blocks · ${escape(state.shared.theme)} theme. Private sources will show Access required.</p>${button('Import to My Space','import','class="primary"')}</div>`:''}</section>`;
}
function studioScreen() {
  return `<div class="heading"><div><span class="badge">B2B WORKSPACE</span><h1>Studio</h1><p class="meta">Connect your service. Shape its storefront.</p></div><span class="meta">Preview owner: Alice</span></div><div class="stack"><section class="card"><h2><span class="step">1</span>Connect a bot</h2>${!state.bot?`<p class="subtle">Bring an existing HTTP bot or a Telegram adapter. Your bot stays under your control.</p><form id="bot-form" class="form-grid"><div class="field"><label for="bot-name">Bot name</label><input id="bot-name" name="name" value="Northstar Catalog" maxlength="80" required></div><div class="field"><label for="bot-kind">Integration</label><select id="bot-kind"><option>HTTP service</option><option>Telegram adapter</option></select></div><div class="full"><button type="submit" class="primary">Create bot</button></div></form>`:`<span class="badge">${state.data?'DATA RECEIVED':'WAITING FOR FIRST UPDATE'}</span><p>${escape(state.bot)} · Individual bot key</p>${state.key?`<div class="banner"><h3>Save your registration credential</h3><p class="copy-code">DEMO-REGISTRATION-CREDENTIAL</p><p>This placeholder is shown once. It is not a working key.</p>${button('I saved it · hide','hide-key')}</div>`:'<p class="meta">Registration credential hidden. Real rotation and revocation will require confirmation.</p>'}<div class="actions">${button('Simulate first bot update','bot-data')}${button('Revoke demo bot','revoke-bot','class="danger"')}</div>`}</section><section class="card"><h2><span class="step">2</span>Configure your channel</h2><form id="publish-form" class="stack"><div class="form-grid"><div class="field"><label for="page-title">Channel name</label><input id="page-title" name="title" value="${escape(state.pageTitle)}" maxlength="80" required></div><div class="field"><label for="visibility">Who can view this channel?</label><select id="visibility" name="visibility"><option value="public" ${state.visibility==='public'?'selected':''}>Public</option><option value="private" ${state.visibility==='private'?'selected':''}>Selected members</option></select></div></div><p class="meta">Included blocks: product card and catalog views. Selected members preview: Bob only.</p><div class="actions">${button('Preview channel','studio-preview')}<button type="submit" class="primary" ${!state.data || state.condition==='offline'?'disabled':''}>Publish channel</button></div><p class="meta">Publish becomes available after the bot supplies valid sample data.</p></form></section>${state.published?`<section class="card"><span class="badge">PUBLISHED IN PREVIEW</span><h2>${escape(state.pageTitle)}</h2><p>${state.visibility==='private'?'Selected members':'Public'} · Version 1</p><a class="action-link" href="#/channels/shop">Open published channel preview</a><p class="meta">No live channel or external share link has been created.</p></section>`:''}</div>`;
}
function accountScreen() {
  return `<section class="card state-card"><span class="badge">LOCAL ACCOUNT</span><h1>Welcome to MarkeTOB</h1><p class="subtle">Sign in on this computer to save channels and build your space.</p><div class="stack"><div class="field"><label for="local-username">Username</label><input id="local-username" value="bob-demo" readonly autocomplete="off"></div><div class="field"><label for="local-password">Password</label><input id="local-password" type="password" value="demo-only" readonly autocomplete="off"></div>${button('Continue as Bob','demo-login','class="primary"')}</div><p class="meta">Design preview: sample credentials are read-only. Real local accounts are implemented separately; do not enter personal credentials here.</p></section>`;
}
function widgetScreen() {
  return `${back}<h1>News at a glance</h1><p class="subtle">Android home screen mockup · native testing is deferred.</p><div class="field"><label for="widget-source">News source</label><select id="widget-source"><option value="news" ${state.widget==='news'?'selected':''}>Daily Brief · public</option><option value="private" ${state.widget==='private'?'selected':''}>Team Insights · access required</option></select></div><div class="widget-frame"><div class="widget-card"><h2>${state.widget==='private'?'MarkeTOB · Access required':'MarkeTOB · Daily Brief'}</h2>${state.widget==='private'?'<p>Access required</p><p class="meta">Open MarkeTOB to choose an available source.</p>':'<p><strong>A little less scrolling.</strong></p><p>A new collection is ready to explore</p><p class="meta">Last updated 09:40 UTC · Sample cache</p>'}${button('Open news','open-news')}</div></div><p class="meta">The widget shows source time and stale state. Background refresh follows Android limits. Logout and expired private cache must remove private headlines.</p>`;
}
function render(focus=false) {
  const path=route();const selected=path.split('/')[1];
  document.body.classList.toggle('mobile-list',path==='channels' && state.condition==='normal');
  document.querySelector('.user-badge').innerHTML=path==='studio'?'A <span>Alice · Local demo</span>':state.friend?'C <span>Carol · Local demo</span>':'B <span>Bob · Local demo</span>';
  document.querySelectorAll('.app-header nav a').forEach(a=>a.hash===`#/${path.split('/')[0]}`?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));
  sidebar.innerHTML=`<h2>Channels</h2>${Object.keys(channels).map(id=>link(id)).join('')}<div class="sidebar-foot"><strong>Your bot feed, organised.</strong><p>Save channels and bring their blocks together in My Space.</p><span class="badge">${state.saved.size} SAVED</span></div>`;
  const conditions={loading:['Loading your channel','Fetching the latest available update…','◌',''],empty:['No updates yet','This channel is ready. Its bot has not supplied data yet.','○','Try again'],error:['Could not refresh','Your layout is safe. Try fetching the latest update again.','!','Try again'],revoked:['Access revoked','The owner removed your access. Private content has been cleared from this view.','◇','Back to channels'],missing:['Source unavailable','The source was removed or is temporarily unavailable. Your other blocks remain available.','○','Back to channels'],unsupported:['Update required','This layout uses a version this client cannot display.','↻','Back to channels']};
  if(conditions[state.condition])main.innerHTML=back+statusCard(...conditions[state.condition]);
  else {
    let html=path==='channels'?`<div class="heading"><div><span class="badge">WELCOME BACK</span><h1>A home for all your bots</h1><p class="subtle">Choose a channel to explore its products, news and insights.</p></div></div><div class="cards">${Object.keys(channels).map(id=>`<section class="card">${link(id,true)}<span class="badge ${id==='private'?'private':''}">${channels[id].access}</span><p class="meta">A sample storefront powered by an independent bot.</p></section>`).join('')}</div>`:path.startsWith('channels/')?channelScreen(selected):path==='space'?spaceScreen():path==='studio'?studioScreen():path==='widget'?widgetScreen():path==='account'?accountScreen():statusCard('Page unavailable','Choose a channel or open My Space.','○','Back to channels');
    main.innerHTML=(state.condition==='offline'?'<div class="banner" role="status"><strong>Offline · showing a saved update</strong><br>Last source update: 21 Oct 2026, 09:42 UTC. Sending requests is unavailable until you reconnect.</div>':'')+html;
  }
  if(focus)main.focus();
}
main.addEventListener('click',event=>{
  const target=event.target.closest('button[data-action]');if(!target)return;
  const action=target.dataset.action;const index=Number(target.dataset.index);const id=target.dataset.block;
  if(action==='retry'){state.condition='normal';document.querySelector('#preview-state').value='normal';location.hash='/channels';render(true);return;}
  if(action==='save-channel'){const channel=route().split('/')[1];state.saved.has(channel)?state.saved.delete(channel):state.saved.add(channel);render();document.querySelector('#save-channel')?.focus();message('Saved channels updated in this preview.');return;}
  if(action==='view-request'){document.querySelector('#request-panel')?.focus();return;}
  if(action==='request'){state.request='sent';message('Demo request sent. A bot result is still required.');}
  if(action==='chart')state.chart=state.chart==='bars'?'table':'bars';
  if(action==='add-block'||action==='pick-block'){const blockId=id||document.querySelector('#block-picker').value;if(!state.blocks.includes(blockId))state.blocks.push(blockId);message('Block added to My Space. Source permissions stay separate.');}
  if(action==='move-up'&&index>0)[state.blocks[index-1],state.blocks[index]]=[state.blocks[index],state.blocks[index-1]];
  if(action==='move-down'&&index<state.blocks.length-1)[state.blocks[index+1],state.blocks[index]]=[state.blocks[index],state.blocks[index+1]];
  if(action==='remove')state.blocks.splice(index,1);
  if(action==='save-layout')message('Layout saved in this preview session. No server changes were made.');
  if(action==='share'){state.shared={version:1,blocks:[...state.blocks],theme:state.theme,density:state.density};message('Demo code created. It contains layout settings and source references only.');}
  if(action==='import'&&state.shared){state.blocks=[...state.shared.blocks];state.theme=state.shared.theme;state.density=state.shared.density;state.friend=true;state.importPreview=false;message('Imported as Carol. Private sources still require access.');}
  if(action==='hide-key')state.key=false;
  if(action==='bot-data'){state.data=true;message('Sample data received. You can preview and publish the channel.');}
  if(action==='revoke-bot'){state.bot=false;state.key=false;state.data=false;state.published=false;message('Demo bot revoked. No real credential was changed.');}
  if(action==='studio-preview'){location.hash='/channels/shop';return;}
  if(action==='demo-login'){state.friend=false;location.hash='/channels';return;}
  if(action==='open-news'){location.hash='/channels/news';return;}
  render(true);
});
main.addEventListener('submit',event=>{
  event.preventDefault();const form=event.target;const data=new FormData(form);
  if(form.id==='bot-form'){state.bot=String(data.get('name')).trim();state.key=true;render(true);}
  if(form.id==='publish-form'&&state.data){state.pageTitle=String(data.get('title')).trim();state.visibility=data.get('visibility');state.published=true;channels.shop.title=state.pageTitle;channels.shop.access=state.visibility==='public'?'Public':'Private';render(true);message('Channel version 1 published in this preview.');}
  if(form.id==='import-form'){
    if(!state.shared||String(data.get('code')).trim()!=='MT-DEMO-001'){document.querySelector('#import-error').textContent='Code not found. First create a demo code with Share layout.';return;}
    state.importPreview=true;render(true);
  }
});
main.addEventListener('change',event=>{
  if(event.target.id==='theme')state.theme=event.target.value;
  else if(event.target.id==='density')state.density=event.target.value;
  else if(event.target.id==='request-status')state.request=event.target.value;
  else if(event.target.id==='widget-source')state.widget=event.target.value;
  else return;
  const id=event.target.id;render();document.getElementById(id)?.focus();
});
document.querySelector('.skip').addEventListener('click',event=>{event.preventDefault();(getComputedStyle(main).display==='none'?sidebar:main).focus();});
document.querySelector('#preview-state').addEventListener('change',event=>{state.condition=event.target.value;render();});
document.querySelector('#widget-preview').addEventListener('click',()=>{state.condition='normal';document.querySelector('#preview-state').value='normal';location.hash='/widget';});
window.addEventListener('hashchange',()=>{message('');render(true);});
render();
