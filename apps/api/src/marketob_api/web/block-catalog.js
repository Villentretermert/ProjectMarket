import {el, button, field, message} from './dom.js';
import {renderBlockPreview} from './render.js';

// Own only the authorized snapshot in memory. Clearing it also removes every preview.
export function blockCatalog(onAdd) {
  const search=field('Search blocks',{type:'search',maxlength:120,placeholder:'Search titles and content'});
  const type=el('select',{'aria-label':'Block type'},[['all','All types'],['product','Products'],['news','News'],['chart','Charts']].map(([id,name])=>el('option',{value:id},name)));
  const count=el('p',{class:'muted',role:'status'}),grid=el('div',{class:'catalog-grid'}),hint=message('');
  const node=el('section',{class:'block-catalog','aria-label':'Block catalog'},el('h2',{},'Block catalog'),
    message('Preview published blocks from your favorite channels.'),
    el('div',{class:'toolbar catalog-filters'},search.node,el('label',{},'Block type',type)),count,grid,hint);
  let snapshot=null,disabled=false,limit=false,focusAfterAdd=null;
  function draw(){
    const focus=document.activeElement?.closest('[data-catalog-block]')?.dataset.catalogBlock||focusAfterAdd;
    grid.replaceChildren();
    if(!snapshot){count.textContent='';hint.textContent='';return;}
    const query=search.input.value.trim().toLocaleLowerCase('en');
    const candidates=snapshot.channel.layout.blocks.flatMap(block=>{
      const record=snapshot.records.find(r=>r.source.channel_id===block.source.channel_id&&r.source.resource_id===block.source.resource_id);
      return record?[{block,record}]:[];
    });
    const matches=candidates.filter(({block,record})=>{
      const data=record.content,text=[data.title,data.body,data.description].filter(Boolean).join(' ').toLocaleLowerCase('en');
      return (type.value==='all'||block.content_type===type.value)&&(!query||text.includes(query));
    });
    count.textContent=matches.length+' of '+candidates.length+' blocks';
    for(const {block,record} of matches){
      const add=button('Add to My Space',()=>{if(snapshot&&!disabled&&!limit){focusAfterAdd=block.block_id;onAdd(block.block_id);}},{class:'primary',disabled:disabled||limit});
      grid.append(el('article',{class:'catalog-card','data-catalog-block':block.block_id},renderBlockPreview(block,record),add));
    }
    if(!candidates.length)grid.append(message('This channel has no available published blocks.'));
    else if(!matches.length)grid.append(el('div',{class:'catalog-empty'},message('No blocks match your filters.'),button('Clear filters',()=>{
      search.input.value='';type.value='all';draw();search.input.focus();
    })));
    hint.textContent=limit?'Your space has 50 blocks. Remove one to add another.':disabled?'Finish saving your changes before adding a block.':'';
    // Keep keyboard position when a save refreshes the same source.
    if(focus&&!disabled&&(document.activeElement===document.body||node.contains(document.activeElement)))for(const card of grid.children)if(card.dataset.catalogBlock===focus){card.querySelector('button')?.focus({preventScroll:true});focusAfterAdd=null;}
  }
  search.input.addEventListener('input',draw);type.addEventListener('change',draw);
  return {node,setSource(value){snapshot=value;draw();},setState(blocked,full){
    disabled=blocked;limit=full;
    for(const add of grid.querySelectorAll('.catalog-card>button'))add.disabled=disabled||limit;
    if(!disabled&&focusAfterAdd&&snapshot){for(const card of grid.children)if(card.dataset.catalogBlock===focusAfterAdd)card.querySelector('button')?.focus({preventScroll:true});focusAfterAdd=null;}
    hint.textContent=snapshot?(limit?'Your space has 50 blocks. Remove one to add another.':disabled?'Finish saving your changes before adding a block.':''):'';
  }};
}
