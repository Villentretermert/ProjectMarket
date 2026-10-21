import { Capacitor, registerPlugin } from '@capacitor/core';

const widget = registerPlugin('NewsWidget');
const native = Capacitor.isNativePlatform();
const content = document.querySelector('#content');
const status = document.querySelector('#status');
const key = 'marketob.pm002.web.preferences.v1';
const values = [42, 55, 51, 68, 72, 65, 84];
const news = [
  {title: 'Your morning briefing, in one place', body: 'A short update from your news bot. This is a synthetic fixture, not a real news report.'},
  {title: 'New collection is ready to explore', body: 'A second sample story demonstrates a compact news feed and a link back from the Android widget.'},
];
let saved = new Set();
let chart = 'bars';
try {
  const raw = localStorage.getItem(key);
  const prefs = raw && raw.length <= 4096 ? JSON.parse(raw) : null;
  if (prefs?.version === 1) {
    saved = new Set(Array.isArray(prefs.favorites) ? prefs.favorites.filter(x => ['shop', 'news'].includes(x)) : []);
    chart = prefs.chart === 'values' ? 'values' : 'bars';
  }
} catch { status.textContent = 'Preferences unavailable; this session remains usable.'; }

function persist() {
  try { localStorage.setItem(key, JSON.stringify({version: 1, favorites: [...saved], chart})); }
  catch { status.textContent = 'Preferences could not be saved.'; }
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, handler, className) {
  const node = element('button', text, className);
  node.addEventListener('click', handler);
  return node;
}
function chartContent() {
  if (chart === 'values') {
    const table = element('table');
    table.append(element('caption', 'Catalog views · sample series'));
    const heading = element('tr');
    for (const title of ['Day', 'Views']) { const th = element('th', title); th.scope = 'col'; heading.append(th); }
    const head = element('thead'); head.append(heading); table.append(head);
    const body = element('tbody');
    values.forEach((v,i) => { const row = element('tr'); row.append(element('td', String(i + 1)), element('td', String(v))); body.append(row); });
    table.append(body); return table;
  }
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 350 180'); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Catalog views, days 1 to 7: 42, 55, 51, 68, 72, 65, 84.');
  values.forEach((value, index) => {
    const bar = document.createElementNS(svg.namespaceURI, 'rect');
    for (const [k,v] of Object.entries({x: index*50+12,y: 155-value*1.4,width: 26,height: value*1.4,rx: 5,fill: '#2468bc'})) bar.setAttribute(k,String(v));
    const label = document.createElementNS(svg.namespaceURI,'text');
    label.setAttribute('x', String(index*50+25)); label.setAttribute('y', '175'); label.setAttribute('text-anchor','middle');label.setAttribute('font-size','12');label.textContent=String(index+1);
    svg.append(bar,label);
  });
  return svg;
}
function render() {
  const path = location.hash.slice(1) || '/channels/shop';
  const channel = path === '/channels/shop' ? 'shop' : path === '/channels/news' ? 'news' : null;
  content.replaceChildren();
  document.querySelectorAll('nav a').forEach(a => a.dataset.channel === channel ? a.setAttribute('aria-current','page') : a.removeAttribute('aria-current'));
  if (!channel) { content.append(element('h1', 'Channel unavailable')); return; }
  const heading = element('div', null, 'channel-heading');
  const saveButton = button(saved.has(channel) ? 'Saved' : 'Save channel', () => { saved.has(channel) ? saved.delete(channel) : saved.add(channel); persist(); render(); document.querySelector('#save-channel').focus(); });
  saveButton.id = 'save-channel'; saveButton.setAttribute('aria-pressed', String(saved.has(channel)));
  heading.append(element('h1', channel === 'shop' ? 'Northstar Shop' : 'Daily Brief'), saveButton);
  content.append(heading, element('p', 'Public channel · sample data · source time is illustrative', 'muted'));
  if (channel === 'shop') {
    const cards = element('div', null, 'cards');
    const product = element('article', null, 'card');
    const art=element('div', '▤', 'product-icon'); art.setAttribute('aria-hidden','true');
    product.append(art, element('h2','Daily notebook'), element('p','A5 notebook with dotted pages.','muted'),element('p','EUR 18.00','price'),element('p','In stock · Demo item','stock'),button('Send request',()=>status.textContent='Demo request: Pending. No order was submitted and no payment was taken.','primary'));
    const graph = element('section', null, 'card');
    const toggle = button(chart === 'bars' ? 'Show values' : 'Show chart', () => {chart = chart === 'bars' ? 'values' : 'bars';persist();render();document.querySelector('#chart-toggle').focus();}); toggle.id='chart-toggle';
    graph.append(element('h2','Catalog views'),element('p','A week at a glance · sample series','muted'),chartContent(),element('p','Day 1–7 · Views','muted'),toggle);
    cards.append(product,graph);content.append(cards);
  } else {
    const feed = element('div',null,'news-list');
    news.forEach((item,index)=>{const card=element('article',null,'card');card.append(element('p',`DEMO STORY ${index+1}`,'muted'),element('h2',item.title),element('p',item.body));feed.append(card);});
    content.append(feed);
    const panel=element('section',null,'card widget');
    panel.append(element('h2','News on your home screen'),element('p',native ? 'Send this public sample feed to the native Android widget, then add it to your launcher.' : 'Native Android widget code is prepared but device testing is deferred. This panel is not a widget.'));
    const publish=button('Update demo widget',async()=>{try{const result=await widget.publishDemoNews({headlines:news.map(x=>x.title)});status.textContent=`Updated public demo cache for ${result.widgetCount} installed widgets.`;}catch{status.textContent='Native widget update failed.';}});
    const pin=button('Add home widget',async()=>{try{const result=await widget.requestPin();status.textContent=result.supported ? 'Confirm the widget in your launcher.' : 'Add MarkeTOB from your launcher widget picker.';}catch{status.textContent='Use the launcher widget picker to add MarkeTOB.';}});
    const clear=button('Clear widget cache',async()=>{try{await widget.clear();status.textContent='Public demo widget cache cleared.';}catch{status.textContent='Could not clear the native widget cache.';}});
    for(const b of [publish,pin,clear]){b.disabled=!native;panel.append(b);}content.append(panel);
  }
}
document.querySelector('#profile').addEventListener('click',()=>{document.querySelector('#identity').textContent='Previewing as Bob · local demo profile';status.textContent='Demo profile selected. Real local accounts and access checks are planned in PM-006.';});
// Keep the keyboard skip link out of the channel hash router.
document.querySelector('.skip').addEventListener('click',event=>{event.preventDefault();content.focus();});
document.querySelector('#runtime').textContent=native ? 'Android bundled Web UI' : 'Browser Web UI';
function connectivity(){document.querySelector('#connectivity').textContent=navigator.onLine ? 'Demo data bundled locally' : 'Offline · bundled demo data';}
window.addEventListener('online',connectivity);window.addEventListener('offline',connectivity);window.addEventListener('hashchange',render);
connectivity();render();
if(native){
  const open = ({channel}) => {if(['news','shop'].includes(channel))location.hash=`/channels/${channel}`;};
  widget.addListener('openChannel',open);
  widget.getLaunchChannel().then(open).catch(()=>{});
} else if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(()=>{status.textContent='Offline shell cache unavailable; online preview still works.';});
}
