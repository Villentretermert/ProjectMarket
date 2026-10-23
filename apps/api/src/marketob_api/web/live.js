import {api,session} from './api.js';
import {el,button,modal,message,errorBox,toast} from './dom.js';

export async function eventPreferences(channelID){
  const errors=el('div'),body=el('div',{class:'stack'},message('Choose events shown while MarkeTOB is open.'));
  const names=[['news.published','News updates'],['catalog.changed','Catalog changes'],['request.status','My request status']];
  const inputs=names.map(([id,name])=>{const input=el('input',{type:'checkbox',value:id,'aria-label':name,disabled:true});body.append(el('label',{class:'event-choice'},input,name));return input;});
  let ready=false,busy=false;
  body.append(errors);
  let save;
  modal('Channel events',body,close=>[save=button('Save',async()=>{
    if(!ready||busy)return;busy=true;save.disabled=true;errors.replaceChildren();
    try{await api('/preferences/'+channelID,{method:'PUT',body:{channel_id:channelID,events:inputs.filter(i=>i.checked).map(i=>i.value)}});close();toast('Event preferences saved.');}
    catch(error){errors.append(errorBox(error));}finally{busy=false;save.disabled=false;}
  },{class:'primary',disabled:true})]);
  try{const value=await api('/preferences/'+channelID);inputs.forEach(i=>{i.checked=value.events.includes(i.value);i.disabled=false;});ready=true;save.disabled=false;}
  catch(error){errors.append(errorBox(error));}
}

export async function liveBootstrap(){return (await api('/updates')).next_cursor;}

export async function refreshStatuses(root,items){
  const ids=items?new Set(items.filter(i=>i.kind==='request.status').map(i=>i.target_id)):null;
  for(const host of root.querySelectorAll('[data-action-request]')){
    if(host.dataset.actionRequest&&(!ids||ids.has(host.dataset.actionRequest)))await host.onStatusUpdate?.();
  }
}

export function startLive(root,initialCursor,refreshSidebar){
  const account=session?.user.user_id,scope=new AbortController(),seen=new Set(),unavailable=new Set();
  const indicator=document.querySelector('#connection');
  let cursor=initialCursor,timer,needsResync=false,failures=0;
  const active=()=>!scope.signal.aborted&&root.isConnected&&!document.hidden&&navigator.onLine&&session?.user.user_id===account;
  const stop=()=>{scope.abort();clearTimeout(timer);};
  window.addEventListener('route-leave',stop,{once:true,signal:scope.signal});
  window.addEventListener('private-state-cleared',stop,{once:true,signal:scope.signal});
  const labels={'news.published':'News updated','catalog.changed':'Catalog updated','request.status':'Request status updated'};
  async function tick(){
    if(!active())return;
    let delay=2000;
    try{
      if(needsResync){
        // Establish a watermark before reading snapshots, including recovery after lost replies.
        cursor=await liveBootstrap();await root.onUpdates?.(null);await refreshSidebar();needsResync=false;unavailable.clear();
      }
      const query=new URLSearchParams({cursor});
      [...new Set(root.liveChannels?.()||[])].slice(0,50).forEach(cid=>query.append('watch',cid));
      const page=await api('/updates?'+query,{signal:AbortSignal.any([scope.signal,AbortSignal.timeout(5000)])});
      if(!active())return;
      // Authorization invalidations must clear the view on every poll. An independent
      // snapshot read may have restored content between two identical revoke hints.
      const denied=new Set(page.items.filter(i=>i.kind==='access.revoked').map(i=>i.channel_id));
      if(denied.size)root.onAccessRevoked?.(denied);
      const fresh=page.items.filter(item=>item.kind==='access.revoked'?!unavailable.has(item.channel_id):!seen.has(item.update_id));
      if(fresh.length){await root.onUpdates?.(fresh);if(!active())return;await refreshSidebar();}
      if(!active())return;
      // Advance only after applying the batch; a failed read triggers a full authorized resync.
      cursor=page.next_cursor;failures=0;indicator.textContent='Live';indicator.dataset.state='live';
      const notifications=new Set();
      for(const item of fresh){
        if(item.kind==='access.revoked')unavailable.add(item.channel_id);
        else {seen.add(item.update_id);unavailable.delete(item.channel_id);}
        if(item.notify)notifications.add(labels[item.event_name]);
      }
      while(seen.size>1000)seen.delete(seen.values().next().value);
      notifications.forEach(value=>{if(value)toast(value);});
      if(page.has_more)delay=50;
    }catch(error){
      if(!active())return;
      needsResync=true;root.onLiveUnavailable?.();document.querySelector('#sidebar').replaceChildren();
      document.querySelectorAll('dialog').forEach(d=>d.close());
      indicator.textContent='Reconnecting · Content hidden';
      indicator.dataset.state='reconnecting';
      delay=error.retryAfter?error.retryAfter*1000:Math.min(2000*2**failures++,8000);
    }finally{if(active())timer=setTimeout(tick,delay);}
  }
  indicator.textContent='Live';indicator.dataset.state='live';timer=setTimeout(tick,2000);
  return stop;
}
