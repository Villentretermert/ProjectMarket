import fs from 'node:fs/promises';
import path from 'node:path';
const colors={ink:'#17334B',blue:'#1665B7',muted:'#536D82',paper:'#F7F9FC',line:'#C8D6E3',pale:'#EAF2FA',white:'#FFFFFF',green:'#23714F',amber:'#96631B'};
function text(s,value,x,y,w,h,size=28,color=colors.ink,bold=false){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.style={fontFamily:'Arial',fontSize:size,color,bold};t.text.insets=0;return t;
}
function box(s,label,x,y,w=240,h=108,pending=false){
 const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:pending?'#FFF4E1':colors.pale,line:{fill:pending?'#D9AC66':colors.blue,width:1.5}});
 n.text=label;n.text.style={fontFamily:'Arial',fontSize:25,color:colors.ink,alignment:'center',verticalAlignment:'middle'};n.text.insets=14;return n;
}
function arrow(s,a,b,fromSide='right',toSide='left',pending=false){return s.shapes.connect(a,b,{kind:'straight',fromSide,toSide,line:{fill:pending?colors.amber:colors.blue,width:2,style:pending?'dashed':'solid'},tail:{type:'triangle',width:'med',length:'med'}});}
function diagram(s,type){
 if(type==='context'){
  const b2c=box(s,'B2C\nWeb-клиент',65,200,250,104), b2b=box(s,'B2B\nStudio',65,390,250,104);
  const core=box(s,'MarkeTOB\nAPI + хранилище',470,290,300,120);
  const bot=box(s,'HTTP-боты\nPython / внешние',960,200,250,104),ext=box(s,'Другие сервисы\nRSS / бизнес-логика',960,390,250,104);
  arrow(s,b2c,core);arrow(s,b2b,core);arrow(s,bot,core,'left','right');arrow(s,bot,ext,'bottom','top');
  text(s,'POST данных\nGET событий',790,385,160,70,20);
  text(s,'Готово: Web, Studio, общий шлюз, Python-примеры',65,555,1140,45,26,colors.green);
  text(s,'Позже: Android, виджет, Google / FCM, облачная эксплуатация',65,610,1140,44,25,colors.amber);
 }else if(type==='containers'){
  const client=box(s,'Браузер\nHTML / JS',55,205,215,105),proxy=box(s,'Caddy\nHTTPS',340,205,215,105),api=box(s,'API\nFastAPI / Python',630,205,250,105),db=box(s,'PostgreSQL\nданные + outbox',980,205,245,105);
  arrow(s,client,proxy);arrow(s,proxy,api);arrow(s,api,db);
  const bot=box(s,'Пилотные боты\nотдельные контейнеры',420,450,300,105),maint=box(s,'Maintenance\nretention / outbox',895,450,300,105);
  arrow(s,bot,api,'top','bottom');arrow(s,maint,db,'top','bottom');
  text(s,'Docker Compose: единая сеть, отдельный volume БД, pinned images',65,605,1140,45,25);
  text(s,'Backup / restore запускает оператор отдельной командой.',65,648,1140,28,20);
 }else if(type==='entities'){
  const u=box(s,'User',60,190,210,80),w=box(s,'Workspace\nMembership',370,190,230,100),b=box(s,'Bot\nKey',710,190,210,100),c=box(s,'Channel\nLayout / Grant',1010,190,210,100);
  arrow(s,u,w);arrow(s,w,b);arrow(s,b,c);
  const p=box(s,'Personal page\nFavorite / Share',65,445,260,105),a=box(s,'Action request\nEvent / Delivery',470,445,280,105),r=box(s,'Record\nMessage receipt',945,445,275,105);
  arrow(s,u,p,'bottom','top');arrow(s,u,a,'bottom','left');arrow(s,c,r,'bottom','top');
  s.shapes.connect(p,r,{kind:'elbow',fromSide:'bottom',toSide:'bottom',line:{fill:colors.blue,width:2},tail:{type:'triangle'}});arrow(s,a,b,'top','bottom');
  text(s,'Layout хранит ссылки. Данные и доступ принадлежат исходному Channel.',65,610,1140,42,25);
 }else if(type==='actions'){
  const q=box(s,'queued\nзаявка создана',65,210,245,100),p=box(s,'processing\nбот принял',460,210,245,100),done=box(s,'confirmed / failed\nитог бота',900,210,305,100);
  arrow(s,q,p);arrow(s,p,done);
  const unknown=box(s,'unknown\nAwaiting confirmation',450,450,320,110,true),cancel=box(s,'cancelled\nпо правилам API',65,450,245,110);
  arrow(s,q,unknown,'bottom','left',true);arrow(s,p,unknown,'bottom','top',true);arrow(s,unknown,done,'right','bottom');
  arrow(s,q,cancel,'bottom','top');text(s,'Отзыв\nдо ACK',65,350,110,65,19);
  text(s,'Повторный GET проверяет ту же операцию. ACK не заменяет бизнес-результат.',65,610,1140,45,24);
 }
}
export async function build({presentation,input}){
 const all=JSON.parse(await fs.readFile(input.dataPath,'utf8'));
 const current=presentation.slides.items.length;
 if(current!==input.start)throw new Error(`Expected ${input.start} slides, found ${current}`);
 for(let i=input.start;i<Math.min(input.end,all.length);i++){
  const d=all[i],s=presentation.slides.add({width:1280,height:720});
  const dark=d.kind==='section';s.background.fill=dark?colors.ink:colors.paper;
  const titleColor=dark?colors.white:colors.ink;
  text(s,`MARKETOB  /  ${d.section.toUpperCase()}`,64,30,1120,28,17,dark?'#A8C8E0':colors.muted,true);
  text(s,d.title,64,dark?185:82,1150,dark?135:100,dark?58:44,titleColor,true);
  text(s,`${String(i+1).padStart(2,'0')} / ${all.length}     24.11.2026`,64,681,1120,25,16,dark?'#A8C8E0':colors.muted);
  if(d.kind==='section')text(s,d.body,68,370,1110,170,35,'#D7E7F3');
  else if(d.kind==='image'){
   if(d.portrait){
    s.images.add({path:path.join(input.imageDir,d.image),alt:d.title+' — настоящий Web-интерфейс на демонстрационных данных',fit:'contain',position:{left:735,top:170,width:440,height:485}});
    text(s,d.body.split('\n').join('\n\n'),65,215,600,350,30);
   }else{
    s.images.add({path:path.join(input.imageDir,d.image),alt:d.title+' — настоящий Web-интерфейс на демонстрационных данных',fit:'contain',position:{left:395,top:170,width:825,height:490}});
    text(s,d.body.split('\n').join('\n\n'),65,215,300,400,27);
   }
  }else if(d.kind==='table'){
   const cols=d.rows[0].length, widths=cols===3?[245,420,485]:Array(cols).fill(1150/cols);
   const t=s.tables.add({rows:d.rows.length,columns:cols,left:65,top:190,width:1150,height:445,columnWidths:widths,values:d.rows});
   for(let r=0;r<d.rows.length;r++)for(let c=0;c<cols;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?colors.ink:(r%2?colors.white:colors.pale);
    cell.text.style={fontFamily:'Arial',fontSize:22,color:r===0?colors.white:colors.ink,bold:r===0};
   }t.borders.assign({style:'solid',fill:colors.line,width:1});
   if(i===55)text(s,'Общий префикс всех маршрутов: /v1',65,648,1140,28,20);
  }else if(d.kind==='flow'){
   const nodes=d.nodes.map((n,k)=>{
    const node=box(s,n,65+k*300,270,250,145);
    if(n.split('\n').length>2)node.text.style={fontFamily:'Arial',fontSize:22,color:colors.ink,alignment:'center',verticalAlignment:'middle'};
    return node;
   });for(let k=0;k<nodes.length-1;k++)arrow(s,nodes[k],nodes[k+1]);
   text(s,d.body,65,480,1130,150,28);
  }else if(d.kind==='diagram')diagram(s,d.diagram);
  else if(d.kind==='stat'){
   text(s,d.stat,65,220,1110,150,112,colors.blue,true);
   text(s,d.body.split('\n').join('\n\n'),70,395,1130,245,29);
  }else{
   const lines=d.body.split('\n');const height=lines.length>4?76:92;
   lines.forEach((line,k)=>{text(s,String(k+1).padStart(2,'0'),65,200+k*height,65,60,28,colors.blue,true);text(s,line,155,200+k*height,1045,height-10,30);});
  }
  s.speakerNotes.text=d.notes+'\n\nИсточники в репозитории (срез 24.11.2026):\n'+d.sources.map(p=>p.startsWith('https://')?p:'https://github.com/Villentretermert/ProjectMarket/blob/'+(p.endsWith('ALPINE-ATTRIBUTION-2026-11-24.md')?'main':'11653f0a81f5911076ddedc473bbc60e63909d70')+'/'+p).join('\n');
 }
 return {slides:presentation.slides.items.length};
}
