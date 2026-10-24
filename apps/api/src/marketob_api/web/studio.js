import {api, all, session, setWorkspace} from './api.js';
import {el, button, link, field, heading, message, errorBox, modal, toast} from './dom.js';
import {channelEditor} from './studio-editor.js';

const scopes=['messages:write','events:read','events:ack','events:result'];
export function choose(label,values,value) {
  const input=el('select',{'aria-label':label},values.map(([id,name])=>el('option',{value:id},name)));input.value=value;
  return {input,node:el('label',{},label,input)};
}
export function secretDialog(title,secret,instruction) {
  const box=el('textarea',{'aria-label':'One-time credential',readonly:true,spellcheck:'false'},secret);
  const dialog=modal(title,el('div',{},message(instruction),box,
    el('p',{class:'notice'},'Store this credential securely. It will not be shown again.')),
    close=>[button('Copy credential',async()=>{try{await navigator.clipboard.writeText(box.value);toast('Credential copied.');}catch{box.select();toast('Select and copy the credential.');}}),button('I have saved it',close,{class:'primary'})]);
  dialog.addEventListener('close',()=>{box.value='';box.textContent='';});
  dialog.querySelector('.toolbar button').textContent='Close';
  return dialog;
}
export async function studio(parts,{refresh,navigate}) {
  const userID=session.user.user_id, routeHash=location.hash;
  const active=()=>session?.user.user_id===userID && location.hash===routeHash && !document.hidden;
  const workspaces=await all('/workspaces');
  const org=parts[1]?workspaces.find(w=>w.org_id===parts[1]):workspaces[0];
  if(parts[1]&&!org) return el('section',{class:'empty'},el('h1',{},'Workspace unavailable'),message('Your membership may have been removed.'),link('Back to Studio','#/studio'));
  const errors=el('div'), root=el('div',{class:'stack'});
  async function run(fn) {errors.replaceChildren();try{await fn();}catch(error){if(active())errors.replaceChildren(errorBox(error));}}
  const own=workspaces.find(w=>w.role==='owner');
  const workspaceForm=()=>{
    const name=field('Workspace name',{required:true,maxlength:80,value:own?.name||''});
    const submit=el('button',{type:'submit',class:'primary'},own?'Save workspace name':'Create workspace');
    return el('section',{class:'panel'},el('h2',{},own?'Your workspace':'Start publishing'),
      message('Connect your HTTP bot and publish a page your audience can follow.'),
      el('form',{onsubmit:event=>{event.preventDefault();submit.disabled=true;run(async()=>{
        const value=await api('/account/business-profile',{method:'PUT',body:{name:name.input.value}});
        if(active())navigate('/studio/'+value.org_id);
      }).finally(()=>{submit.disabled=false;});}},name.node,submit));
  };
  if(!org) return el('div',{class:'stack'},heading('Studio','Your bot. Your audience. Your workspace.'),workspaceForm(),errors);
  setWorkspace(org.org_id);
  const base='/studio/'+org.org_id, manage=org.role!=='editor';
  const selector=choose('Workspace',workspaces.map(w=>[w.org_id,w.name+' · '+w.role]),org.org_id);
  selector.input.addEventListener('change',()=>navigate('/studio/'+selector.input.value));
  root.append(heading('Studio',org.name+' · '+org.role,selector.node),
    el('nav',{class:'toolbar','aria-label':'Studio'},link('Bots & pages','#'+base),link('Team','#'+base+'/team'),
      button('Refresh',refresh)),errors);
  if(parts[2]==='channel') {
    if(!(await all('/owner/channels')).some(c=>c.channel_id===parts[3]))throw new Error('Page unavailable in this workspace.');
    root.append(await channelEditor(parts[3],{org,base,active,run,refresh,navigate,choose}));return root;
  }
  if(parts[2]==='team') {
    const members=await all('/workspaces/'+org.org_id+'/members');
    root.append(el('section',{class:'panel'},el('h2',{},'Workspace team'),
      message('Owner manages the team. Admin manages bots, keys and access. Editor designs and publishes pages.'),
      el('p',{class:'notice'},'One Owner per workspace. Transfer ownership before deleting the Owner’s account.')));
    if(org.role==='owner') {
      const name=field('Registered username',{required:true,pattern:'[a-z0-9_-]+',maxlength:40});
      const role=choose('Team role',[['editor','Editor'],['admin','Admin']],'editor');
      const submit=el('button',{type:'submit',class:'primary'},'Add or update member');
      root.append(el('form',{class:'panel',onsubmit:event=>{event.preventDefault();submit.disabled=true;run(async()=>{
        await api('/workspaces/'+org.org_id+'/members',{method:'PUT',body:{username:name.input.value,role:role.input.value}});
        if(active())refresh();
      }).finally(()=>{submit.disabled=false;});}},name.node,role.node,submit));
      const admins=members.filter(m=>m.role==='admin');
      const transfer=el('section',{class:'panel'},el('h2',{},'Transfer ownership'),
        message('The selected Admin becomes Owner. You become Admin. Channels, bots and keys continue working. The recipient must not already own a workspace.'));
      if(admins.length){
        const target=choose('New owner',admins.map(m=>[m.username,'@'+m.username]),admins[0].username);
        const password=field('Current password for transfer',{type:'password',required:true,minlength:12,maxlength:128,autocomplete:'current-password'});
        const send=el('button',{type:'submit',class:'danger'},'Review transfer');
        window.addEventListener('route-leave',()=>{password.input.value='';},{once:true});
        transfer.append(el('form',{onsubmit:event=>{
          event.preventDefault();const username=target.input.value;
          const dialog=modal('Transfer workspace to @'+username+'?',message('Only the new Owner will manage the team. You will remain an Admin until you leave or delete your account.'),close=>[
            button('Transfer ownership now',event=>{
              event.currentTarget.disabled=true;send.disabled=true;
              run(async()=>{
                await api('/workspaces/'+org.org_id+'/ownership',{method:'POST',body:{username,password:password.input.value}});
                close();if(active())refresh();
              }).finally(()=>{password.input.value='';send.disabled=false;close();});
            },{class:'danger'})]);
          dialog.addEventListener('close',()=>{password.input.value='';});
        }},target.node,password.node,send));
      }else transfer.append(message('Add an existing registered user as Admin before transferring ownership.'));
      root.append(transfer);
    }
    for(const member of members) {
      const panel=el('section',{class:'panel'},el('h3',{},member.display_name),message('@'+member.username+' · '+member.role));
      if(org.role==='owner'&&member.role!=='owner') {
        const role=choose('Role for '+member.username,[['editor','Editor'],['admin','Admin']],member.role);
        panel.append(el('div',{class:'toolbar'},role.node,button('Save role',()=>run(async()=>{
          await api('/workspaces/'+org.org_id+'/members',{method:'PUT',body:{username:member.username,role:role.input.value}});if(active())refresh();
        })),button('Remove member',()=>modal('Remove team member',message('@'+member.username+' will lose workspace permissions. Independent read grants remain separate.'),close=>[
          button('Remove',()=>{close();run(async()=>{await api('/workspaces/'+org.org_id+'/members/'+member.user_id,{method:'DELETE'});if(active())refresh();});},{class:'danger'})]))));
      }
      root.append(panel);
    } return root;
  }
  if(parts[2]==='bot') {
    if(!(await all('/bots')).some(b=>b.bot_id===parts[3]))throw new Error('Bot unavailable in this workspace.');
    const botID=parts[3], bot=await api('/bots/'+encodeURIComponent(botID));
    root.append(el('section',{class:'panel'},el('h2',{},bot.name),el('span',{class:'badge'},bot.state),
      message('Last seen: '+(bot.last_seen?new Date(bot.last_seen).toLocaleString('en'):'Not connected yet')),
      el('p',{},'Bot ID: ',el('code',{},botID)),message('Gateway: '+location.origin+'/v1'),
      message('Your HTTP service exchanges the registration credential with POST /v1/bot-registrations/exchange using Authorization: Bearer <credential>, body {}. It then uses the returned operational key to send messages and read events.')));
    if(manage&&bot.state!=='revoked') {
      const issue=async replacement=>{
        const value=await api('/bots/'+botID+'/keys',{method:'POST',body:{scopes,...(replacement?{replaces_key_id:replacement}:{})}});
        if(active())secretDialog('Operational key',value.api_key,'Expires '+new Date(value.key.expires_at).toLocaleDateString('en')+'. Refresh key inventory after closing.');
      };
      root.append(el('div',{class:'toolbar'},button('New registration credential',()=>run(async()=>{
        const value=await api('/bots/'+botID+'/registration',{method:'POST',body:{}});
        if(active())secretDialog('Registration credential',value.registration_credential,'Single use. Expires in 15 minutes. Earlier registration credentials are now invalid.');
      })),bot.state==='active'?button('Issue operational key',()=>run(()=>issue()),{class:'primary'}):null));
      const keys=await all('/bots/'+botID+'/keys');
      root.append(el('h2',{},'Key inventory'));
      for(const key of keys) {
        const remaining=new Date(key.expires_at).getTime()-Date.now();
        const state=key.revoked?'Revoked':remaining<=0?'Expired':remaining<=7*86400000?'Expires within 7 days':'Active';
        const panel=el('section',{class:'panel'},el('h3',{},key.prefix+'…'),el('span',{class:state==='Expired'||state==='Expires within 7 days'?'notice':'badge'},state),
          message('Expires '+new Date(key.expires_at).toLocaleString('en')),message(key.scopes.join(' · ')));
        if(!key.revoked) panel.append(el('div',{class:'toolbar'},button('Rotate key',()=>modal('Rotate operational key',message('The existing key will stop working immediately. Update your bot with the new key.'),close=>[
          button('Rotate now',()=>{close();run(()=>issue(key.key_id));},{class:'primary'})])),button('Revoke key',()=>modal('Revoke operational key',message('This key will stop working immediately.'),close=>[
          button('Revoke',()=>{close();run(async()=>{await api('/bots/'+botID+'/keys/'+key.key_id,{method:'DELETE'});if(active())refresh();});},{class:'danger'})]))));
        root.append(panel);
      }
      root.append(button('Revoke bot',()=>modal('Revoke bot',message('All credentials stop working and its channels become unavailable. This bot cannot be reactivated.'),close=>[
        button('Revoke bot permanently',()=>{close();run(async()=>{await api('/bots/'+botID,{method:'DELETE'});if(active())refresh();});},{class:'danger'})]),{class:'danger'}));
    } return root;
  }
  const [bots,channels]=await Promise.all([all('/bots'),all('/owner/channels')]);
  const botPanel=el('section',{class:'panel'},el('h2',{},'Bots'));
  for(const bot of bots) botPanel.append(link(bot.name+' · '+bot.state,'#'+base+'/bot/'+bot.bot_id,{class:'channel-link'}));
  if(!bots.length)botPanel.append(message('No bots connected yet. Register your first HTTP service.'));
  if(manage) {
    const name=field('Bot name',{required:true,maxlength:80}),submit=el('button',{type:'submit',class:'primary'},'Register bot');
    botPanel.append(el('form',{onsubmit:event=>{event.preventDefault();submit.disabled=true;run(async()=>{
      const value=await api('/bots',{method:'POST',body:{name:name.input.value}});
      if(active()) {
        const secret=secretDialog('Registration credential',value.registration_credential,'Give this single-use credential to your HTTP service. It expires in 15 minutes.');
        secret.addEventListener('close',()=>{if(active())navigate(base+'/bot/'+value.bot.bot_id);});
      }
    }).finally(()=>{submit.disabled=false;});}},name.node,submit));
  }
  root.append(botPanel);
  const channelPanel=el('section',{class:'panel'},el('h2',{},'Pages'));
  for(const channel of channels)channelPanel.append(link(channel.title+' · '+(channel.published?'Published':'Draft'),'#'+base+'/channel/'+channel.channel_id,{class:'channel-link'}));
  const liveBots=bots.filter(b=>b.state!=='revoked');
  if(liveBots.length) {
    const title=field('Page title',{required:true,maxlength:80}),slug=field('Page slug',{required:true,minlength:3,maxlength:80,pattern:'[a-z0-9-]+'});
    const bot=choose('Source bot',liveBots.map(b=>[b.bot_id,b.name]),liveBots[0].bot_id),submit=el('button',{type:'submit',class:'primary'},'Create page');
    channelPanel.append(el('form',{onsubmit:event=>{event.preventDefault();submit.disabled=true;run(async()=>{
      const value=await api('/channels',{method:'POST',body:{title:title.input.value,slug:slug.input.value,bot_id:bot.input.value,visibility:'selected'}});
      if(active())navigate(base+'/channel/'+value.channel_id);
    }).finally(()=>{submit.disabled=false;});}},title.node,slug.node,bot.node,message('New pages are visible to Selected users after publication.'),submit));
  } else channelPanel.append(message('Register a bot before creating a page.'));
  root.append(channelPanel);
  if(!own)root.append(workspaceForm());
  return root;
}
