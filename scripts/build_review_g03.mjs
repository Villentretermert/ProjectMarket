// Local G03 evidence deck. Reuse the established presentation style and native tables/diagrams.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const repo=process.cwd(), skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill) throw new Error('Set MARKETOB_PRESENTATIONS_SKILL and supplied runtime paths.');
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const load=JSON.parse(await fs.readFile(path.join(repo,'docs/task-results/assets/PM-012/local-load.json'),'utf8'));
const faults=JSON.parse(await fs.readFile(path.join(repo,'docs/task-results/assets/PM-012/local-faults.json'),'utf8'));
if(load.result!=='PASS'||faults.result!=='PASS') throw new Error('Accepted evidence required.');
const out=path.join(repo,'docs/reviews/G03'),build=path.join(repo,'.local/G03-build');
await fs.mkdir(out,{recursive:true});await fs.mkdir(build,{recursive:true});
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const c={bg:'#F3F6FB',ink:'#213247',muted:'#53677F',blue:'#2468BC',green:'#1E7659',amber:'#825414',line:'#D5DFEB'};
const font='Arial';
function text(s,value,x,y,w,h,size=28,bold=false,color=c.ink){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.insets=0;t.text.style={typeface:font,fontSize:size,bold,color};return t;
}
function slide(title,notes){
 const s=deck.slides.add();s.background.fill=c.bg;
 text(s,title,64,46,1152,92,44,true);
 text(s,`${deck.slides.items.length} / 10`,1130,675,86,25,18,false,c.muted);
 s.speakerNotes.text=notes;return s;
}
function table(s,values,widths,y=165,h=400){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top:y,width:1152,height:h,columnWidths:widths,values});
 t.borders.assign({fill:c.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let col=0;col<values[0].length;col++){
  const cell=t.getCell(r,col);cell.fill=r===0?c.blue:'#FFFFFF';
  cell.text.style={typeface:font,fontSize:24,bold:r===0,color:r===0?'#FFFFFF':c.ink};
 }
 return t;
}
function node(s,label,x,y,w,h,fill){
 const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:c.line,width:1}});
 n.text=label;n.text.insets=14;n.text.style={typeface:font,fontSize:26,color:c.ink,alignment:'center',verticalAlignment:'middle'};return n;
}
function connect(s,a,b,from='right',to='left'){
 s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:c.muted,width:2},tail:{type:'triangle',width:'med',length:'med'}});
}
{
 const s=slide('MarkeTOB / G03','Источники: отчёты PM-009–012. Локальный пилот без Google/Firebase/облака. UI English, обсуждение Russian.');
 text(s,'Каналы, заявки и боты',64,232,1152,100,60,true,c.blue);
 text(s,'Работающее ядро\nи проверка восстановления',64,360,1100,125,40);
 text(s,'PM-009–012\n22 октября 2026',64,566,900,80,26,false,c.muted);
}
{
 const s=slide('Четыре завершённые задачи','Источники: docs/task-results/PM-009.md, PM-010.md, PM-011.md, PM-012.md. CI ссылки и точные commits в отчётах.');
 table(s,[['Задача','Компонент','Фактический результат'],['PM-009','Каналы и публикация','Версии, откат, живые данные'],['PM-010','Заявки и статусы','GET, ACK, result и дедупликация'],['PM-011','Python SDK и два бота','Каталог / RSS, процессы и Docker'],['PM-012','Проверка ядра','Сбои, восстановление, нагрузка']],[175,380,597],166,380);
 text(s,'12 из 24 задач пилота завершены. Следующий блок подключает Web.',64,585,1135,65,28,true,c.green);
}
{
 const s=slide('Система и готовность','Зелёный: готово. Синий: частично. Серый: не сделано/отложено. Источники: compose.yaml, compose.bots.yaml, docs/ROADMAP.md. UI link is planned. Outbox foreground delivery remains PM-018.');
 text(s,'Готово: зелёный     Частично: синий     Не сделано: серый',64,144,1152,40,25,false,c.muted);
 const bots=node(s,'Python SDK\nКаталог / RSS\nОтдельные ключи',64,240,300,150,'#DFF1E8');
 const api=node(s,'FastAPI\nКаналы / доступ\nЗаявки / статусы',490,240,300,150,'#DFF1E8');
 const web=node(s,'Web\nМакет готов\nAPI ещё не подключён',916,240,300,150,'#EAF2FD');
 const worker=node(s,'Maintenance\nRetention / timeout\nГотово',64,475,300,135,'#DFF1E8');
 const db=node(s,'PostgreSQL\nSnapshot / receipt\nRequest / outbox',490,475,300,135,'#DFF1E8');
 const android=node(s,'Android / widget\nСборка и устройство\nотложены',916,475,300,135,'#E5EAF0');
 connect(s,bots,api);connect(s,api,web);connect(s,api,db,'bottom','top');connect(s,worker,db);connect(s,web,android,'bottom','top');
 text(s,'HTTP',383,272,90,35,23,false,c.muted);text(s,'план',815,272,90,35,23,false,c.muted);
}
{
 const s=slide('Оформление и данные канала','Источники: channels.py, migrations/004_channels.sql, docs/api/CHANNELS.md. Layout versions are immutable, rollback creates new version; latest data is not reverted. Sources must be compatible and authorized.');
 const owner=node(s,'Владелец\nЧерновик оформления',64,215,300,120,'#EAF2FD');
 const published=node(s,'Опубликованная\nверсия оформления',490,215,300,120,'#DFF1E8');
 const consumer=node(s,'Snapshot клиента\nТолько разрешённые\nблоки и данные',916,315,300,160,'#DFF1E8');
 const bot=node(s,'Бот\nНовая revision',64,455,300,120,'#EAF2FD');
 const latest=node(s,'Актуальные\nданные источников',490,455,300,120,'#DFF1E8');
 connect(s,owner,published);connect(s,bot,latest);connect(s,published,consumer);connect(s,latest,consumer);
 text(s,'Publish',382,235,100,35,23,false,c.muted);text(s,'POST',385,475,90,35,23,false,c.muted);
 text(s,'Откат оформления сохраняет новые данные. По умолчанию Selected users.',64,620,1135,42,26,true,c.blue);
}
{
 const s=slide('Request purchase и результат','Источники: actions.py, request_state.py, marketob_bots/catalog.py/state.py. Quantity=1, no cart/payment. ACK after durable inbox. Real external services must implement idempotency.');
 const rows=[['1','Клиент отправляет заявку','Сервер проверяет доступ, наличие товара и revision.'],['2','Бот читает событие','Локальный журнал сохраняет событие до ACK.'],['3','Бот выполняет операцию','Demo ledger хранит один результат на request ID.'],['4','Клиент получает статус','Confirmed или Failed. ACK сам по себе успеха не означает.']];
 rows.forEach((r,i)=>{const y=165+i*116;text(s,r[0],64,y,70,55,40,true,c.blue);text(s,r[1],164,y,1000,44,31,true);text(s,r[2],164,y+49,1035,58,27);});
 text(s,'Демонстрационные заявки. Оплаты, корзины и отгрузки нет.',64,645,1140,30,23,false,c.muted);
}
{
 const s=slide('Восстановление после сбоев','Источник: docs/task-results/assets/PM-012/local-faults.json. Four os._exit(91) process crashes, API restarts, worker restart. HTTP outbox trigger failure returns expected 500 and rolls back record+receipt. CI also stops DB and restores API.');
 table(s,[['Точка сбоя','После перезапуска','Результат'],['Перед ACK / после ACK','Заявка завершается один раз','PASS'],['Перед result / после result','Сохранённый результат повторяется','PASS'],['Отказ записи outbox','Данные и receipt откатываются','PASS'],['Maintenance остановлен','Незавершённая заявка сохраняется','PASS'],['Восемь одинаковых POST','Одна квитанция и одно событие','PASS']],[360,560,232],156,420);
 text(s,'117 автоматических тестов и проверки реальных HTTP-процессов прошли.',64,612,1140,54,27,true,c.green);
}
{
 const s=slide('Локальный поток 1 000 сообщений/мин','Источник: local-load.json. 3000 successes in180.139s,100bots,10readers,16threads. i7-11700K8cores16threads,~64GiB RAM,SATA KingstonSSD,Windows11,Python3.14.7,PG18.6. 40%news40%products20%chart,3260–24557bytes. HTTP+SDK timing, not server-only or UI. Full30minL2 remains PM022.');
 text(s,String(load.scheduled)+' / '+String(load.scheduled),64,166,570,95,64,true,c.blue);
 text(s,'принятых сообщений за 3 минуты',64,265,570,65,28);
 text(s,Math.round(load.successful_ingest_latency.p95_ms)+' мс',710,166,500,95,64,true,c.blue);
 text(s,'p95 до квитанции приёма',710,265,500,65,28);
 table(s,[['Показатель','Результат'],['Боты / читающие API-сессии','100 / 10'],['Чтение p95 / успешные чтения','254 мс / 1 549'],['После рестарта receipt / outbox','3 000 / 3 000']],[650,502],370,215);
 text(s,'HTTP + SDK на loopback. Полный L2 и скорость UI ещё не проверены.',64,620,1140,45,25,false,c.amber);
}
{
 const s=slide('Код и сущности','Источники: channels.py, actions.py, request_state.py, marketob_sdk/client.py, marketob_bots/state.py, scripts/backend_lab.py. More detailed code walkthrough in G03 README.');
 table(s,[['Компонент','За что отвечает','Основные сущности'],['channels.py','Черновик, публикация, откат','Channel, Version, Source'],['actions.py','Создание, GET, ACK, result','Request, Event, Result'],['request_state.py','Отзыв, unknown, retention','Request, Outbox'],['SDK / bot journals','HTTP и восстановление','Message, Inbox, DemoEffect'],['backend_lab / load','Изоляция и измерения','Test schema, process, receipt']],[330,400,422],156,420);
 text(s,'API, SDK, боты и стенд написаны на Python. Web использует HTML/CSS/JS.',64,618,1140,48,26,false,c.muted);
}
{
 const s=slide('Данные ботов и интерфейс','Источники: catalog.py/news.py, actual smoke_bots reports. Image: docs/task-results/assets/PM-003/studio.png, existing synthetic UI prototype. The current Web prototype is not connected to the implemented backend.');
 text(s,'Готовые данные через API',64,164,545,50,31,true);
 text(s,'Soap / Rice: confirmed\nPaper towels: failed\nMilk: out of stock\n\nRSS: заголовок, дата, ссылка\nГрафик: окно публикаций',64,244,555,270,28);
 text(s,'Подключение интерфейса\nначинается в PM-013.',64,560,555,80,30,true,c.blue);
 const bytes=await fs.readFile(path.join(repo,'docs/task-results/assets/PM-003/studio.png'));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Existing PM-003 Studio prototype with synthetic data; API not connected',fit:'contain',position:{left:650,top:180,width:566,height:380}});
 text(s,'Существующий макет PM-003',650,584,566,36,24,false,c.muted);
}
{
 const s=slide('Следующие четыре задачи','Источники: docs/ROADMAP.md, G02 answers. Team roles required PM014 before external pilot. Exact matrix is asked at G03. PM013 begins only after G03 answers or explicit authorization with assumptions.');
 table(s,[['Порядок','Задача','Зачем'],['PM-013','Рабочий Web-клиент','Показать данные и статусы в UI'],['PM-014','Studio и командные роли','Подключать ботов без терминала'],['PM-015','Каналы и избранное','Сохранять источники как контакты'],['PM-016','My Space','Собирать блоки разных каналов']],[175,470,507],166,380);
 text(s,'Перед продолжением: роли команды, поведение UI и 13 отдельных вопросов.',64,593,1140,68,30,true,c.blue);
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(out,process.env.MARKETOB_DECK_NAME||'MarkeTOB-G03.pptx');
const tables=[2,6,7,8,10];
const result=await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,
 pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(x=>['--require-native-table-slide',String(x)])],
 explicitTotalSlideCount:10,requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify(result));
const verified=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const [i,s] of verified.slides.items.entries()){
 const png=await verified.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log('Ten final slide previews ready for inspection.');
