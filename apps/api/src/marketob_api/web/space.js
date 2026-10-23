import {sharePage} from './sharing.js';
import {api, all, session} from './api.js';
import {el, button, link, field, heading, message, modal, errorBox, toast} from './dom.js';
import {renderBlock} from './render.js';
import {favorites} from './favorites.js';
import {refreshStatuses} from './live.js';

// Only unconfirmed layout references survive visibility/offline transitions, never source data.
const pendingEdits=new Map();
window.addEventListener('private-state-cleared',()=>pendingEdits.clear());
const clone=value=>structuredClone(value);
function choose(label,options,value) {
  const input=el('select',{'aria-label':label},options.map(([id,name])=>el('option',{value:id},name)));
  if(value!==undefined)input.value=value;
  return {input,node:el('label',{},label,input)};
}
const blank=title=>({title,expected_template_version:0,layout:{schema_version:'1.0',template_version:1,theme:'blue',density:'compact',blocks:[]}});
const canonical=value=>Array.isArray(value)?value.map(canonical):(value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value);
const equalLayout=(page,body)=>page.title===body.title && JSON.stringify(canonical(page.layout))===JSON.stringify(canonical(body.layout));

export async function space(parts,{navigate,refresh}) {
  const account=session.user.user_id, pages=await all('/personal-pages'), root=el('div',{class:'space'});
  const active=()=>root.isConnected && session?.user.user_id===account && !document.hidden;
  function createPage(){
    const title=field('New page title',{required:true,maxlength:80,value:'My Space'}),errors=el('div');
    let body,key,busy=false;
    modal('Create personal page',el('div',{class:'stack'},title.node,errors),close=>[
      button('Create page',async()=>{
        if(busy || !title.input.reportValidity() || !active())return;
        if(!title.input.value.trim()){title.input.setCustomValidity('Enter a page title.');title.input.reportValidity();title.input.setCustomValidity('');return;}
        busy=true;body ||= blank(title.input.value.trim());key ||= crypto.randomUUID();title.input.disabled=true;errors.replaceChildren();
        try{const page=await api('/personal-pages',{method:'POST',body,key});close();if(active())navigate('/space/'+page.page_id);}
        catch(error){errors.append(errorBox(error),message('Retry uses the same creation request. Refresh the page list if you close this dialog.'));}
        finally{busy=false;}
      },{class:'primary'})]);
  }
  if(!pages.length){
    root.append(heading('My Space','A personal home for the things you follow.'),el('section',{class:'empty'},
      el('h2',{},'Build your own space'),message('Bring published blocks from your favorite channels together.'),
      button('Create My Space',createPage,{class:'primary'}),link('Import template','#/import'),link('Explore channels','#/channels')));
    return root;
  }
  const pageID=parts[1]||pages[0].page_id, route='/personal-pages/'+encodeURIComponent(pageID), cacheKey=account+':'+pageID;
  let snapshot=await api(route+'/snapshot'), saved=snapshot.page,draft=clone(saved),history=[],pending=null,undoing=false,previous=null;
  let busy=false,failed=null,preview=false,sourceSnapshot=null,sourceGeneration=0,liveDirty=false;
  const recovered=pendingEdits.get(cacheKey);
  if(recovered){
    if(equalLayout(saved,recovered.pending)){pendingEdits.delete(cacheKey);}
    else {({pending,undoing,previous,history,draft}=clone(recovered));failed=new Error('An edit has not been confirmed. Retry it or reload the saved page.');}
  }
  const savedChannels=(await favorites()).items.filter(i=>i.available);
  const status=el('p',{role:'status',class:'muted'}),errors=el('div'),blocks=el('div',{class:'blocks'});
  const pageSelect=choose('Personal page',pages.map(p=>[p.page_id,p.title]),pageID);
  pageSelect.input.addEventListener('change',()=>navigate('/space/'+pageSelect.input.value));
  const title=field('Space title',{required:true,maxlength:80,value:draft.title});
  const theme=choose('Theme',[['blue','Blue'],['ink','Ink']],draft.layout.theme);
  const density=choose('Density',[['compact','Compact'],['comfortable','Comfortable']],draft.layout.density);
  const source=choose('Source channel',savedChannels.map(c=>[c.slug,c.title]));
  const item=choose('Block to add',[]),sourceError=el('div');
  const add=button('Add block',()=>{
    const selected=sourceSnapshot?.channel.layout.blocks.find(b=>b.block_id===item.input.value);
    if(!selected)return;
    change(next=>next.layout.blocks.push({...clone(selected),block_id:'personal_'+crypto.randomUUID()}));
  },{class:'primary'});
  const editPanel=el('section',{class:'panel stack'},title.node,el('div',{class:'toolbar'},theme.node,density.node),
    el('div',{class:'toolbar source-picker'},source.node,item.node,add),sourceError,
    savedChannels.length?null:message('Save a readable channel in Channels to choose its published blocks.'));
  const undo=button('Undo',()=>{if(history.length)startSave(clone(history.at(-1)),true);});
  const previewButton=button('Preview',()=>{preview=!preview;paint();});
  const reload=async()=>{
    if(busy)return;busy=true;snapshot={page:saved,blocks:[]};paint();errors.replaceChildren();sourceSnapshot=null;item.input.replaceChildren();
    try{snapshot=await api(route+'/snapshot');saved=snapshot.page;draft=clone(saved);history=[];pending=null;failed=null;pendingEdits.delete(cacheKey);}
    catch(error){failed=error;}
    finally{busy=false;if(active()){await refreshChoices();paint();await loadSource();if(liveDirty)await root.onUpdates(null);}}
  };
  const refreshButton=button('Refresh',()=>{if(pending){toast('Retry the edit or choose Reload saved before refreshing.');return;}reload();});
  const deleteButton=button('Delete page',()=>modal('Delete personal page',message('Delete this personal layout? Its source channels will remain available.'),close=>[
    button('Delete',async()=>{close();if(!active())return;busy=true;paint();try{await api(route,{method:'DELETE'});pendingEdits.delete(cacheKey);if(active())navigate('/space');}catch(error){busy=false;failed=error;if(active())paint();}},{class:'danger'})]),{class:'danger'});
  root.append(heading('My Space','Your own layout, connected to live sources.',button('Share',()=>sharePage(saved)),link('Import template','#/import'),undo,previewButton,refreshButton),
    el('div',{class:'toolbar space-pages'},pageSelect.node,button('New page',createPage),deleteButton),status,errors,editPanel,blocks);
  title.input.addEventListener('change',()=>{if(title.input.reportValidity())change(next=>{next.title=title.input.value.trim();});});
  title.input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();title.input.blur();}});
  theme.input.addEventListener('change',()=>change(next=>{next.layout.theme=theme.input.value;}));
  density.input.addEventListener('change',()=>change(next=>{next.layout.density=density.input.value;}));
  source.input.addEventListener('change',loadSource);

  function change(fn){if(busy||pending)return;const next=clone(draft);fn(next);startSave(next,false);}
  function startSave(next,isUndo){
    if(busy||pending||!active())return;
    if(!next.title.trim()){title.input.setCustomValidity('Enter a page title.');title.input.reportValidity();title.input.setCustomValidity('');return;}
    if(next.layout.blocks.length>50){toast('A personal page supports up to 50 blocks.');return;}
    previous=clone(saved);undoing=isUndo;
    pending={title:next.title,expected_template_version:saved.layout.template_version,
      layout:{...next.layout,template_version:saved.layout.template_version+1}};
    draft={page_id:pageID,title:pending.title,layout:clone(pending.layout)};
    pendingEdits.set(cacheKey,{pending:clone(pending),draft:clone(draft),previous:clone(previous),undoing,history:clone(history)});
    attempt();
  }
  async function attempt(){
    if(busy||!pending||!active())return;busy=true;failed=null;errors.replaceChildren();paint();
    try{
      saved=await api(route,{method:'PUT',body:pending});
      if(undoing)history.pop();else {history.push(previous);history=history.slice(-20);}
      draft=clone(saved);pending=null;pendingEdits.delete(cacheKey);
      // Resolve again after save; never reuse content if its access changed during editing.
      snapshot={page:saved,blocks:[]};
      try{snapshot=await api(route+'/snapshot');}catch(error){failed=error;}
    }catch(error){
      failed=error;snapshot={page:saved,blocks:[]};sourceSnapshot=null;item.input.replaceChildren();
      try{snapshot=await api(route+'/snapshot');}catch{/* No authorized content can be retained. */}
    }finally{
      busy=false;
      if(active()){await refreshChoices();if(!pending)await loadSource();paint();}
      if(liveDirty&&active())await root.onUpdates(null);
    }
  }
  async function refreshChoices(){
    const own=++sourceGeneration;
    const selected=source.input.value;source.input.replaceChildren();item.input.replaceChildren();sourceSnapshot=null;
    try{
      const current=await favorites();if(!active()||own!==sourceGeneration)return;
      current.items.filter(c=>c.available).forEach(c=>source.input.append(el('option',{value:c.slug},c.title)));
      if([...source.input.options].some(o=>o.value===selected))source.input.value=selected;
    }catch(error){if(active())sourceError.replaceChildren(errorBox(error));}
  }
  async function loadSource(){
    const own=++sourceGeneration;sourceSnapshot=null;item.input.replaceChildren();sourceError.replaceChildren();add.disabled=true;
    if(!source.input.value||!active()||pending)return;
    try{
      const value=await api('/channels/'+encodeURIComponent(source.input.value));
      if(own!==sourceGeneration||!active())return;
      sourceSnapshot=value;
      for(const block of value.channel.layout.blocks){
        const record=value.records.find(r=>r.source.resource_id===block.source.resource_id);
        if(record)item.input.append(el('option',{value:block.block_id},record.content.title+' · '+block.content_type));
      }
      if(!item.input.options.length)sourceError.append(message('This channel has no available published blocks.'));
    }catch(error){if(own===sourceGeneration&&active()){sourceError.append(errorBox(error));snapshot={page:saved,blocks:[]};try{snapshot=await api(route+'/snapshot');}catch{/* Keep unavailable placeholders. */}if(error.status===404)await refreshChoices();}}
    finally{if(own===sourceGeneration&&active())paint();}
  }
  function paint(){
    root.className='space '+draft.layout.theme;
    // Source-picker requests can finish while the user is typing an unsaved title.
    if(document.activeElement!==title.input || busy || pending)title.input.value=draft.title;
    theme.input.value=draft.layout.theme;density.input.value=draft.layout.density;
    const currentOption=[...pageSelect.input.options].find(o=>o.value===pageID);if(currentOption)currentOption.textContent=saved.title;
    status.textContent=busy?'Saving…':pending?(failed?.status===409?'Not saved · Conflict with another client':'Save not confirmed'):'Saved · v'+saved.layout.template_version;
    errors.replaceChildren();
    if(failed)errors.append(errorBox(failed),el('div',{class:'toolbar'},
      pending&&failed.status!==409?button('Retry save',attempt):null,button('Reload saved',reload)));
    editPanel.hidden=preview;previewButton.textContent=preview?'Edit layout':'Preview';
    blocks.className='blocks '+draft.layout.theme+' '+(draft.layout.density==='comfortable'?'comfortable':'');blocks.replaceChildren();
    draft.layout.blocks.forEach((block,index)=>{
      const original=snapshot.page.layout.blocks.find(b=>b.block_id===block.block_id);
      const result=snapshot.blocks.find(b=>b.block_id===block.block_id);
      const compatible=original&&original.content_type===block.content_type&&original.source.channel_id===block.source.channel_id&&original.source.resource_id===block.source.resource_id;
      const record=compatible&&result?.available?result.record:null;
      const card=renderBlock(block,record,{channel_id:block.source.channel_id,actions:record?result.actions:[]},
        {onAccessLost:reload,onView:view=>change(next=>{next.layout.blocks[index].view=view;})});
      if(preview)card.querySelectorAll('select').forEach(s=>{s.disabled=true;});
      const controls=el('div',{class:'toolbar'},button('Move up',()=>change(next=>{const bs=next.layout.blocks;[bs[index-1],bs[index]]=[bs[index],bs[index-1]];}),{disabled:index===0}),
        button('Move down',()=>change(next=>{const bs=next.layout.blocks;[bs[index+1],bs[index]]=[bs[index],bs[index+1]];}),{disabled:index===draft.layout.blocks.length-1}),
        button('Remove block',()=>change(next=>{next.layout.blocks.splice(index,1);}),{class:'danger'}));
      controls.hidden=preview;
      blocks.append(el('section',{class:'space-item','data-space-block':block.block_id},card,controls));
    });
    if(!draft.layout.blocks.length)blocks.append(el('section',{class:'empty'},el('h2',{},'No blocks yet'),message('Choose a source channel and add a published block.')));
    for(const node of root.querySelectorAll('input,select,button')){
      if(busy||pending)node.disabled=true;
      else if(!node.closest('.space-item'))node.disabled=false;
    }
    if(!busy)errors.querySelectorAll('button').forEach(b=>{b.disabled=false;});
    undo.disabled=busy||!!pending||!history.length;add.disabled=busy||!!pending||!item.input.options.length||draft.layout.blocks.length>=50;
    root.dataset.unsaved=pending?'true':'false';
  }
  const scope=new AbortController();
  root.liveChannels=()=>[...new Set(draft.layout.blocks.map(b=>b.source.channel_id))];
  root.onLiveUnavailable=(ids=null)=>{
    snapshot={page:snapshot.page,blocks:ids?snapshot.blocks.map(result=>{
      const block=snapshot.page.layout.blocks.find(b=>b.block_id===result.block_id);
      return block&&ids.has(block.source.channel_id)?{block_id:result.block_id,available:false}:result;
    }):[]};
    sourceGeneration++;
    if(!ids||!sourceSnapshot||ids.has(sourceSnapshot.channel.channel_id)){sourceSnapshot=null;item.input.replaceChildren();}
    if(!ids)source.input.replaceChildren();
    else for(const option of [...source.input.options]){
      if(savedChannels.some(c=>c.slug===option.value&&ids.has(c.channel_id)))option.remove();
    }
    paint();
  };
  root.onUpdates=async items=>{
    const revoked=items?.some(i=>i.kind==='access.revoked');
    if(revoked)root.onLiveUnavailable(new Set(items.filter(i=>i.kind==='access.revoked').map(i=>i.channel_id)));
    if(busy){liveDirty=true;return;}
    if(items===null||items.some(i=>i.kind!=='request.status')){
      const value=await api(route+'/snapshot');if(!active())return;
      // Keep saved/draft/history/version independent from refreshed source payloads.
      snapshot=value;liveDirty=false;paint();
      if(revoked||items===null){await refreshChoices();if(!pending)await loadSource();}
    }
    await refreshStatuses(root,items);
  };
  window.addEventListener('route-leave',()=>scope.abort(),{once:true});
  window.addEventListener('beforeunload',event=>{if(pending){event.preventDefault();event.returnValue='';}},{signal:scope.signal});
  document.addEventListener('click',event=>{if(pending&&root.isConnected&&event.target.closest('a[href]')){event.preventDefault();toast('Retry the edit or choose Reload saved before leaving.');}},{capture:true,signal:scope.signal});
  paint();root.afterRender=loadSource;return root;
}
