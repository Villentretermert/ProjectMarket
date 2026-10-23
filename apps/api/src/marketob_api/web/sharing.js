import {api,session} from './api.js';
import {el,button,link,field,heading,message,modal,errorBox,toast} from './dom.js';

const url=code=>location.origin+'/app/#/import/'+code;
async function copy(value){try{await navigator.clipboard.writeText(value);toast('Copied.');}catch{toast('Select the displayed value and copy it.');}}
export function sharePage(page){
  const account=session.user.user_id,expiry=el('select',{'aria-label':'Link expiry'},
    el('option',{value:'30'},'30 days'),el('option',{value:'7'},'7 days'),el('option',{value:'never'},'Never'));
  const errors=el('div'),list=el('div',{class:'stack'}),root=el('div',{class:'stack'},
    message('Shares this saved title, appearance and source references. Source data and access rights are separate.'),
    message('The recipient needs an account and access to this same MarkeTOB server.'),el('label',{},'Link expiry',expiry),errors,list);
  let pending=null,busy=false;
  const active=()=>root.isConnected&&session?.user.user_id===account&&!document.hidden;
  const create=button('Create link',async()=>{
    if(busy||!active())return;busy=true;create.disabled=true;expiry.disabled=true;errors.replaceChildren();
    pending ||= {key:crypto.randomUUID(),body:{expected_template_version:page.layout.template_version,
      expires_at:expiry.value==='never'?null:new Date(Date.now()+Number(expiry.value)*86400000).toISOString()}};
    try{await api('/personal-pages/'+page.page_id+'/shares',{method:'POST',...pending});pending=null;if(active())await load();}
    catch(error){if(active())errors.append(errorBox(error),message('Retry uses the same link request. Reload My Space if its saved version changed.'));}
    finally{busy=false;if(active()){create.disabled=false;expiry.disabled=!!pending;create.textContent=pending?'Retry create link':'Create link';}}
  },{class:'primary'});
  async function load(){
    try{
      const result=await api('/personal-pages/'+page.page_id+'/shares');if(!active())return;
      list.replaceChildren();if(!result.items.length)list.append(message('No active links.'));
      for(const share of result.items){
        const value=field('Template link',{value:url(share.code),readonly:true}),code=field('Template code',{value:share.code,readonly:true});
        const row=el('section',{class:'panel stack'},value.node,code.node,message(share.expires_at?'Expires '+new Date(share.expires_at).toLocaleString('en'):'No expiry'),
          el('div',{class:'toolbar'},button('Copy link',()=>copy(url(share.code))),button('Copy code',()=>copy(share.code)),button('Revoke',async()=>{
            if(!active())return;try{await api('/shares/'+share.share_id,{method:'DELETE'});if(active())await load();}catch(error){if(active())errors.replaceChildren(errorBox(error));}
          },{class:'danger'})));list.append(row);
      }
    }catch(error){if(active())errors.replaceChildren(errorBox(error,load));}
  }
  modal('Share personal page',root,()=>[create]);load();
}

function parseCode(value){
  let code=value.trim();
  if(code.includes('://')){
    const value=new URL(code);
    if(value.origin!==location.origin||value.pathname!=='/app/'||value.search||!value.hash.startsWith('#/import/'))throw new Error('Use a link from this MarkeTOB server.');
    code=value.hash.slice(9);
  }
  if(!/^[A-Za-z0-9_-]{32}$/.test(code))throw new Error('Enter a valid template code or same-server link.');
  return code;
}
export function importTemplate(parts,{navigate}){
  const account=session.user.user_id,root=el('div'),errors=el('div'),preview=el('section',{class:'panel stack',hidden:true});
  const input=field('Template link or code',{required:true,maxlength:500,value:parts[1]||''});
  const active=()=>root.isConnected&&session?.user.user_id===account&&!document.hidden;
  let code=null,key=null,busy=false;
  const submit=button('Import as new page',async()=>{
    if(busy||!code||!active())return;busy=true;submit.disabled=true;errors.replaceChildren();
    key ||= crypto.randomUUID();
    try{const page=await api('/template-imports',{method:'POST',body:{code},key});if(active())navigate('/space/'+page.page_id);}
    catch(error){if(active())errors.append(errorBox(error),message('Retry recovers the same imported page.'));}
    finally{busy=false;if(active())submit.disabled=false;}
  },{class:'primary'});
  const inspect=button('Preview template',async()=>{
    if(busy||!active()||!input.input.reportValidity())return;errors.replaceChildren();preview.hidden=true;
    try{
      const next=parseCode(input.input.value);busy=true;inspect.disabled=true;input.input.disabled=true;
      const data=await api('/template-imports/preview',{method:'POST',body:{code:next}});if(!active())return;
      code=next;key=null;preview.replaceChildren(el('h2',{},data.title.slice(0,73)+' (copy)'),
        message('Theme: '+data.layout.theme+' · Density: '+data.layout.density),
        message('Creates an independent page. Access to each source is checked with your account.'));
      const list=el('ol');for(const block of data.layout.blocks)list.append(el('li',{},block.content_type+' · '+block.view+' · '+(data.unavailable_blocks.includes(block.block_id)?'Source unavailable':'Available')));
      preview.append(list,submit);preview.hidden=false;
    }catch(error){if(active()){code=null;errors.append(errorBox(error));}}
    finally{busy=false;if(active()){inspect.disabled=false;input.input.disabled=false;}}
  },{class:'primary'});
  input.input.addEventListener('input',()=>{code=null;key=null;preview.hidden=true;});
  root.append(heading('Import template','Bring a shared layout into your own space.',link('My Space','#/space')),
    el('section',{class:'panel stack'},input.node,inspect,errors),preview);return root;
}
