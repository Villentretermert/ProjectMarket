// G02 evidence deck. Runtime paths come from load_workspace_dependencies.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const repo=process.cwd(), skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill) throw new Error('Set MARKETOB_PRESENTATIONS_SKILL and supplied runtime paths.');
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const out=path.join(repo,'docs/reviews/G02'), build=path.join(repo,'.local/G02-build');
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
 const s=slide('MarkeTOB / G02','Источники: docs/task-results/PM-005.md–PM-008.md. Контрольная точка после основы, identity, registry и ingestion. Локальный этап, без облака.');
 text(s,'Локальный backend',64,230,1152,95,62,true,c.blue);
 text(s,'Аккаунты, подключение ботов\nи надёжное сохранение данных',64,355,1090,140,38);
 text(s,'PM-005–008\n22 октября 2026',64,568,800,80,26,false,c.muted);
}
{
 const s=slide('Реализованные компоненты','Источники: отчёты PM-005–008, commit d4a24d8 / 94a2cf3 / ab48d25 / 6fd3574. Фактические acceptance и CI ссылки в Markdown G02.');
 table(s,[['Задача','Компонент','Результат'],['PM-005','Окружение и CI','Python workspace, Docker, health'],['PM-006','Аккаунты и права','Сессии, B2B workspace, grants'],['PM-007','Реестр ботов','Bootstrap, ключи, scopes, отзыв'],['PM-008','Приём сообщений','Снимок, версии, dedup и outbox']],[175,380,597],166,380);
 text(s,'Все эти компоненты работают локально через HTTP и PostgreSQL.',64,584,1130,70,29,true,c.green);
}
{
 const s=slide('Система и готовность','Источники: apps/api/src/marketob_api, compose.yaml, docs/ROADMAP.md. Зелёный: готово в backend. Синий: частично. Серый: не сделано/отложено. Связь API с UI и Android пока целевая.');
 text(s,'Готово: зелёный     Частично: синий     Не сделано: серый',64,144,1152,40,25,false,c.muted);
 const bots=node(s,'HTTP-интеграция ботов\nКлючи и приём готовы\nSDK / боты: PM-011',64,240,300,150,'#EAF2FD');
 const api=node(s,'FastAPI\nIdentity / registry\nIngestion',490,240,300,150,'#DFF1E8');
 const web=node(s,'Web UX\nПрототип готов\nAPI ещё не подключён',916,240,300,150,'#EAF2FD');
 const worker=node(s,'Python maintenance\nОчистка истории\nГотово',64,475,300,135,'#DFF1E8');
 const db=node(s,'PostgreSQL\nДанные / квитанции\nOutbox',490,475,300,135,'#DFF1E8');
 const android=node(s,'Android / widget\nСборка и устройство\nотложены',916,475,300,135,'#E5EAF0');
 connect(s,bots,api);connect(s,api,web);connect(s,api,db,'bottom','top');connect(s,worker,db);
 connect(s,web,android,'bottom','top');
 text(s,'HTTP',383,272,90,35,23,false,c.muted);text(s,'план',815,272,90,35,23,false,c.muted);
}
{
 const s=slide('Подключение бота','Источники: docs/api/IDENTITY.md, BOT_REGISTRATION.md, INGESTION.md. Реализованный HTTP flow. Studio UI относится к PM-014.');
 const rows=[['1','Локальный аккаунт','Владелец включает личный B2B workspace.'],['2','Регистрация бота','Сервер выдаёт одноразовый код на 15 минут.'],['3','Обмен кода','Бот получает рабочий ключ на 90 дней.'],['4','Черновик канала','Владелец создаёт источник, бот отправляет данные.']];
 rows.forEach((r,i)=>{const y=170+i*116;text(s,r[0],64,y,70,55,40,true,c.blue);text(s,r[1],164,y,1000,44,31,true);text(s,r[2],164,y+49,1035,58,27);});
 text(s,'Сервер хранит verifier ключа. Полный секрет виден только при выдаче.',64,644,1140,30,23,false,c.muted);
}
{
 const s=slide('Одна транзакция приёма','Источник: apps/api/src/marketob_api/ingestion.py. Bot/source authorization предшествует replay. Snapshot, receipt, history, data_revision и outbox коммитятся атомарно. tests/test_ingestion.py проверяет trigger-induced rollback.');
 const input=node(s,'Проверка ключа\nСхема / квота\nПрава на источник',64,292,285,145,'#EAF2FD');
 const tx=node(s,'',440,180,400,370,'#DFF1E8');
 text(s,'PostgreSQL transaction',460,204,360,60,28,true);
 text(s,'Актуальная запись / tombstone\n\nКвитанция и история сообщения\n\nВерсия канала и событие outbox',460,292,360,230,26);
 const success=node(s,'Commit\nHTTP 200\nКвитанция приёма',931,292,285,145,'#DFF1E8');
 connect(s,input,tx);connect(s,tx,success);
 text(s,'Сбой записи outbox откатывает все изменения этого сообщения.',64,576,1150,76,31,true,c.blue);
}
{
 const s=slide('Проверки отказов и повторов','Источники: tests/test_identity.py, test_bots.py, test_ingestion.py. Общий локальный прогон: 73 passed, 39.88s, Python 3.14.7/PostgreSQL 18.6. scripts/smoke_ingestion.py и .local реальный процесс проверили restart.');
 table(s,[['Проверка','Ожидаемое поведение','Результат'],['Один bootstrap, два запроса','Только один рабочий ключ','PASS'],['Чужой бот / revoked key','Отказ без доступа к данным','PASS'],['Дубль / старый revision','Прежняя квитанция / 409','PASS'],['Сбой записи события','Откат данных и квитанции','PASS'],['Перезапуск API','Та же durable-квитанция','PASS']],[390,520,242],156,420);
 text(s,'73 локальных теста прошли. Отдельный HTTP-прогон проверил restart.',64,612,1130,45,28,true,c.green);
}
{
 const s=slide('Скорость локального приёма','Источник: docs/task-results/assets/PM-008/ingestion-burst.json. Windows/Python 3.14.7/PostgreSQL 18.6, loopback HTTP, 4 clients, 100 successful messages in 3.384s. p50 108.93ms, p95 222.53ms, max 330.41ms. Короткий synthetic burst, не steady-state benchmark.');
 text(s,'29,55',64,178,490,95,70,true,c.blue);text(s,'запроса в секунду',64,277,510,50,30);
 text(s,'223 мс',690,178,510,95,70,true,c.blue);text(s,'p95 до подтверждения записи',690,277,520,70,28);
 table(s,[['Условия','Значение'],['Принято / ошибок','100 / 0'],['Боты / одновременные клиенты','4 / 4'],['Длительность / текст новости','3,384 с / 512 символов']],[650,502],375,210);
 text(s,'Длительные 1 000 сообщений/мин и задержку в UI проверим отдельно.',64,624,1140,38,25,false,c.amber);
}
{
 const s=slide('Код и сущности','Источники: apps/api/src/marketob_api/{identity,bot_identity,bot_routes,ingestion,maintenance,payloads}.py и migrations/001–003. Детальные пояснения и границы в docs/reviews/G02/README.md.');
 table(s,[['Компонент','Назначение','Сущности'],['identity / access','Сессии и серверные права','User, Session, Org, Grant'],['bot_identity / bot_routes','Регистрация и отзыв ключей','Bot, Registration, Key'],['payloads / quotas','Схемы и лимиты сообщений','Message, RateBucket'],['ingestion','Атомарная запись и replay','Record, Receipt, Outbox'],['maintenance','Ограниченная история','History 7d, Receipt 30d']],[350,425,377],156,420);
 text(s,'Python: API, миграции и тесты. SDK и пилотные боты предстоят.',64,620,1140,42,27,false,c.muted);
}
{
 const s=slide('Интерфейс и оставшаяся работа','Изображение: docs/task-results/assets/PM-003/studio.png, исходный HTML/JS demo. Это неизменённый прототип, не интерфейс нового backend. Границы: docs/ROADMAP.md и WORKING_AGREEMENT.md.');
 text(s,'Web Studio пока использует\nдемонстрационные данные.',64,170,545,105,31,true);
 text(s,'Далее нужны публикация каналов,\nчтение блоков и заявки боту.\n\nЗатем подключим Web-интерфейс.\n\nAndroid, Google и облако\nостаются отложенными.',64,313,555,290,28);
 const bytes=await fs.readFile(path.join(repo,'docs/task-results/assets/PM-003/studio.png'));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Existing PM-003 Studio prototype with synthetic data',fit:'contain',position:{left:650,top:180,width:566,height:380}});
 text(s,'Существующий макет PM-003',650,584,566,36,24,false,c.muted);
}
{
 const s=slide('Следующие четыре задачи','Источник: docs/ROADMAP.md. PM-009–012 начинаются после ответов G02 или нового явного разрешения продолжить с допущениями. Предыдущее разрешение реализовать PM-006–008 не отменяет G02.');
 table(s,[['Порядок','Задача','Зачем'],['PM-009','Публикация и snapshot','Показать разрешённые данные'],['PM-010','Заявки, GET, ACK, result','Связать действие клиента с ботом'],['PM-011','SDK и два пилотных бота','Подключать внешние HTTP-сервисы'],['PM-012','Полный backend-цикл','Проверить сбои и восстановление']],[175,470,507],166,380);
 text(s,'Перед продолжением обсудим 12 отдельных вопросов G02.',64,593,1140,68,31,true,c.blue);
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(out,process.env.MARKETOB_DECK_NAME||'MarkeTOB-G02.pptx');
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
