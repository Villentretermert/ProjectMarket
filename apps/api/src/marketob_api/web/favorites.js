import {api, session} from './api.js';
import {el, button, link, field, message, toast, heading} from './dom.js';

export async function favorites() { return session ? api('/favorites') : {revision:0,items:[]}; }
export function favoriteLink(item) {
  return item.available ? link([
    el('span',{class:'avatar','aria-hidden':'true'},item.title.slice(0,1)),
    el('span',{},item.title), item.unread?el('span',{class:'badge'},'New'):null,
  ],'#/channel/'+item.slug,{class:'channel-link'}) : el('span',{class:'channel-link muted'},'Channel unavailable');
}
export async function channels(openForm, refresh) {
  let saved=await favorites();const host=el('div',{class:'stack'}), search=field('Search favorites',{type:'search',maxlength:80});
  let busy=false;
  const draw=()=>{
    host.replaceChildren();
    const query=search.input.value.trim().toLocaleLowerCase('en');
    saved.items.forEach((item,index)=>{
      if(query && !(item.available?item.title:'Channel unavailable').toLocaleLowerCase('en').includes(query))return;
      const run=async fn=>{if(busy)return;busy=true;try{await fn();await refresh();}catch(error){toast(error.message);}finally{busy=false;}};
      const move=offset=>run(async()=>{
        const ids=saved.items.map(i=>i.channel_id);[ids[index],ids[index+offset]]=[ids[index+offset],ids[index]];
        await api('/favorites/order',{method:'PUT',body:{expected_revision:saved.revision,channel_ids:ids}});
      });
      host.append(el('section',{class:'favorite-row','data-favorite':item.channel_id}, favoriteLink(item),
        el('div',{class:'toolbar'},button('Move up',()=>move(-1),{disabled:index===0}),
          button('Move down',()=>move(1),{disabled:index===saved.items.length-1}),
          button('Remove',()=>run(()=>api('/favorites/'+item.channel_id,{method:'DELETE'}))))));
    });
    if(!host.children.length)host.append(message(saved.items.length?'No favorites match your search.':'No favorites yet. Open a shared channel and choose Add to favorites.'));
  };
  search.input.addEventListener('input',draw);draw();
  const root=el('div',{},heading('Channels','Keep the channels you follow in your own order.',button('Refresh',refresh)),
    el('div',{class:'stack'},el('section',{class:'panel'},openForm()),
    el('section',{class:'panel'},el('h2',{},'Favorites'),session?search.node:link('Sign in to save channels','#/login'),host)));
  root.liveChannels=()=>saved.items.map(i=>i.channel_id);
  root.onUpdates=async()=>{const value=await favorites();if(root.isConnected){saved=value;draw();}};
  root.onLiveUnavailable=()=>{saved={...saved,items:saved.items.map(i=>({channel_id:i.channel_id,available:false}))};draw();};
  root.onAccessRevoked=ids=>{saved={...saved,items:saved.items.map(i=>ids.has(i.channel_id)?{channel_id:i.channel_id,available:false}:i)};draw();};
  return root;
}
export async function channelFavorite(snapshot, refresh) {
  const channel=snapshot.channel, host=el('div',{class:'toolbar'});
  if(!session)return {node:link('Sign in to save','#/login/'+channel.slug),seen:async()=>{}};
  const account=session.user.user_id, saved=await favorites(), exists=saved.items.some(i=>i.channel_id===channel.channel_id);
  const observed={data_revision:snapshot.data_revision,template_version:channel.layout.template_version};
  const seen=()=>api('/favorites/'+channel.channel_id+'/seen',{method:'PUT',body:observed});
  host.append(button(exists?'Remove from favorites':'Add to favorites',async()=>{
    if(session?.user.user_id!==account)return;
    try {
      await api('/favorites/'+channel.channel_id,{method:exists?'DELETE':'PUT',...(!exists?{body:{}}:{})});
      if(!exists)await seen();await refresh();
    }catch(error){toast(error.message);if(error.status===404)await refresh();}
  }));
  // Mark the exact rendered revisions, never a later revision that arrived in the meantime.
  return {node:host,seen:async()=>{if(exists && session?.user.user_id===account)await seen();}};
}
