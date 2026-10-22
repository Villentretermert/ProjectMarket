import {api, all, session, setSession} from './api.js';
import {el, button, link, message, field, heading, errorBox, toast} from './dom.js';
import {renderSnapshot} from './render.js';
import {clearRequests} from './actions.js';

const main = document.querySelector('#main'), sidebar = document.querySelector('#sidebar');
let generation = 0;
export const routes = new Map();
export function navigate(path) { if (location.hash === '#' + path) route(); else location.hash=path; }
export function refresh() { return route(); }
export function channelLink(channel) {
  return link([el('span', {class:'avatar','aria-hidden':'true'}, channel.title.slice(0,1)), el('span', {}, channel.title)], '#/channel/' + encodeURIComponent(channel.slug), {class:'channel-link'});
}
async function channelList() {
  if (!session) return [];
  try { return (await all('/owner/channels')).filter(c=>c.published); }
  catch (error) { if ([403,404].includes(error.status)) return []; throw error; }
}
function account() {
  const host = document.querySelector('#account'); host.replaceChildren();
  if (!session) host.append(link('Sign in', '#/login'));
  else host.append(el('span', {}, session.user.display_name), button('Sign out', async () => {
    try { await api('/auth/session', {method:'DELETE'}); clearRequests(); setSession(null); navigate('/login'); }
    catch (error) { toast(error.message); }
  }));
}
function signIn(register = false) {
  const username = field('Username', {name:'username',required:true,minlength:3,maxlength:40,pattern:'[a-z0-9_-]+',autocomplete:'username'});
  const password = field('Password', {name:'password',type:'password',required:true,minlength:12,maxlength:128,autocomplete:register?'new-password':'current-password'});
  const name = field('Display name', {name:'display_name',required:true,maxlength:80,autocomplete:'nickname'});
  const errors = el('div'), submit = el('button', {type:'submit',class:'primary'}, register?'Create account':'Sign in');
  const form = el('form', {onsubmit:async event => {
    event.preventDefault(); submit.disabled=true; errors.replaceChildren();
    try {
      const body = {username:username.input.value,password:password.input.value};
      if (register) body.display_name=name.input.value;
      const result = await api('/auth/'+(register?'register':'login'), {method:'POST',body});
      clearRequests(); setSession(result); navigate('/space');
    } catch(error) { errors.append(errorBox(error)); } finally { submit.disabled=false; password.input.value=''; }
  }}, register?name.node:null, username.node, password.node, submit, errors);
  return el('section', {class:'panel auth'}, el('div', {class:'eyebrow'},'Welcome to MarkeTOB'),
    el('h1', {},register?'Create your account':'Your bots. One space.'), message('Use your local MarkeTOB account.'), form,
    el('p', {},link(register?'Already registered? Sign in':'New here? Create an account',register?'#/login':'#/register')));
}
function openChannelForm() {
  const slug = field('Channel link or slug', {required:true,placeholder:'Paste a MarkeTOB channel link',maxlength:500});
  const errors = el('div');
  return el('form', {onsubmit:event=>{
    event.preventDefault(); errors.replaceChildren(); let value=slug.input.value.trim();
    try {
      if (value.includes('://')) {
        const url=new URL(value);
        if (url.origin!==location.origin || !url.hash.startsWith('#/channel/')) throw new Error();
        value=decodeURIComponent(url.hash.slice('#/channel/'.length));
      }
      if (!/^[a-z0-9-]{3,80}$/.test(value)) throw new Error();
      navigate('/channel/'+value);
    } catch { errors.append(errorBox(new Error('Enter a channel slug or a link from this MarkeTOB server.'))); }
  }}, slug.node, el('button', {type:'submit',class:'primary'},'Open channel'), errors);
}
routes.set('space', async () => el('div', {}, heading('My Space','A personal home for the things you follow.'),
  el('section', {class:'empty'}, el('h2', {},'Make room for your favorite sources'),
    message('Open a channel to explore its news, products and charts. The personal page editor is being added in this development stage.'),
    link('Explore channels', '#/channels'))));
