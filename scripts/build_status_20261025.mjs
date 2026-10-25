// Status snapshot from committed evidence. Build files stay private under .local.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const repo=process.cwd(),skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill||!process.env.RUNTIME_PYTHON)throw new Error('Set presentation skill and bundled Python paths.');
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const out=path.join(repo,'docs/reviews/STATUS-2026-10-25');
const build=path.join(repo,'.local/status-2026-10-25');
await fs.mkdir(out,{recursive:true});await fs.mkdir(build,{recursive:true});
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const font='Arial',N=13;
const c={bg:'#FFFFFF',ink:'#122D48',blue:'#1768BC',muted:'#536A80',line:'#D5E0EB',green:'#13745A',amber:'#946013',ready:'#E7F4EF',partial:'#FFF1D9',later:'#EDF1F6'};
const base='https://github.com/Villentretermert/ProjectMarket/blob/37543ee/';
const sources=[];
function text(s,value,x,y,w,h,size=28,bold=false,color=c.ink){
 const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.insets=0;t.text.style={typeface:font,fontSize:size,bold,color};return t;
}
function slide(title,refs,notes=''){
 const s=deck.slides.add();s.background.fill=c.bg;
 const index=deck.slides.items.length;
 text(s,title,64,46,1152,102,44,true);
 text(s,'MarkeTOB  /  25 октября 2026',64,677,850,24,18,false,c.muted);
 text(s,`${index} / ${N}`,1130,677,86,24,18,false,c.muted);
 const urls=refs.map(p=>p.startsWith('https://')?p:base+p);
 s.speakerNotes.text=`${notes}\n\nИсточники:\n${urls.join('\n')}`;
 sources.push({slide:index,title,sources:urls,notes});return s;
}
function table(s,values,widths,y=172,h=394,size=25){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top:y,width:1152,height:h,columnWidths:widths,values});
 t.borders.assign({fill:c.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let col=0;col<values[0].length;col++){
  const cell=t.getCell(r,col);cell.fill=r===0?c.ink:'#FFFFFF';
  cell.text.style={typeface:font,fontSize:size,bold:r===0,color:r===0?'#FFFFFF':c.ink};
 }return t;
}
function node(s,label,x,y,w,h,fill=c.ready){
 const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:c.line,width:1}});
 n.text=label;n.text.insets=12;n.text.style={typeface:font,fontSize:26,color:c.ink,alignment:'center',verticalAlignment:'middle'};return n;
}
function connect(s,a,b,from='right',to='left'){
 s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:c.muted,width:2},tail:{type:'triangle',width:'med',length:'med'}});
}
async function shot(s,file,x,y,w,h,crop){
 const bytes=await fs.readFile(path.join(repo,file));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Фактический экран MarkeTOB, демонстрационные данные. '+file,fit:'contain',...(crop?{crop}:{}),position:{left:x,top:y,width:w,height:h}});
}
{
 const s=slide('MarkeTOB',['docs/STATUS.md','docs/ROADMAP.md'],'Дополнительный обзор по запросу владельца. Не закрывает G05, не меняет счётчик задач. Последние CI, аудит и установленная поставка проверены 24 октября.');
 text(s,'Текущий статус',64,210,1152,96,72,true,c.blue);
 text(s,'Один интерфейс для каталогов,\nновостей и действий через ботов',64,335,1110,112,38);
 text(s,'Локальный Web-пилот',64,515,1000,48,32,true);
 text(s,'25 октября 2026\nДоказательства проверок по состоянию на 24 октября',64,579,1100,66,23,false,c.muted);
}
{
 const s=slide('Готовность пилота',['docs/STATUS.md','docs/ROADMAP.md','docs/reviews/G05.md'],'19/24 — счётчик полностью принятых PM-задач, не оценка доли трудозатрат. Завершены PM-001–018 и PM-021. После G04 принято 3 задачи из 4.');
 text(s,'19 / 24',64,175,450,130,104,true,c.blue);
 text(s,'задач пилота принято',68,320,420,86,32,true);
 text(s,'Это счётчик задач.\nОн не оценивает объём\nоставшейся работы.',68,446,410,128,26,false,c.muted);
 text(s,'Работает',552,176,650,44,31,true,c.green);
 text(s,'Web, B2B Studio, боты, My Space,\nобмен страницами и Docker-поставка.',552,226,650,88,29);
 text(s,'Частично готово',552,338,650,44,31,true,c.amber);
 text(s,'Нагрузочная приёмка, безопасность\nрелиза и передача владельцу.',552,388,650,88,29);
 text(s,'Отложено владельцем',552,500,650,44,31,true,c.muted);
 text(s,'Android, домашний виджет,\nGoogle/Firebase и облако.',552,550,650,86,29);
}
{
 const file='docs/task-results/assets/PM-016/space-preview.png';
 const s=slide('Личная витрина B2C',[file,'docs/task-results/PM-016.md','docs/task-results/PM-010.md'],'Фрагмент реального экрана приёмки PM-016. Синтетические товар, новость и заявка. Снимок этапа PM-016, не новая проверка 25 октября. Заявка не списывает деньги.');
 await shot(s,file,48,163,800,470,{left:0.194,top:0.23,right:0.018,bottom:0.375});
 text(s,'My Space',886,177,330,44,32,true,c.blue);
 text(s,'Блоки разных каналов\nв одной странице.',886,233,330,90,28);
 text(s,'Порядок, оформление\nи тип визуализации.\nАвтосохранение и Undo.',886,343,330,132,28);
 text(s,'Request purchase\nотправляет заявку\nи показывает ответ.',886,495,330,130,28);
 text(s,'Фактический экран PM-016. Демонстрационные данные, без оплаты.',64,643,1152,25,18,false,c.muted);
}
{
 const s=slide('B2B Studio и подключение ботов',['docs/task-results/PM-014.md','docs/adr/0009-workspace-roles.md','docs/adr/0017-personal-data-and-transfer.md','docs/setup/PILOT_BOTS.md'],'Решение D46 добавило передачу владения активному Admin с подтверждением паролем. Ограничения прежних снимков PM-014 об отсутствии передачи владения больше не действуют.');
 table(s,[['Роль','Доступные действия'],['Owner','Команда, передача владения и все настройки'],['Admin','Боты, ключи, доступ к каналам и публикация'],['Editor','Оформление, публикация и откат страниц']],[240,912],168,300,28);
 text(s,'У каждого бота свой ключ',64,501,560,45,31,true,c.blue);
 text(s,'Регистрация, замена и отзыв ключей.\nPython SDK и единый HTTP-контракт.',64,554,560,83,27);
 text(s,'Оформление отдельно от данных',670,501,546,45,31,true,c.blue);
 text(s,'Public или Selected users.\nНовые данные видны после приёма.',670,554,546,83,27);
}
{
 const s=slide('Обмен страницами и обновления',['docs/task-results/PM-017.md','docs/task-results/PM-018.md','docs/adr/0012-template-sharing.md','docs/adr/0013-live-updates.md'],'Обмен реализован кодом неизменяемого серверного шаблона. Доступ к каждому источнику проверяется заново. Срок по умолчанию 30 дней. Получателю нужны аккаунт и доступ к тому же серверу. Polling 2 секунды в открытом Web.');
 const a=node(s,'Моя страница\nОформление и ссылки',64,180,300,108);
 const b=node(s,'Ссылка или код\nСрок и отзыв',490,180,300,108);
 const d=node(s,'Независимая копия\nПроверка доступа',916,180,300,108);
 connect(s,a,b);connect(s,b,d);
 text(s,'Права на закрытые данные сохраняются у источника',64,333,1152,54,32,true,c.blue);
 text(s,'Друг получает собственную копию оформления.\nНедоступный источник остаётся скрытым.',64,399,1152,88,29);
 text(s,'Открытый Web проверяет изменения каждые 2 секунды.\nEvents показывает выбранные события внутри приложения.',64,518,1152,88,29);
 text(s,'Фоновые push-уведомления и Android-виджет пока не реализованы.',64,630,1152,34,24,false,c.muted);
}
{
 const file='docs/task-results/assets/PM-023/dependencies/deployed-privacy.png';
 const s=slide('Личные данные и удаление аккаунта',[file,'docs/task-results/PM-023-account-privacy.md','docs/adr/0017-personal-data-and-transfer.md'],'Фактический опубликованный снимок проверки установленного локального пилота, демонстрационный аккаунт. В экспорт входят профиль, Favorites, My Space, свои заявки и Events. Ключи ботов, чужие данные и содержимое источников исключены.');
 await shot(s,file,48,170,755,459,{left:0.194,top:0.22,right:0.025,bottom:0.04});
 text(s,'Экспорт JSON',851,178,365,44,31,true,c.blue);
 text(s,'Профиль, избранное,\nMy Space, свои заявки\nи настройки Events.',851,230,365,125,27);
 text(s,'Удаление',851,388,365,44,31,true,c.blue);
 text(s,'Сначала передача\nworkspace новому Owner.\nЗатем пароль и DELETE.',851,440,365,129,27);
 text(s,'Внешние копии и резервные копии оператора удаление аккаунта не стирает.',64,639,1152,29,22,false,c.muted);
}
{
 const s=slide('Система локального пилота',['docs/adr/0014-local-delivery.md','docs/adr/0013-live-updates.md','docs/task-results/PM-023-dependencies.md','docs/ROADMAP.md'],'Редактируемая схема. Зелёные компоненты реализованы и проверены в локальном составе. Эксплуатационная и релизная приёмка частичная. Android/widget/cloud не реализованы либо отложены. Caddy обслуживает локальный HTTPS. Каталог/RSS запускаются отдельно и используют тот же шлюз.');
 const w=node(s,'Web\nEnglish UI',64,174,210,108);
 const p=node(s,'Caddy\nHTTPS',340,174,210,108);
 const api=node(s,'Python API\nПрава и Bot API',616,174,250,108);
 const db=node(s,'PostgreSQL\nДанные и очередь',932,174,284,108);
 connect(s,w,p);connect(s,p,api);connect(s,api,db);
 const bot=node(s,'Каталог / RSS\nPython SDK',616,358,250,110);
 const worker=node(s,'Maintenance\nОчистка и доставка',932,358,284,110);
 connect(s,bot,api,'top','bottom');connect(s,worker,db,'top','bottom');
 node(s,'Android / виджет / облако\nОтложено, не готово',64,358,486,110,c.later);
 node(s,'Полная нагрузочная и релизная приёмка: частично готово',64,536,1152,72,c.partial);
 text(s,'Зелёный: готово в локальном составе',64,636,610,28,23,false,c.green);
 text(s,'Серый: не сделано / отложено',720,636,496,28,23,false,c.muted);
}
{
 const s=slide('Основные компоненты и сущности',['apps/api/src/marketob_api/identity.py','apps/api/src/marketob_api/ingestion.py','apps/api/src/marketob_api/actions.py','apps/api/src/marketob_api/personal_pages.py','apps/api/src/marketob_api/privacy.py','apps/api/src/marketob_api/web/space.js'],'Файлы backend находятся в apps/api/src/marketob_api. Имена сущностей на слайде описывают предметную область, а не обещают буквальные названия ORM-классов. Backend, схемы, SDK и боты написаны на Python. Web runtime использует JavaScript/CSS.');
 table(s,[['Компоненты Python','Сущности','Ответственность'],['identity.py, teams.py','User, Workspace, роль','Сессии и границы доступа'],['ingestion.py, channels.py','Bot, Message, Snapshot','Приём данных и витрина'],['actions.py, request_state.py','Request, Event, Result','Заявка и ответ бота'],['personal_pages.py, sharing.py','Страница и шаблон','Композиция и обмен'],['privacy.py, access_changes.py','Экспорт, удаление, resync','Личные данные и отзыв']],[435,320,397],170,426,24);
 text(s,'Python: backend, контракты, SDK, боты.  JavaScript/CSS: интерактивный Web.',64,630,1152,36,24,false,c.muted);
}
{
 const s=slide('Отзыв доступа при заполненной очереди',['apps/api/src/marketob_api/access_changes.py','docs/task-results/PM-023-queue-fix.md','docs/adr/0016-permission-invalidation.md'],'SQL из invalidate_access, переносы и пробелы адаптированы для чтения. Изменение прав и общего маркера проходит атомарно. Клиенты получают resync и заново проверяют источники. Это устранило зависимость от количества свободных мест change_outbox. Полный L2 остаётся отложенным.');
 text(s,'access_changes.py / invalidate_access()',64,166,1152,43,27,true,c.blue);
 text(s,'UPDATE delivery_state\nSET watermark = watermark + 1, retention_floor = watermark + 1',64,226,1152,95,29);
 text(s,'1',64,363,60,50,34,true,c.blue);
 text(s,'Права и маркер меняются одной транзакцией.',134,369,1082,46,30);
 text(s,'2',64,441,60,50,34,true,c.blue);
 text(s,'Клиент перечитывает разрешённые snapshots.',134,447,1082,46,30);
 text(s,'3',64,519,60,50,34,true,c.blue);
 text(s,'Отзыв работает и при полной очереди уведомлений.',134,525,1082,46,30);
 text(s,'Общий resync добавляет чтения. Его поведение под полной нагрузкой ещё проверим.',64,628,1152,36,24,false,c.muted);
}
{
 const s=slide('Проверки и установленная поставка',['docs/task-results/assets/PM-023/dependencies/ci-results.json','docs/task-results/assets/PM-023/dependencies/local-delivery.json','docs/task-results/assets/PM-023/dependencies/deployed-browser.json','https://github.com/Villentretermert/ProjectMarket/actions/runs/40128462069'],'CI 40128462069 на runtime commit 9afe3ec: все 4 jobs PASS. 90 unit +110 integration =200 разных Python tests. Повтор unit на Windows/Ubuntu не суммируется. 54 Chromium scenarios. Локальный backup/restore между PostgreSQL18.4/18.6 сверил 29 таблиц и10 sequences. Проверки выполнены 24 октября.');
 text(s,'200',64,174,350,112,88,true,c.blue);
 text(s,'Python-тестов',64,296,350,46,30,true);
 text(s,'90 unit и 110 integration',64,352,350,71,25,false,c.muted);
 text(s,'54',480,174,350,112,88,true,c.blue);
 text(s,'сценария Chromium',480,296,350,46,30,true);
 text(s,'Все 4 задания CI прошли',480,352,350,71,25,false,c.muted);
 text(s,'29 + 10',896,188,320,94,60,true,c.blue);
 text(s,'таблиц и sequences',896,296,320,80,28,true);
 text(s,'Совпали после\nbackup / restore',896,382,320,82,25,false,c.muted);
 text(s,'Локально установлен 9afe3ec',64,494,1152,50,35,true);
 text(s,'Python 3.14.9    PostgreSQL 18.6    Caddy 2.11.7',64,558,1152,45,29);
 text(s,'Последняя проверка 24 октября: HTTPS, Web, экспорт и 4 healthy-сервиса.',64,630,1152,32,23,false,c.muted);
}
{
 const s=slide('Обновление зависимостей',['docs/task-results/assets/PM-023/dependencies/comparison.json','docs/task-results/PM-023-dependencies.md'],'Trivy0.76.1, база от24октября13:07:23Z, linux/amd64. До: a7deaab, после: установленные образы9afe3ec. Сумма только трёх основных образов: Critical28/6, High280/163. Отдельный bot image в сумму не включён. Это строки package/version/advisory, не уникальные CVE и не доказанные атаки.');
 table(s,[['Образ','Critical до','Critical сейчас','High до','High сейчас'],['API / worker','6','2','70','61'],['HTTPS proxy','6','0','94','6'],['PostgreSQL','16','4','116','96'],['Всего строк','28','6','280','163']],[264,222,222,222,222],168,337,25);
 text(s,'32 High/Critical имеют указанную исправленную версию',64,533,1152,43,29,true,c.amber);
 text(s,'Остались в proxy и БД. Требуются разбор применимости и проверенные обновления.',64,586,1152,42,25);
 text(s,'Снимок 24 октября. Строки сканера могут повторять один CVE. Внешний релиз не принят.',64,642,1152,26,19,false,c.muted);
}
{
 const s=slide('Что остаётся до полной приёмки',['docs/tasks/PM-019.md','docs/tasks/PM-020.md','docs/tasks/PM-022.md','docs/tasks/PM-023.md','docs/tasks/PM-024.md'],'Android и виджет отложены владельцем. Полный L2:30минут/100клиентов на свободном компьютере, не подтверждён короткими тестами. PM-023 независимая Web/API-часть готова, но release gate открыт. PM-024 инструкции подготовлены, RC и приёмка владельцем отсутствуют.');
 table(s,[['Задача','Состояние','Оставшийся результат'],['PM-019','Отложена','APK/AAB и проверка на телефоне'],['PM-020','Отложена','Новостной домашний виджет'],['PM-022','Частично','Полный L2 на свободном компьютере'],['PM-023','Частично','Зависимости, notices и native privacy'],['PM-024','Частично','Сквозная приёмка и передача владельцу']],[180,245,727],166,426,26);
 text(s,'Google/Firebase и облако отложены. iOS и Windows остаются этапом развития.',64,626,1152,39,24,false,c.muted);
}
{
 const s=slide('Следующие шаги и порядок работ',['docs/STATUS.md','docs/task-results/PM-023-dependencies.md','docs/setup/PILOT_HANDOFF.md','docs/reviews/G05.md','docs/WORKING_AGREEMENT.md'],'Предлагаемый порядок для обсуждения, не новое разрешение начать работу. После этой дополнительной презентации запрашиваются12отдельных ответов. Android/облако/L2 не возобновляются автоматически. G05 по регламенту после20й полностью принятой задачи.');
 text(s,'1',64,176,65,52,38,true,c.blue);
 text(s,'Оставшиеся риски зависимостей',145,177,1071,47,33,true);
 text(s,'Разобрать пути вызова, обновить компоненты и повторить CI.\nЭто ближайший технический приоритет перед внешним пилотом.',145,237,1071,88,27);
 text(s,'2',64,351,65,52,38,true,c.blue);
 text(s,'Проверка продукта владельцем',145,352,1071,47,33,true);
 text(s,'Пройти локальный сценарий двух аккаунтов и двух ботов.\nСобрать замечания к My Space, Studio и заявкам.',145,412,1071,88,27);
 text(s,'3',64,526,65,52,38,true,c.blue);
 text(s,'Возврат к отложенным проверкам',145,527,1071,47,33,true);
 text(s,'Android и полный L2 после отдельного продолжения владельца.\nФормальная G05 после следующей полностью принятой задачи.',145,587,1071,76,26);
}
if(deck.slides.items.length!==N)throw new Error('Unexpected slide count.');
await fs.writeFile(path.join(build,'sources.json'),JSON.stringify(sources,null,2)+'\n');
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const filename=process.env.MARKETOB_DECK_NAME||'MarkeTOB-status-2026-10-25.pptx';
const finalPath=path.join(out,filename),tableSlides=[4,8,11,12];
const result=await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,
 pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableSlides.flatMap(n=>['--require-native-table-slide',String(n)])],
 explicitTotalSlideCount:N,requiredNativeTableOwnerSlides:tableSlides,requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,filename+'.validation.json')});
console.log(JSON.stringify(result));
const verified=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const [i,s] of verified.slides.items.entries()){
 const png=await verified.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log(`Rendered ${i+1}/${N}`);
}
try{
 const pdf=await verified.export({format:'pdf'});
 await fs.writeFile(path.join(out,path.basename(filename,'.pptx')+'.pdf'),new Uint8Array(await pdf.arrayBuffer()));
 console.log('PDF exported.');
}catch(error){console.warn(`PDF export unavailable: ${error.code||error.message}`);}
