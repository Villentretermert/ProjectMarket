// Review source: native editable system diagram/tables, actual UI screenshots and measured results.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const repo=process.cwd(),skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill)throw new Error('Set MARKETOB_PRESENTATIONS_SKILL and RUNTIME_PYTHON.');
const proof=JSON.parse(await fs.readFile(path.join(repo,'.local/pm022/acceptance.json'),'utf8'));
assert.equal(proof.taskAccepted,true,'Do not present PM-022 as complete before acceptance');
const load=JSON.parse(await fs.readFile(path.join(repo,'docs/task-results/assets/PM-022/L2.json'),'utf8'));
assert.equal(load.duration_seconds,1800);assert.equal(load.steady_accepted,30000);assert.equal(load.rendered,30000);
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const out=path.join(repo,'docs/reviews/G05'),build=path.join(repo,'.local/G05-build');
await fs.mkdir(out,{recursive:true});await fs.mkdir(build,{recursive:true});
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const c={bg:'#F3F6FB',ink:'#213247',muted:'#53677F',blue:'#2468BC',green:'#1E7659',amber:'#825414',line:'#D5DFEB'},font='Arial';
const ms=value=>Math.round(value).toLocaleString('ru-RU')+' мс';
const seconds=value=>(value/1000).toLocaleString('ru-RU',{maximumFractionDigits:2})+' с';
function text(s,value,x,y,w,h,size=28,bold=false,color=c.ink){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.insets=0;t.text.style={typeface:font,fontSize:size,bold,color};return t;
}
function slide(title,notes){
 const s=deck.slides.add();s.background.fill=c.bg;text(s,title,64,46,1152,92,44,true);
 text(s,deck.slides.items.length+' / 12',1130,675,86,25,18,false,c.muted);s.speakerNotes.text=notes;return s;
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
async function shot(s,file,x,y,w,h){
 const bytes=await fs.readFile(path.join(repo,'docs/task-results/assets',file));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Actual MarkeTOB Web acceptance with synthetic pilot data',fit:'contain',position:{left:x,top:y,width:w,height:h}});
}
{
 const s=slide('MarkeTOB / G05','Sources: task-results PM-017,018,021,022. Review after the twentieth completed pilot task. Android/cloud remain explicitly deferred.');
 text(s,'Обмен страницами\nи локальная эксплуатация',64,210,1152,165,60,true,c.blue);
 text(s,'20 из 24 задач пилота',64,428,1152,65,40);
 text(s,'PM-017, PM-018, PM-021, PM-022\n'+proof.date,64,565,1100,80,27,false,c.muted);
}
{
 const s=slide('Четыре завершённые задачи','Sources: four task result documents. Counts follow actual completions, not task numbers. PM-019/020 remain deferred and do not count toward completion.');
 table(s,[['Задача','Результат','Проверка'],['PM-017','Ссылка и код шаблона','Импорт с отдельными правами'],['PM-018','Обновления и Events','L1, отзыв доступа, reconnect'],['PM-021','Локальная Docker-поставка','HTTPS, backup, новая БД'],['PM-022','Метрики и пределы нагрузки','L2, burst, квоты и alerts']],[185,465,502],165,380);
 text(s,'Android и домашний виджет остаются отложенными.',64,594,1152,60,29,true,c.amber);
}
{
 const s=slide('Обмен оформлением','Source: docs/task-results/PM-017.md, import-preview.png. The screenshot is synthetic acceptance evidence. The share code is deliberately masked. Sharing carries immutable layout/source references; the importing account must independently have source rights.');
 text(s,'Share / Import template',64,170,380,75,32,true,c.blue);
 text(s,'Ссылка передаёт оформление\nи ссылки на источники.\n\nУ друга появляется\nнезависимая копия.\n\nЗакрытые данные требуют\nотдельного доступа.',64,278,380,300,27);
 await shot(s,'PM-017/import-preview.png',470,165,746,468);
 text(s,'Фактический Web. Код ссылки скрыт.',470,636,746,30,23,false,c.muted);
}
{
 const s=slide('Обновления в открытом приложении','Source: docs/task-results/PM-018.md, live-events.png, updates.py, web/live.js. Foreground polling with a two-second interval, scoped cursor, authorized snapshots and optional in-app toasts. Background OS push remains absent.');
 text(s,'Events выбираются\nдля каждого канала',64,170,395,90,32,true,c.blue);
 text(s,'Новости и изменения каталога\n\nСтатусы собственных заявок\n\nПри потере связи содержимое\nскрывается до пересинхронизации.\n\nФоновый push пока не готов.',64,299,395,330,27);
 await shot(s,'PM-018/live-events.png',495,154,721,500);
}
{
 const s=slide('Локальная поставка и восстановление','Source: PM-021 report and docker-recovered-window.png. API/worker/PostgreSQL/Caddy on Ubuntu WSL. Backup into a fresh database, exact migration compatibility and HTTP replay verified. Screenshot is a new synthetic demonstration created after restore, not evidence by itself of historic UI restoration.');
 text(s,'Web работает\nчерез Docker / WSL',64,168,395,95,32,true,c.blue);
 text(s,'Python API и worker\nPostgreSQL, локальный HTTPS\n\nBackup восстанавливается\nв новую БД.\n\nИсходная БД сохраняется\nдо проверки переключения.',64,298,395,310,27);
 await shot(s,'PM-021/docker-recovered-window.png',495,155,677,470);
 text(s,'Демонстрационный My Space после восстановления',495,640,721,32,22,false,c.muted);
}
{
 const s=slide('Результат полного L2','Source: docs/task-results/assets/PM-022/L2.json. 100 bot identities and 100 headless visible Edge contexts for 1800 seconds. 80% news/products <=4KiB,20% charts <=32KiB. Successful server processing measures ingest/read; action availability includes HTTP. Live uses receipt-to-DOM revision after rAF, not physical screen pixels. Shared Windows host, not cloud capacity.');
 const ingest=load.server.routes['POST /v1/bot/messages'],read=load.server.routes['GET /v1/channels/{slug}'];
 table(s,[['Метрика','p95','p99','Цель p95'],['Приём сервером',ms(ingest.p95_ms),ms(ingest.p99_ms),'≤500 мс'],['Чтение сервером',ms(read.p95_ms),ms(read.p99_ms),'≤500 мс'],['Данные на экране',seconds(load.live.p95_ms),seconds(load.live.p99_ms),'≤3 с'],['Заявка доступна боту',ms(load.action_available_http.p95_ms),ms(load.action_available_http.p99_ms),'≤3 с']],[440,220,220,272],163,360);
 text(s,'30 000 из 30 000 сообщений отображены',64,549,1152,55,32,true,c.green);
 text(s,'100 ботов, 100 клиентов, 1 000 сообщений/мин, 30 минут\nWindows / PostgreSQL18.6, loopback, общий компьютер',64,614,1152,60,24,false,c.muted);
}
{
 const s=slide('Всплеск и восстановление','Source: PM-022 L2.json and tests/test_operations.py. Burst uses open-loop offered load with bounded per-bot queues, stable message IDs and Retry-After. Intermediate burst DOM revisions may coalesce; accepted receipts and final snapshots are checked. Reconnect is a real offline browser context; restart includes API/worker and durable row counts, not a forced OS/database crash.');
 table(s,[['Проверка','Результат'],['Предложено за 60 секунд','3 000 сообщений'],['Принято за первую минуту',String(load.burst.accepted_during_minute)],['Принято после повторов',String(load.burst.accepted)+' из 3 000'],['Восстановление после минуты',load.burst.recovery_seconds.toFixed(1)+' с'],['Итоговые snapshots','100 из 100 клиентов'],['Reconnect',ms(load.reconnect_ms)]],[610,542],155,425);
 text(s,'После рестарта сохранены все подтверждённые квитанции.',64,616,1152,60,27,true,c.green);
}
{
 const s=slide('Эксплуатационные ограничения','Source: ADR-0015, OPERATIONS.md, migration011, maintenance.py, operations.py. Per-bot finite capacity is distinct from30-day retention. Count-based outbox guards have bounded in-flight overshoot. Alerts are local CLI JSON/exit status; no automatic outbound delivery or scheduler is installed.');
 table(s,[['Объект','Предел / поведение'],['История одного бота','256 MiB или 100 000 сообщений'],['Нерешённые заявки','1 000 на бота, затем 429'],['Текущие записи и tombstones','10 000 на бота'],['Доставленные уведомления','Час хранения, затем resync по floor'],['Диагностика','JSON-логи с ротацией, CLI alerts']],[460,692],156,399);
 text(s,'Заполненная история останавливает новый приём.\nПринятые данные сохраняют свой срок хранения.',64,591,1152,70,28,false,c.muted);
}
{
 const s=slide('Состояние системы','Source: implementation through PM-022 and roadmap. Green nodes implemented and tested locally. Amber Android/widget deferred and native acceptance incomplete. Privacy/export/deletion/release audit PM-023/024 remains not accepted. External Google/Firebase/iOS/Windows remain future scope. Diagram is native and editable.');
 const bots=node(s,'HTTP-боты\nPython SDK\nГотово',64,212,250,125,'#E4F3EC');
 const api=node(s,'Python API\nПрава и события\nГотово',414,212,300,125,'#E4F3EC');
 const web=node(s,'Web / My Space\nStudio, Share\nГотово',904,212,310,125,'#E4F3EC');
 const db=node(s,'PostgreSQL\nДанные и очереди\nГотово',414,442,300,125,'#E4F3EC');
 const worker=node(s,'Worker / CLI\nОчистка, метрики\nГотово локально',64,442,250,125,'#E4F3EC');
 node(s,'Android / widget\nОтложено\nНе проверено',904,442,310,125,'#FFF0D8');
 connect(s,bots,api);connect(s,api,web);connect(s,api,db,'bottom','top');connect(s,db,worker,'left','right');
 text(s,'Privacy-аудит и релизная приёмка ещё не выполнены.',64,615,1152,55,28,true,c.amber);
}
{
 const s=slide('Код и основные сущности','Sources: sharing.py, updates.py, database.py, ingestion.py, request_state.py, maintenance.py and migrations009–011. Table describes actual responsibilities. Canonical schemas remain the API source of truth.');
 table(s,[['Компонент','Сущность','Ответственность'],['sharing.py','template_shares','Immutable копия оформления'],['updates.py','change_outbox / delivery_state','Порядок доставки и resync'],['actions.py','action_requests / results','ACK, результат и идемпотентность'],['database.py','Primary / auxiliary pools','Короткие транзакции без starvation'],['maintenance.py','history_usage / worker_state','Очистка, ёмкость, heartbeat']],[270,420,462],155,420);
 text(s,'Snapshot, receipt и outbox записываются одной транзакцией.',64,613,1152,60,27,true,c.blue);
}
{
 const s=slide('Проверки и границы результата','Source: final PM-022 acceptance report and CI '+proof.ciUrl+'. Test counts are cumulative. L2 is synthetic and performed on a shared local host. No claim of device/store/cloud/background push readiness. All screenshots are actual prior acceptance using synthetic data.');
 text(s,proof.pythonTests+' Python-проверок\n47 браузерных сценариев\n4 успешных CI jobs',64,178,560,240,40,true,c.green);
 text(s,'Проверены квоты, noisy bot,\nзаполненная очередь, alerts,\nretention, replay и восстановление.',665,183,550,170,29);
 text(s,'Не проверены настоящий Android/виджет, Google/Firebase\nи облачный сервер. Privacy/release задачи остаются открытыми.\nMAU не означает число одновременных пользователей.',64,489,1152,145,29,false,c.muted);
}
{
 const s=slide('Оставшиеся задачи пилота','Source: roadmap/tasks019020023024 and explicit Android deferral. This is the proposed remaining sequence, not authorization to resume Android. Before next task ask at least10 separate questions. Web/API-only PM-023 preparation can be prioritized by owner while native gates remain open.');
 table(s,[['Задача','Зачем','Состояние'],['PM-019 Android','Проверить APK/AAB на телефоне','Отложено'],['PM-020 Widget','Проверить новости на home screen','Отложено'],['PM-023 Privacy','Доступ, удаление, export и аудит','Не начата'],['PM-024 Приёмка','Релиз-кандидат и передача владельцу','Не начата']],[300,590,262],165,350);
 text(s,'До возвращения к Android можно подготовить\nнезависимую часть проверки Web/API.',64,555,1152,90,31,true,c.blue);
}
const candidate=path.join(build,'candidate.pptx');await(await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(out,process.env.MARKETOB_DECK_NAME||'MarkeTOB-G05.pptx'),tables=[2,6,7,8,10,12];
const result=await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tables.flatMap(x=>['--require-native-table-slide',String(x)])],
 explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:tables,requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});console.log(JSON.stringify(result));
const verified=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const[i,s]of verified.slides.items.entries()){
 const png=await verified.export({slide:s,format:'png',scale:1});await fs.writeFile(path.join(build,'slide-'+(i+1)+'.png'),new Uint8Array(await png.arrayBuffer()));
}
console.log('Twelve final slide previews ready for inspection.');
