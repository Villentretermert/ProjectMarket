// Local G01 presentation. Uses the supplied Artifact Tool runtime, not application code.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const repo=process.cwd();
const skill=process.env.MARKETOB_PRESENTATIONS_SKILL;
if(!skill) throw new Error('Set MARKETOB_PRESENTATIONS_SKILL and runtime paths from load_workspace_dependencies.');
const {importRuntimeModule}=await import(pathToFileURL(path.join(skill,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile,FileBlob}=await importRuntimeModule('@oai/artifact-tool');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const out=path.join(repo,'docs/reviews/G01');
const build=path.join(repo,'.local/G01-build');
await fs.mkdir(build,{recursive:true});await fs.mkdir(out,{recursive:true});
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const c={bg:'#F3F6FB',ink:'#213247',muted:'#53677F',blue:'#2468BC',green:'#1E7659',amber:'#825414',line:'#D5DFEB'};
const font='Arial';
function text(slide,value,x,y,w,h,size=28,bold=false,color=c.ink){
 const s=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 s.text=value;s.text.insets=0;s.text.style={typeface:font,fontSize:size,bold,color};return s;
}
function slide(title,notes){
 const s=deck.slides.add();s.background.fill=c.bg;
 text(s,title,64,42,1152,92,44,true);
 text(s,`${deck.slides.items.length} / 9`,1130,676,86,24,16,false,c.muted);
 s.speakerNotes.text=notes;return s;
}
function table(s,values,widths,y=170,height=360){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top:y,width:1152,height,columnWidths:widths,values});
 t.borders.assign({fill:c.line,width:1,style:'solid'});
 for(let r=0;r<values.length;r++)for(let col=0;col<values[0].length;col++){
  const cell=t.getCell(r,col);cell.fill=r===0?c.blue:'#FFFFFF';
  cell.text.style={typeface:font,fontSize:24,bold:r===0,color:r===0?'#FFFFFF':c.ink};
 }
 return t;
}
async function image(s,name,x,y,w,h){
 const bytes=await fs.readFile(path.join(repo,'docs/task-results/assets/PM-003',name));
 s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:`MarkeTOB design prototype: ${name}`,fit:'contain',position:{left:x,top:y,width:w,height:h}});
}
function node(s,label,x,y,w,h,fill){
 const n=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:c.line,width:1}});
 n.text=label;n.text.insets=14;n.text.style={typeface:font,fontSize:24,color:c.ink,alignment:'center',verticalAlignment:'middle'};return n;
}
function connect(s,a,b,from='right',to='left'){
 s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:c.muted,width:2},tail:{type:'triangle',width:'med',length:'med'}});
}
{
 const s=deck.slides.add();s.background.fill=c.blue;
 text(s,'MarkeTOB',70,150,1100,110,76,true,'#FFFFFF');
 text(s,'Локальный пилот\nКонтрольная точка G01',74,285,1070,150,44,false,'#FFFFFF');
 text(s,'PM-001–004 завершены в зафиксированном объёме\n21 октября 2026',74,520,1070,90,26,false,'#FFFFFF');
 s.speakerNotes.text='Источники: docs/STATUS.md, docs/task-results/PM-001.md–PM-004.md. PM-002 принят в Web-объёме по решению владельца отложить Android. Продукт ещё не готов.';
}
{
 const s=slide('Результаты первых четырёх задач','Источники: docs/task-results/PM-001.md, PM-002.md, PM-003.md, PM-004.md. Готовность относится к результату конкретной задачи, не ко всему приложению.');
 table(s,[['Задача','Результат','Граница готовности'],['PM-001','30 требований, 16 историй','Требования и цели проверки'],['PM-002','Web-стек и архитектура','Android проверим позже'],['PM-003','Интерактивный UX','Демонстрационные данные'],['PM-004','64 схемы, 44 операции','Спецификация API']], [185,455,512],164,376);
 text(s,'Продуктовый backend, Docker-образ и APK ещё предстоит создать.',64,578,1120,65,28,false,c.amber);
}
{
 const s=slide('Каталог и статус заявки','Источник изображения: docs/task-results/assets/PM-003/catalog-request.png. Данные и действие синтетические. Прототип PM-003, не рабочая покупка. Сценарии: docs/DESIGN.md.');
 text(s,'Пользователь сохраняет канал и отправляет заявку боту.',64,174,425,105,30,true);
 text(s,'Request sent показывает очередь.\n\nConfirmed появляется после результата бота.\n\nView request открывает существующую заявку.',64,310,415,260,27);
 text(s,'Макет с demo-данными',64,615,425,34,22,false,c.muted);
 await image(s,'catalog-request.png',520,136,700,520);
}
{
 const s=slide('Мобильная навигация и закрытый источник','Источники: mobile-channels.png и widget-private.png в docs/task-results/assets/PM-003/. HTML-прототип. Реальное устройство и Android widget отложены владельцем.');
 await image(s,'mobile-channels.png',64,150,285,490);
 await image(s,'widget-private.png',385,150,285,490);
 text(s,'На телефоне список каналов и содержимое открываются последовательно.',730,175,475,140,28);
 text(s,'Закрытый источник показывает Access required без новостных данных.',730,340,475,130,28);
 text(s,'Виджет пока представлен HTML-макетом. APK и USB-проверка отложены.',730,520,475,120,26,false,c.amber);
}
{
 const s=slide('Система: готовность компонентов','Источники: docs/ARCHITECTURE.md и ADR-0001–0003. Зелёный: готовая спецификация. Синий: проверенный прототип. Серый: запланированный runtime. Все соединения показывают целевую архитектуру, не действующую интеграцию.');
 text(s,'Готово: контракт     Частично: клиентский прототип     Не сделано: runtime',64,135,1150,44,23,false,c.muted);
 const bot=node(s,'Python-боты\nне сделано',64,220,270,112,'#E5EAF0');
 const api=node(s,'FastAPI\nне сделано',505,220,270,112,'#E5EAF0');
 const web=node(s,'Web UX\nчастично',946,220,270,112,'#EAF2FD');
 connect(s,bot,api);connect(s,api,web);
 const contract=node(s,'Контракт 1.0\nготово',64,462,270,112,'#DFF1E8');
 const db=node(s,'PostgreSQL + worker\nне сделано',505,462,270,112,'#E5EAF0');
 const android=node(s,'Android + widget\nпроверка отложена',946,462,270,112,'#E5EAF0');
 connect(s,api,db,'bottom','top');
 s.shapes.connect(api,android,{kind:'elbow',fromSide:'right',toSide:'left',line:{fill:c.muted,width:2},tail:{type:'triangle',width:'med',length:'med'}});
 text(s,'POST / GET',356,237,135,32,22,false,c.muted);
 text(s,'snapshots',800,237,130,32,22,false,c.muted);
 text(s,'Боты общаются через API. Доступ к таблицам БД им не предоставляется.',64,617,1145,40,25);
}
{
 const s=slide('Жизненный цикл действия','Источники: docs/api/PROTOCOL.md, packages/contracts/src/contracts/reference_model.py, packages/contracts/tests/test_protocol.py. Модель поведения проверена. Durable commit, гонки и восстановление реального PostgreSQL проверяются в PM-010/012.');
 text(s,'1',64,176,70,65,46,true,c.blue);text(s,'Запись заявки',156,175,900,45,32,true);
 text(s,'Сервер проверяет права, наличие товара и его revision.\nПовтор с тем же ключом возвращает существующую заявку.',156,229,1030,90,27);
 text(s,'2',64,341,70,65,46,true,c.blue);text(s,'GET и ACK',156,340,900,45,32,true);
 text(s,'GET допускает повторную доставку. Бот сохраняет событие\nи подтверждает получение отдельным ACK.',156,394,1030,90,27);
 text(s,'3',64,505,70,65,46,true,c.blue);text(s,'Результат бота',156,504,900,45,32,true);
 text(s,'Processing, Confirmed или Failed меняют бизнес-статус.\nНеопределённый результат требует сверки, без новой покупки.',156,558,1030,90,27);
}
{
 const s=slide('Код, компоненты и сущности','Источники: design/prototype/prototype.js, packages/contracts/src/contracts/build_contract.py, packages/contracts/src/contracts/reference_model.py, docs/ARCHITECTURE.md. User/Session, Bot/Key, Channel/Grant, ActionRequest/BotEvent и SharedTemplate пока описаны контрактом, не таблицами работающей БД.');
 table(s,[['Файл / компонент','Что делает','Сущности'],['prototype.js','Переходы экранов в памяти','Channel, Block, My Space'],['build_contract.py','Генерирует OpenAPI и схемы','Message, Layout, Result'],['reference_model.py','Проверяет сценарии доставки','Request, Event, ACK'],['Identity / Registry','Следующий этап реализации','User, Session, Bot, Key'],['Pages / Sharing','Права и ссылки на источники','Channel, Grant, Template']], [330,440,382],156,436);
 text(s,'Python используется для контракта, проверок и будущего backend.',64,620,1140,35,26,false,c.muted);
}
{
 const s=slide('Проверки и оставшиеся риски','Источники: docs/task-results/PM-001.md–PM-004.md, assets/PM-003/contrast.json, assets/PM-004/verification.json. 1000 сообщений/мин и p95<=3с являются целями PM-022, не результатами текущего этапа.');
 text(s,'Проверено',64,160,520,55,34,true,c.green);
 text(s,'25 контрактных тестов прошли.\n\n12 цветовых пар прошли проверку.\n\nDesktop и mobile UX пройдены.\n\nWeb-spike открывается offline.',64,238,540,350,28);
 text(s,'Проверить при реализации',686,160,530,55,34,true,c.amber);
 text(s,'SQL-транзакции и реальные права.\n\nПадение API/worker и восстановление.\n\nAPK, устройство и домашний виджет.\n\nНагрузка 1 000 сообщений/мин.',686,238,530,350,28);
 text(s,'Цели производительности ещё не измерены. Google и облачный push отложены.',64,625,1152,36,24,false,c.muted);
}
{
 const s=slide('Следующий этап: основа backend','Источник: docs/ROADMAP.md, задачи PM-005–008. Начать после ответов G01 либо явного разрешения продолжить с записанными допущениями. Docker отсутствует в текущей среде, его проверка остаётся обязательной перед поставкой.');
 table(s,[['Порядок','Задача','Зачем сейчас'],['PM-005','Окружение и CI','Воспроизводимый запуск и проверки'],['PM-006','Локальные сессии и права','Отделить пользователей и источники'],['PM-007','Боты и индивидуальные ключи','Разрешить безопасное подключение'],['PM-008','Приём и хранение сообщений','Получить первые реальные snapshots']], [175,470,507],164,365);
 text(s,'До PM-005 нужны ответы на вопросы G01.\nПосле PM-008 проведём следующую презентацию.',64,571,1120,84,30,true,c.blue);
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(deck)).save(candidate);
const finalPath=path.join(out,process.env.MARKETOB_DECK_NAME||'MarkeTOB-G01.pptx');
const result=await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,
 pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[2,7,9].flatMap(x=>['--require-native-table-slide',String(x)])],
 explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[2,7,9],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify(result));
const verified=await PresentationFile.importPptx(await FileBlob.load(finalPath));
for(const [i,s] of verified.slides.items.entries()){
 const png=await verified.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
try {
 const pdf=await verified.export({format:'pdf'});
 await fs.writeFile(path.join(out,path.basename(finalPath,'.pptx')+'.pdf'),new Uint8Array(await pdf.arrayBuffer()));
 console.log('PPTX, PDF and nine rendered previews are ready for visual review.');
} catch(error) {
 console.warn(`PPTX and previews are ready; PDF export unavailable: ${error.code || error.message}. Use the reviewed slide PNG fallback.`);
}
