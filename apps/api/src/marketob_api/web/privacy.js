import {api,session,setSession} from './api.js';
import {el,button,link,field,heading,message,errorBox,modal} from './dom.js';
import {clearRequests} from './actions.js';

export async function privacy({refresh,navigate}) {
  const userID=session.user.user_id, preview=await api('/account/deletion-preview');
  const root=el('div',{class:'stack'}),errors=el('div'),progress=el('p',{role:'status',class:'muted'});
  const controller=new AbortController();
  const active=()=>root.isConnected&&session?.user.user_id===userID;
  window.addEventListener('route-leave',()=>controller.abort(),{once:true});
  const download=button('Download JSON',async()=>{
    download.disabled=true;errors.replaceChildren();progress.textContent='Preparing your export…';
    try {
      const parts=['{"schema_version":"1.0","started_at":'+JSON.stringify(new Date().toISOString())];
      let size=0;
      for(const section of ['profile','favorites','spaces','requests','events']) {
        parts.push(','+JSON.stringify(section)+':[');let cursor=null,first=true,count=0;
        do {
          const batch=await api('/account/export?section='+section+(cursor?'&cursor='+encodeURIComponent(cursor):''),
            {signal:AbortSignal.any([controller.signal,AbortSignal.timeout(15000)])});
          if(!active())return;
          for(const item of batch.items){
            const text=JSON.stringify(item);size+=new Blob([text]).size;
            if(size>50*1024*1024)throw new Error('This export exceeds the 50 MB browser limit. Use the paginated export API to download all records.');
            parts.push((first?'':',')+text);first=false;count++;
          }
          cursor=batch.next_cursor;progress.textContent='Preparing '+section+' · '+count+' records';
        }while(cursor);
        parts.push(']');
      }
      parts.push(',"completed_at":'+JSON.stringify(new Date().toISOString())+'}');
      const url=URL.createObjectURL(new Blob(parts,{type:'application/json'}));
      const anchor=link('Download',url,{download:'marketob-personal-data.json'});root.append(anchor);anchor.click();anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      progress.textContent='Your JSON file is ready. Keep your downloaded copy private.';
    }catch(error){if(active()){progress.textContent='Export was not completed. No partial file was downloaded.';errors.replaceChildren(errorBox(error));}}
    finally{download.disabled=false;}
  },{class:'primary'});
  root.append(heading('Data & privacy','Manage your local MarkeTOB account.',button('Refresh',refresh)),
    el('section',{class:'panel'},el('h2',{},'Download your data'),
      message('Profile, Favorites, My Space, your request records and Events settings.'),
      message('Source contents, bot keys, passwords and other people’s data are excluded. References do not grant access to a channel.'),download,progress),errors);
  const removal=el('section',{class:'panel'},el('h2',{},'Delete account'),
    message(preview.personal_pages+' personal '+(preview.personal_pages===1?'space':'spaces')+' · '+preview.unresolved_requests+' unresolved '+(preview.unresolved_requests===1?'request':'requests')),
    message('All sessions will end. Your personal spaces, Favorites, Events settings and shared links will be removed. Workspace channels and bots stay with their new owner.'),
    el('p',{class:'notice'},'Your username and ID remain reserved. Request records follow the retention policy; acknowledged operations may still finish. External bot data, downloaded copies and operator backups are not erased by this action.'));
  if(!preview.can_delete){
    removal.append(el('h3',{},'Transfer ownership first'),message('You cannot delete your account while you own a workspace. In Studio → Team, transfer it to an active Admin who does not already own a workspace.'));
    for(const org of preview.owned_workspaces)removal.append(link('Open team: '+org.name,'#/studio/'+org.org_id+'/team',{class:'channel-link'}));
  }else{
    const password=field('Current password',{type:'password',required:true,minlength:12,maxlength:128,autocomplete:'current-password'});
    const confirmation=field('Type DELETE to confirm',{required:true,pattern:'DELETE',maxlength:6,autocomplete:'off'});
    const submit=el('button',{type:'submit',class:'danger'},'Review deletion');
    window.addEventListener('route-leave',()=>{password.input.value='';confirmation.input.value='';},{once:true});
    removal.append(el('form',{onsubmit:event=>{
      event.preventDefault();errors.replaceChildren();
      const dialog=modal('Delete your account?',message('This removes your personal setup and ends every session. Requests already acknowledged by a bot may still complete. This cannot be undone.'),close=>[
        button('Delete account permanently',async event=>{
          const trigger=event.currentTarget;trigger.disabled=true;submit.disabled=true;
          try{
            await api('/account',{method:'DELETE',body:{password:password.input.value,confirmation:confirmation.input.value}});
            if(active()){clearRequests();setSession(null);close();navigate('/login');}
          }catch(error){if(active()){close();errors.replaceChildren(errorBox(error,refresh));}}
          finally{password.input.value='';submit.disabled=false;}
        },{class:'danger'})]);
      dialog.addEventListener('close',()=>{password.input.value='';});
    }},password.node,confirmation.node,submit));
  }
  root.append(removal);return root;
}
