import {api, all} from './api.js';
import {el, button, link, field, message, modal, toast} from './dom.js';
import {views, renderSnapshot} from './render.js';

export async function channelEditor(id,{org,base,active,run,refresh,navigate,choose}) {
  const route='/owner/channels/'+encodeURIComponent(id), manage=org.role!=='editor';
  let [channel,resources,versions]=await Promise.all([api(route),all(route+'/resources'),all(route+'/versions')]);
  let blocks=structuredClone(channel.layout.blocks), actions=structuredClone(channel.actions), dirty=false,busy=false;
  const title=field('Page title',{required:true,maxlength:80,value:channel.title});
  const visibility=choose('Audience',[['selected','Selected users'],['public','Public']],channel.visibility);
  visibility.input.disabled=!manage;
  const theme=choose('Theme',[['blue','Blue'],['ink','Ink']],channel.layout.theme);
  const density=choose('Density',[['compact','Compact'],['comfortable','Comfortable']],channel.layout.density);
  const root=el('div',{class:'stack'}),notice=el('p',{role:'status',class:'muted'}),list=el('div',{class:'stack'});
  const published=versions.find(v=>v.channel.published)?.channel.layout.template_version;
  const publishButton=button('Publish',()=>modal('Publish page',message('Publish saved draft version '+channel.layout.template_version+' for '+(channel.visibility==='public'?'everyone':'selected users')+'?'),close=>[
    button('Publish now',()=>{close();run(async()=>{await api(route+'/publish',{method:'POST',body:{expected_template_version:channel.layout.template_version}});if(active())refresh();});},{class:'primary'})]),{class:'primary'});
  function changed(){dirty=true;notice.textContent='Unsaved changes. Save the draft before publishing.';publishButton.disabled=true;}
  for(const input of [title.input,visibility.input,theme.input,density.input])input.addEventListener('input',changed);
  const save=el('button',{type:'submit',class:'primary'},'Save draft');
  const form=el('form',{class:'panel',onsubmit:event=>{
    event.preventDefault();if(busy)return;busy=true;save.disabled=true;publishButton.disabled=true;
    run(async()=>{
      await api(route,{method:'PUT',body:{title:title.input.value,visibility:visibility.input.value,actions,
        expected_template_version:channel.layout.template_version,
        layout:{...channel.layout,template_version:channel.layout.template_version+1,
          theme:theme.input.value,density:density.input.value,blocks}}});
      if(active()){toast('Draft saved.');refresh();}
    }).finally(()=>{busy=false;save.disabled=false;publishButton.disabled=dirty;});
  }},el('h2',{},'Page editor'),message('Draft v'+channel.layout.template_version+' · '+(published?'Live version v'+published:'Not published')),
    title.node,visibility.node,el('div',{class:'toolbar'},theme.node,density.node),notice,list,save);
  root.append(form);
  function paintBlocks(){
    list.replaceChildren();
    blocks.forEach((block,index)=>{
      const record=resources.find(r=>r.source.resource_id===block.source.resource_id);
      const view=choose('View for block '+(index+1),views[block.content_type].map(v=>[v,v]),block.view);
      view.input.addEventListener('change',()=>{block.view=view.input.value;changed();});
      const panel=el('section',{class:'block','data-editor-block':block.block_id},el('h3',{},record?.content.title||'Source unavailable'),
        message(block.content_type+' · '+block.source.resource_id),view.node);
      if(block.content_type==='product') {
        const action=el('input',{type:'checkbox','aria-label':'Allow Request purchase for '+(record?.content.title||block.block_id)});
        action.checked=block.action_ids.length>0;
        action.addEventListener('change',()=>{
          if(action.checked) {
            let existing=actions.find(a=>a.resource_id===block.source.resource_id);
            if(!existing){existing={action_id:'purchase_'+crypto.randomUUID(),resource_id:block.source.resource_id,kind:'request_purchase',label:'Request purchase'};actions.push(existing);}
            block.action_ids=[existing.action_id];
          } else block.action_ids=[];
          trimActions();changed();
        });
        panel.append(el('label',{class:'checkbox'},action,'Allow Request purchase'));
      }
      panel.append(el('div',{class:'toolbar'},button('Move up',()=>{[blocks[index-1],blocks[index]]=[blocks[index],blocks[index-1]];changed();paintBlocks();},{disabled:index===0}),
        button('Move down',()=>{[blocks[index+1],blocks[index]]=[blocks[index],blocks[index+1]];changed();paintBlocks();},{disabled:index===blocks.length-1}),
        button('Remove block',()=>{blocks.splice(index,1);trimActions();changed();paintBlocks();},{class:'danger'})));
      list.append(panel);
    });
    if(!blocks.length)list.append(message('No blocks in this draft. Add a source below.'));
  }
  function trimActions(){const used=new Set(blocks.flatMap(b=>b.action_ids));actions=actions.filter(a=>used.has(a.action_id));}
  paintBlocks();
  const sourcePanel=el('section',{class:'panel'},el('h2',{},'Bot data sources'),message('Channel ID: '+id),
    message('Send typed messages to this channel through POST /v1/bot/messages, then refresh sources.'));
  if(resources.length) {
    const source=choose('Source to add',resources.map(r=>[r.source.resource_id,r.content.title+' · '+r.content_type]),resources[0].source.resource_id);
    sourcePanel.append(source.node,button('Add block',()=>{
      if(blocks.length>=50){toast('A page supports up to 50 blocks.');return;}
      const record=resources.find(r=>r.source.resource_id===source.input.value);
      blocks.push({block_id:'block_'+crypto.randomUUID(),source:record.source,content_type:record.content_type,
        view:{news:'article',product:'list',chart:'line'}[record.content_type],action_ids:[]});changed();paintBlocks();
    }));
  } else sourcePanel.append(message('Waiting for the bot to send its first data. You can save an empty draft.'));
  root.append(sourcePanel,
    el('section',{class:'panel'},el('h2',{},'Preview & publication'),
      message('Preview shows the saved draft. Live bot data keeps updating after publication.'),
      el('div',{class:'toolbar'},button('Preview saved draft',()=>run(async()=>{
        const snapshot=await api(route+'/preview');if(!active())return;
        // Preview never sends consumer actions from an unpublished draft.
        snapshot.channel.actions=[];
        modal('Saved draft preview',renderSnapshot(snapshot),close=>[button('Close preview',close)]);
      })),publishButton,
      channel.published?link('Open live page','#/channel/'+channel.slug):null,
      button('Copy page link',async()=>{try{await navigator.clipboard.writeText(location.origin+'/app/#/channel/'+channel.slug);toast('Page link copied.');}catch{toast('Page link: '+location.origin+'/app/#/channel/'+channel.slug);}}))));
  const old=versions.filter(v=>v.published_at&&v.channel.layout.template_version!==channel.layout.template_version);
  if(old.length){
    const version=choose('Published version to restore',old.map(v=>[String(v.channel.layout.template_version),'Version '+v.channel.layout.template_version+' · '+v.channel.title]),String(old.at(-1).channel.layout.template_version));
    root.append(el('section',{class:'panel'},el('h2',{},'Version history'),version.node,
      button('Restore version',()=>modal('Restore published version',message('Creates and publishes a new version. Current source data stays live. Any unsaved changes will be discarded.'),close=>[
        button('Restore and publish',()=>{close();run(async()=>{await api(route+'/rollback',{method:'POST',body:{expected_template_version:channel.layout.template_version,target_template_version:Number(version.input.value)}});if(active())refresh();});},{class:'primary'})]))));
  }
  if(manage){
    const grants=await all(route+'/audience');
    const username=field('Username to grant access',{required:true,pattern:'[a-z0-9_-]+',maxlength:40});
    const grantButton=el('button',{type:'submit',class:'primary'},'Grant read access');
    const audience=el('section',{class:'panel'},el('h2',{},'Selected users'),message('Read access is separate from team membership. Public pages are readable by everyone.'),
      el('form',{onsubmit:event=>{event.preventDefault();grantButton.disabled=true;run(async()=>{
        const user=await api('/users/by-username/'+encodeURIComponent(username.input.value));
        await api(route+'/grants/'+user.user_id,{method:'PUT',body:{}});if(active())refresh();
      }).finally(()=>{grantButton.disabled=false;});}},username.node,grantButton));
    for(const grant of grants)audience.append(el('div',{class:'toolbar'},el('span',{},grant.display_name+' · @'+grant.username),button('Revoke read access',()=>run(async()=>{
      await api(route+'/grants/'+grant.user_id,{method:'DELETE'});if(active())refresh();
    }))));
    root.append(audience,button('Delete page',()=>modal('Delete page',message('Unpublishes this channel and stops new requests. Historical data is retained for recovery.'),close=>[
      button('Delete page permanently',()=>{close();run(async()=>{await api(route,{method:'DELETE'});if(active())navigate(base);});},{class:'danger'})]),{class:'danger'}));
  }
  return root;
}
