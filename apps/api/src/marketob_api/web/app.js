import {api, session, setSession} from './api.js';
import {favorites, favoriteLink, channels, channelFavorite} from './favorites.js';
import {el, button, link, message, field, heading, errorBox, toast} from './dom.js';
import {renderSnapshot} from './render.js';
import {clearRequests} from './actions.js';
import {liveBootstrap,startLive,eventPreferences,refreshStatuses} from './live.js';

const main = document.querySelector('#main'), sidebar = document.querySelector('#sidebar');
let generation = 0;
export const routes = new Map();
export function navigate(path) { if (location.hash === '#' + path) route(); else location.hash=path; }
export function refresh() { return route(); }
export function channelLink(channel) {
  return link([el('span', {class:'avatar','aria-hidden':'true'}, channel.title.slice(0,1)), el('span', {}, channel.title)], '#/channel/' + encodeURIComponent(channel.slug), {class:'channel-link'});
}
function account() {
  const host = document.querySelector('#account'); host.replaceChildren();
  if (!session) host.append(link('Sign in', '#/login'));
  else host.append(el('span', {}, session.user.display_name), button('Sign out', async () => {
    try { await api('/auth/session', {method:'DELETE'}); clearRequests(); setSession(null); navigate('/login'); }
    catch (error) { toast(error.message); }
  }));
}
function signIn(register = false, returnSlug = '') {
  const target=/^import\/[A-Za-z0-9_-]{32}$/.test(returnSlug)?'/'+returnSlug:(/^[a-z0-9-]{3,80}$/.test(returnSlug)?'/channel/'+returnSlug:'');
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
      clearRequests(); setSession(result); navigate(target||'/space');
    } catch(error) { errors.append(errorBox(error)); } finally { submit.disabled=false; password.input.value=''; }
  }}, register?name.node:null, username.node, password.node, submit, errors);
  return el('section', {class:'panel auth'}, el('div', {class:'eyebrow'},'Welcome to MarkeTOB'),
    el('h1', {},register?'Create your account':'Your bots. One space.'), message('Use your local MarkeTOB account.'), form,
    el('p', {},link(register?'Already registered? Sign in':'New here? Create an account',(register?'#/login':'#/register')+(target?'/'+returnSlug:''))));
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
routes.set('space', async parts => (await import('./space.js')).space(parts,{navigate,refresh}));
routes.set('import', async parts => (await import('./sharing.js')).importTemplate(parts,{navigate}));
routes.set('channels', () => channels(openChannelForm,refresh));
routes.set('studio', async parts => (await import('./studio.js')).studio(parts,{refresh,navigate}));
routes.set('channel', async parts => {
  const slug=parts[1];
  if (!/^[a-z0-9-]{3,80}$/.test(slug || '')) throw new Error('Invalid channel link.');
  let snapshot;
  try { snapshot=await api('/channels/'+encodeURIComponent(slug)); }
  catch(error) {
    if (error.status===404) return el('section',{class:'empty'}, el('h1',{},'Channel unavailable'),
      message('This page is private, unpublished or no longer available. Sign in with an allowed account or ask the publisher for access.'),
      !session?link('Sign in','#/login/'+slug):button('Check access',refresh));
    throw error;
  }
  const saved=await channelFavorite(snapshot,refresh);
  const content=el('div',{},renderSnapshot(snapshot,{onAccessLost:refresh}));
  const title=heading(snapshot.channel.title,
    (snapshot.channel.visibility==='public'?'Public channel':'Selected users') + ' · Updated ' + new Date().toLocaleTimeString('en'),
    session?button('Events',()=>eventPreferences(snapshot.channel.channel_id)):null,button('Refresh',refresh));
  const node=el('div', {'data-live-revision':snapshot.data_revision},title,saved.node,content);
  const channelID=snapshot.channel.channel_id;
  node.liveChannels=()=>[channelID];
  node.onLiveUnavailable=()=>{title.querySelector('h1').textContent='Channel unavailable';saved.node.hidden=true;content.replaceChildren(message('Content hidden until access can be checked.'));};
  node.onUpdates=async items=>{
    if(items===null||items.some(i=>i.channel_id===channelID&&i.kind!=='request.status')){
      try{
        const value=await api('/channels/'+encodeURIComponent(slug));if(!node.isConnected)return;
        snapshot=value;title.querySelector('h1').textContent=value.channel.title;saved.node.hidden=false;
        content.replaceChildren(renderSnapshot(value,{onAccessLost:refresh}));node.dataset.liveRevision=value.data_revision;
        // The observed revision, not a newer unseen revision, clears the marker.
        await api('/favorites/'+channelID+'/seen',{method:'PUT',body:{data_revision:value.data_revision,template_version:value.channel.layout.template_version}});
      }catch(error){node.onLiveUnavailable();if(error.status!==404)throw error;}
    }
    await refreshStatuses(node,items);
  };
  node.afterRender=saved.seen;
  return node;
});
async function route() {
  window.dispatchEvent(new Event('route-leave'));
  const own=++generation;
  document.querySelector('#connection').textContent='';
  document.querySelectorAll('dialog').forEach(d=>d.close());
  main.replaceChildren(message('Loading…')); sidebar.replaceChildren(); account();
  if (!navigator.onLine) { main.replaceChildren(el('section',{class:'empty'},el('h1',{},'You are offline'),
    message('Reconnect to load current content and verify access.'),button('Try again',refresh))); return; }
  const parts=location.hash.replace(/^#\/?/,'').split('/'), page=parts[0]||'space';
  document.querySelectorAll('nav a').forEach(a=>a.setAttribute('aria-current',a.hash==='#/'+page?'page':'false'));
  try {
    if (page==='login'||page==='register') main.replaceChildren(signIn(page==='register',parts.slice(1).join('/')));
    else if (!session && !['channels','channel'].includes(page)) main.replaceChildren(signIn(false,page==='import'?'import/'+parts[1]:''));
    else {
      const cursor=session&&['space','channel','channels'].includes(page)?await liveBootstrap():null;
      const fn=routes.get(page), node=fn?await fn(parts):el('h1',{},'Page not found');
      if (own!==generation) return;
      main.replaceChildren(node);
      if(node.afterRender)await node.afterRender();
      if(own!==generation)return;
      if(cursor)startLive(node,cursor,()=>refreshSidebar(own));
    }
    if(document.activeElement===document.body||document.activeElement===main)main.focus({preventScroll:true});
    await refreshSidebar(own);
  } catch(error) { if(own===generation) main.replaceChildren(errorBox(error,refresh)); }
}
async function refreshSidebar(own){
    const saved=await favorites();
    if (own!==generation) return;
    sidebar.replaceChildren(el('h2',{},'Favorites'), link('＋ Open a channel','#/channels',{class:'channel-link'}),
      saved.items.map(favoriteLink).reduce((f,n)=>(f.append(n),f),document.createDocumentFragment()),
      el('p',{class:'sidebar-note'},'All your bots in one calm, useful space.'));
    sidebar.querySelectorAll('a').forEach(a=>{if(a.hash===location.hash)a.setAttribute('aria-current','page');});
}
window.addEventListener('hashchange',route);
window.addEventListener('session-expired',()=>{clearRequests(); navigate('/login');});
window.addEventListener('offline',()=>{document.querySelector('#connection').textContent='Offline · Content hidden until access can be checked.';route();});
window.addEventListener('online',()=>{document.querySelector('#connection').textContent='';boot();});
window.addEventListener('pageshow',event=>{if(event.persisted)boot();});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden) { window.dispatchEvent(new Event('route-leave'));++generation;main.replaceChildren(message('Return to refresh your space.'));sidebar.replaceChildren();document.querySelectorAll('dialog').forEach(d=>d.close()); }
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
