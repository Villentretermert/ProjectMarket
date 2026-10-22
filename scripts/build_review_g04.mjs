// Local review deck from actual UI evidence; native editable tables and system diagram.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const repo=process.cwd(),skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill)throw new Error('Set MARKETOB_PRESENTATIONS_SKILL and RUNTIME_PYTHON.');
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const out=path.join(repo,'docs/reviews/G04'),build=path.join(repo,'.local/G04-build');
await fs.mkdir(out,{recursive:true});await fs.mkdir(build,{recursive:true});
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const c={bg:'#F3F6FB',ink:'#213247',muted:'#53677F',blue:'#2468BC',green:'#1E7659',amber:'#825414',line:'#D5DFEB'},font='Arial';
function text(s,value,x,y,w,h,size=28,bold=false,color=c.ink){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.insets=0;t.text.style={typeface:font,fontSize:size,bold,color};return t;
}
function slide(title,notes){
 const s=deck.slides.add();s.background.fill=c.bg;text(s,title,64,46,1152,92,44,true);
 text(s,`${deck.slides.items.length} / 10`,1130,675,86,25,18,false,c.muted);s.speakerNotes.text=notes;return s;
}
function table(s,values,widths,y=165,h=400){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top:y,width:1152,height:h,columnWidths:widths,values});
 t.borders.assign({fill:c.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let col=0;col<values[0].length;col++){
  const cell=t.getCell(r,col);cell.fill=r===0?c.blue:'#FFFFFF';cell.text.style={typeface:font,fontSize:24,bold:r===0,color:r===0?'#FFFFFF':c.ink};
 }return t;
}
function node(s,label,x,y,w,h,fill){
 const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:c.line,width:1}});
 n.text=label;n.text.insets=12;n.text.style={typeface:font,fontSize:25,color:c.ink,alignment:'center',verticalAlignment:'middle'};return n;
}
function connect(s,a,b,from='right',to='left'){
 s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:c.muted,width:2},tail:{type:'triangle',width:'med',length:'med'}});
}
async function shot(s,file,x,y,w,h,crop){
 const bytes=await fs.readFile(path.join(repo,'docs/task-results/assets',file));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Actual MarkeTOB Web acceptance, synthetic pilot data',fit:'contain',...(crop?{crop}:{}),position:{left:x,top:y,width:w,height:h}});
}
{
 const s=slide('MarkeTOB / G04','Источники: docs/task-results/PM-013.md–PM-016.md. Локальный пилот; данные экранов синтетические. Android и облако отложены владельцем.');
 text(s,'Web, Studio и My Space',64,225,1152,100,60,true,c.blue);
 text(s,'Личный интерфейс\nиз каналов разных ботов',64,354,1100,125,40);
 text(s,'PM-013–016 · 16 из 24 задач пилота\n22 октября 2026',64,565,1100,80,26,false,c.muted);
}
{
 const s=slide('Рабочий Web-клиент','Источник: PM-013 report and actual channel-desktop screenshot. Local session, CSRF, permissions, typed rendering, confirmation before purchase, no payment. Screenshot shows synthetic goods.');
 text(s,'Локальный вход\nи реальные данные API',64,170,420,95,32,true,c.blue);
 text(s,'Новости, товары и графики\n\nRequest purchase:\nподтверждение перед\nотправкой одной единицы\n\nAwaiting confirmation:\nпроверка прежней заявки',64,296,420,290,27);
 await shot(s,'PM-013/desktop-catalog.png',520,160,696,460);
 text(s,'Фактический Web · демонстрационный каталог',520,630,696,34,22,false,c.muted);
}
{
 const s=slide('B2B Studio','Источник: PM-014 report, studio-team screenshot; teams.py, studio.js. Owner/Admin can register/rotate/revoke credentials. API secrets shown only upon creation, never in evidence screenshots. RSS defaults BBC World; test screenshot synthetic.');
 text(s,'Бот → блоки → публикация',64,164,1152,50,32,true,c.blue);
 await shot(s,'PM-014/studio-team.png',64,235,740,388);
 text(s,'Подключение HTTP-бота\nс отдельным ключом\n\nDraft, Publish, Rollback\n\nSelected users\nпо умолчанию\n\nКоманда по username',850,232,366,365,27);
 text(s,'Работающая команда в Studio',64,635,740,30,22,false,c.muted);
}
{
 const s=slide('Роли команды','Источники: ADR-0009, docs/api/TEAMS.md, tests/test_teams.py. G03 explicitly approved three roles/editor publication and keys owner/admin. Only-owner team management and immutable owner are declared engineering details.');
 table(s,[['Действие','Owner','Admin','Editor'],['Читать / редактировать блоки','Да','Да','Да'],['Публиковать / откатывать','Да','Да','Да'],['Боты и ключи','Да','Да','Нет'],['Audience и grants','Да','Да','Нет'],['Изменять команду','Да','Нет','Нет']],[585,189,189,189],162,425);
 text(s,'Права проверяет сервер. Один Owner; передача владения пока не реализована.',64,617,1152,55,26,false,c.muted);
}
{
 const s=slide('Каналы и избранное','Источник: PM-015 report, favorites-desktop screenshot; favorites.py, favorites.js. Limit100; New compares seen template/data revisions, not unread article count. Snapshot after revoke has no metadata.');
 await shot(s,'PM-015/favorites-desktop.png',64,165,740,450);
 text(s,'Открыть ссылку\nи сохранить канал\n\nРучной порядок\nмежду сессиями\n\nNew после новых данных\nили публикации\n\nНедоступный канал\nне раскрывает название',850,173,366,420,27);
 text(s,'Фактический экран · данные для приёмки',64,635,740,30,22,false,c.muted);
}
{
 const s=slide('My Space','Источники: PM-016 report, space-desktop screenshot (top/source editor cropped as indicated), personal_pages.py, space.js. 20pages/50blocks/20undo. Two contexts restore independent layout; source access is independently checked; buy uses original channel.');
 // Native crop keeps the actual source image intact in the editable file.
 await shot(s,'PM-016/space-desktop.png',64,165,740,470,{left:0.2,top:0.12,right:0.02,bottom:0.42});
 text(s,'Блоки разных каналов\nв одной личной странице\n\nВид, плотность, порядок\n\nАвтосохранение и Undo\n\nКонфликт двух клиентов\nбез перезаписи чужой\nправки',850,173,366,420,27);
 text(s,'Фрагмент фактического редактора · источники независимы',64,640,1152,30,22,false,c.muted);
}
{
 const s=slide('Код и сущности','Источники: apps/api/src/marketob_api/{teams,favorites,personal_pages}.py and web/{app,studio,favorites,space,render,actions}.js. Migrations006teams007favorites008personalpages. API/SDK/bots Python; webJS justified ADR0001. Details and links in G04 README.');
 table(s,[['Компонент','Ответственность','Сущности'],['Python: teams / access','Текущие права команды','Workspace / Membership'],['Python: favorites','Порядок и отметки New','Favorite / Revision'],['Python: personal_pages','Layout и разрешённые данные','Page / BlockReference'],['JS: Studio / Space','Редакторы и автосохранение','Draft / Saved version'],['JS: render / actions','Виды блоков и заявки','Record / ActionRequest']],[365,430,357],160,420);
 text(s,'Layout хранит ссылки. Данные и права остаются у исходного канала.',64,615,1152,52,28,true,c.blue);
}
{
 const s=slide('Система и готовность','Источники: compose.yaml, migrations001–008, apps/api/web and docs/ROADMAP.md. Green implemented, blue partial, grey not built/deferred. Arrow Web→API means HTTP; API↔DB conceptual transaction path. Outbox delivery PM018; backups PM021. Native editable diagram.');
 text(s,'Готово: зелёный     Частично: синий     Не сделано: серый',64,143,1152,40,25,false,c.muted);
 const bots=node(s,'Python-боты\nКаталог / RSS\nHTTP и свои ключи',64,232,300,145,'#DFF1E8');
 const api=node(s,'FastAPI\nДоступ / данные\nЗаявки / layouts',490,232,300,145,'#DFF1E8');
 const web=node(s,'Web\nStudio / Channels\nMy Space',916,232,300,145,'#DFF1E8');
 const worker=node(s,'Outbox / worker\nХранение готово\nДоставка: PM-018',64,470,300,145,'#EAF2FD');
 const db=node(s,'PostgreSQL\nОсновные сущности\nBackup: PM-021',490,470,300,145,'#EAF2FD');
 node(s,'Android / widget\nGoogle / cloud\nОтложены',916,470,300,145,'#E5EAF0');
 connect(s,bots,api);connect(s,web,api,'left','right');connect(s,api,db,'bottom','top');connect(s,db,worker,'left','right');
 text(s,'HTTP',385,275,90,35,23,false,c.muted);text(s,'HTTP',813,275,90,35,23,false,c.muted);
}
{
 const s=slide('Проверки четырёх задач','Источники: task-results/PM013–016 and CI39846617703,39853394634,39854053654,39858054474. Counts cumulative, not additive. Python70 unit plus PG48/55/60/67. Browser14/24/29/36, Edge local and Chromium CI. Local137 all pass; actual finalCI must be recorded before acceptance.');
 table(s,[['Приёмка','Python + PostgreSQL','Браузерные сценарии'],['PM-013','118 PASS','14 PASS'],['PM-014','125 PASS','24 PASS'],['PM-015','130 PASS','29 PASS'],['PM-016','137 PASS','36 PASS']],[260,450,442],164,345);
 text(s,'Накопительные наборы: числа не складываются.',64,539,1152,45,27,true,c.green);
 text(s,'Edge локально, Chromium и Docker в CI.\n360px проверено в браузере; настоящий Android ещё не проверен.',64,598,1152,65,25,false,c.muted);
}
{
 const s=slide('Следующий этап','Источники: roadmap/tasks017–020, accepted Android/cloud deferral. Do not beginPM017 until G04 replies/explicit instruction. Android license/build/USB remains deferred; proposed order is not permission. PM021–024 later operations/load/privacy/release, iOS/Windows later.');
 table(s,[['Порядок','Задача','Зачем'],['PM-017','Обмен ссылкой и кодом','Передавать оформление друзьям'],['PM-018','Обновления и события','Видеть изменения за секунды'],['PM-019','Android APK/AAB','Проверить настоящий клиент'],['PM-020','Домашний news widget','Читать новости с экрана телефона']],[175,470,507],164,350);
 text(s,'Android остаётся отложенным до вашего решения.',64,548,1152,45,29,true,c.amber);
 text(s,'Далее: Docker-поставка, backup, нагрузка и релизная приёмка.\nПеред продолжением — отдельные вопросы G04.',64,611,1152,65,26,false,c.muted);
}
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(out,process.env.MARKETOB_DECK_NAME||'MarkeTOB-G04.pptx'),tables=[4,7,9,10];
const result=await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(x=>['--require-native-table-slide',String(x)])],
 explicitTotalSlideCount:10,requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});console.log(JSON.stringify(result));
const verified=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const[i,s]of verified.slides.items.entries()){
 const png=await verified.export({slide:s,format:'png',scale:1});await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log('Ten final slide previews ready for inspection.');