routes.set('channels', async () => {
  const channels=await channelList();
  return el('div', {}, heading('Channels','Open a shared page or browse your published channels.'),
    el('div', {class:'stack'}, el('section', {class:'panel'}, openChannelForm()),
      el('section', {class:'panel'}, el('h2', {},'Published channels'),
        channels.length ? channels.map(channelLink) : message('No channels here yet. Open a link shared by a publisher.'))));
});
routes.set('studio', async()=>el('div', {}, heading('Studio','Publish useful spaces powered by your bots.'),
  el('section',{class:'empty'},el('h2',{},'Studio is being connected'),message('Bot and page management will be available in the next task.'))));
routes.set('channel', async parts => {
  const slug=parts[1];
  if (!/^[a-z0-9-]{3,80}$/.test(slug || '')) throw new Error('Invalid channel link.');
  let snapshot;
  try { snapshot=await api('/channels/'+encodeURIComponent(slug)); }
  catch(error) {
    if (error.status===404) return el('section',{class:'empty'}, el('h1',{},'Channel unavailable'),
      message('This page is private, unpublished or no longer available. Sign in with an allowed account or ask the publisher for access.'),
      !session?link('Sign in','#/login'):button('Check access',refresh));
    throw error;
  }
  return el('div', {}, heading(snapshot.channel.title,
    (snapshot.channel.visibility==='public'?'Public channel':'Selected users') + ' · Updated ' + new Date().toLocaleTimeString('en'),
    button('Refresh',refresh)), renderSnapshot(snapshot,{onAccessLost:refresh}));
});
async function route() {
  const own=++generation;
  document.querySelectorAll('dialog').forEach(d=>d.close());
  main.replaceChildren(message('Loading…')); sidebar.replaceChildren(); account();
  if (!navigator.onLine) { main.replaceChildren(el('section',{class:'empty'},el('h1',{},'You are offline'),
    message('Reconnect to load current content and verify access.'),button('Try again',refresh))); return; }
  const parts=location.hash.replace(/^#\/?/,'').split('/'), page=parts[0]||'space';
  document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.hash==='#/'+page?'page':'false'));
  try {
    if (page==='login'||page==='register') main.replaceChildren(signIn(page==='register'));
    else if (!session && !['channels','channel'].includes(page)) main.replaceChildren(signIn());
    else {
      const fn=routes.get(page), node=fn?await fn(parts):el('h1',{},'Page not found');
      if (own!==generation) return;
      main.replaceChildren(node);
    }
    main.focus({preventScroll:true});
    const channels=await channelList();
    if (own!==generation) return;
    sidebar.append(el('h2',{},'Your channels'), link('＋ Open a channel','#/channels',{class:'channel-link'}),
      channels.map(channelLink).reduce((f,n)=>(f.append(n),f),document.createDocumentFragment()),
      el('p',{class:'sidebar-note'},'All your bots in one calm, useful space.'));
    sidebar.querySelectorAll('a').forEach(a=>{if(a.hash===location.hash)a.setAttribute('aria-current','page');});
  } catch(error) { if(own===generation) main.replaceChildren(errorBox(error,refresh)); }
}
window.addEventListener('hashchange',route);
window.addEventListener('session-expired',()=>{clearRequests(); navigate('/login');});
window.addEventListener('offline',()=>{document.querySelector('#connection').textContent='Offline · Content hidden until access can be checked.';route();});
window.addEventListener('online',()=>{document.querySelector('#connection').textContent='';boot();});
window.addEventListener('pageshow',event=>{if(event.persisted)boot();});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden) { ++generation;main.replaceChildren(message('Return to refresh your space.'));sidebar.replaceChildren();document.querySelectorAll('dialog').forEach(d=>d.close()); }
  else boot();
});
async function boot() {
  try { setSession(await api('/auth/session')); }
  catch(error) {
    if(error.status===401) {setSession(null);clearRequests();}
    else {main.replaceChildren(errorBox(error,boot));return;}
  }
  await route();
}
boot();
