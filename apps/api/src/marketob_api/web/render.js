import {el, message, plainText} from './dom.js';
import {purchaseControls} from './actions.js';

export const views = {news:['article','compact'], product:['list','card'], chart:['line','bars','table']};
const viewNames = {article:'Expanded',compact:'Headlines',list:'Compact list',card:'Card',line:'Line chart',bars:'Bar chart',table:'Data table'};
export function money(value) {
  try {
    const format = new Intl.NumberFormat('en', {style:'currency', currency:value.currency});
    return format.format(value.amount_minor / 10 ** format.resolvedOptions().maximumFractionDigits);
  } catch { return value.amount_minor + ' minor units · ' + value.currency; }
}
function svgNode(name, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function coordinate(value, kind) {
  if (kind !== 'time') return String(value);
  const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toISOString().slice(0,10) : String(value);
}
function chartTable(data) {
  const table = el('table', {}, el('caption', {}, data.title + ' · data'),
    el('thead', {}, el('tr', {}, ['Series',data.x_label,data.y_label + ' (' + data.unit + ')'].map(x => el('th', {scope:'col'}, x)))));
  const body = el('tbody');
  for (const series of data.series) for (const point of series.points)
    body.append(el('tr', {}, el('th', {scope:'row'}, series.name), el('td', {}, coordinate(point.x, data.x_kind)), el('td', {}, String(point.y))));
  table.append(body); return el('div', {class:'table-wrap'}, table);
}
function chart(data, view) {
  if (view === 'table') return chartTable(data);
  const points = data.series.flatMap(x => x.points);
  if (!points.length) return message('No chart data yet.');
  const minX = Math.min(...points.map(x => x.x)), maxX = Math.max(...points.map(x => x.x));
  const minY = Math.min(0,...points.map(x => x.y)), maxY = Math.max(0,...points.map(x => x.y));
  function drawing(narrow) {
  const left=narrow?74:84, right=narrow?330:698, bottom=212, height=narrow?275:252;
  const x = v => left + (v - minX) / (maxX - minX || 1) * (right-left);
  const y = v => 212 - (v - minY) / (maxY - minY || 1) * 180;
  const svg = svgNode('svg', {viewBox:`0 0 ${narrow?350:740} ${height}`, class:'chart '+(narrow?'chart-narrow':'chart-wide'), role:'img', 'aria-label':data.title});
  svg.append(svgNode('title', {}, data.title + '. Exact values are available in the data table.'));
  for (let i=0; i<=4; i++) {
    const value = minY + (maxY - minY) * i / 4;
    const tick=Math.abs(value)>=100000?value.toExponential(1):String(Number(value.toPrecision(4)));
    svg.append(svgNode('line', {x1:left,x2:right,y1:y(value),y2:y(value),class:'chart-grid'}),
      svgNode('text', {x:left-8,y:y(value)+4,'text-anchor':'end',class:'chart-axis'}, tick));
  }
  const label=value=>data.x_kind==='time'?coordinate(value,data.x_kind):(Math.abs(value)>=100000?value.toExponential(1):String(Number(value.toPrecision(4))));
  svg.append(svgNode('text',{x:left,y:narrow?252:239,class:'chart-axis'},label(minX)),
    svgNode('text',{x:right,y:narrow?252:239,'text-anchor':'end',class:'chart-axis'},label(maxX)));
  const colors = ['#1767bd','#b15212','#25764c','#8a49a2','#9d344c'];
  data.series.forEach((series, index) => {
    const color = colors[index % colors.length];
    if (view === 'line') svg.append(svgNode('polyline', {points:series.points.map(p=>`${x(p.x)},${y(p.y)}`).join(' '),class:'chart-line',stroke:color}));
    for (const point of series.points) {
      const width = Math.min(28, (right-left)*0.8 / (points.length || 1));
      const node = view === 'bars' ? svgNode('rect', {x:x(point.x) + index*width - width*data.series.length/2,
        y:Math.min(y(point.y),y(0)),width:Math.max(1,width-2),height:Math.max(1,Math.abs(y(point.y)-y(0))),fill:color}) :
        svgNode('circle', {cx:x(point.x),cy:y(point.y),r:3,fill:color});
      node.append(svgNode('title', {}, `${series.name}: ${coordinate(point.x,data.x_kind)}, ${point.y}`)); svg.append(node);
    }
  });
  return svg;
  }
  // Two static layouts keep axis text legible at phone width without resize listeners.
  return el('div', {}, message(data.x_label + ' · ' + data.y_label + ' (' + data.unit + ')'), drawing(false),drawing(true),
    el('div', {class:'legend'}, data.series.map((s,i)=>el('span', {class:'series-'+i}, `${i+1}. ${s.name}`))),
    el('details', {}, el('summary', {}, 'View chart data'), chartTable(data)));
}
export function renderBlock(block, record, channel, {onAccessLost = () => {}, onView, extra} = {}) {
  const root = el('article', {class:'block', 'data-block':block.block_id});
  if (!record) { root.append(el('h3', {}, 'Source unavailable'), message('This item was removed or you no longer have access.')); return root; }
  if (!views[block.content_type]?.includes(block.view)) { root.append(message('Unsupported block format.')); return root; }
  let view = block.view;
  const select = el('select', {'aria-label':'View for ' + record.content.title}, views[block.content_type].map(v=>el('option', {value:v}, viewNames[v])));
  select.value = view;
  const body = el('div');
  root.append(el('div', {class:'block-head'}, el('span', {class:'badge'}, block.content_type.toUpperCase()), select), body);
  if (extra) root.append(extra);
  function paint() {
    root.className = 'block ' + view;
    body.replaceChildren();
    const data = record.content;
    if (block.content_type === 'news') body.append(el('h2', {}, data.title), plainText(data.body));
    else if (block.content_type === 'product') {
      body.append(el('div', {class:'product-main'}, el('div', {}, el('h2', {}, data.title), plainText(data.description)),
        el('div', {class:'product-price'}, money(data.price))),
      el('div', {class:'product-footer'}, el('span', {class:'badge'}, {in_stock:'In stock', out_of_stock:'Out of stock', unavailable:'Unavailable'}[data.availability]),
        purchaseControls(channel, block, record, onAccessLost)));
    } else body.append(el('h2', {}, data.title), chart(data, view));
  }
  select.addEventListener('change', () => { view=select.value; paint(); onView?.(view); });
  paint(); return root;
}
export function renderSnapshot(snapshot, options = {}) {
  if (snapshot.channel.layout.schema_version !== '1.0') return message('Unsupported layout version.');
  const layout = snapshot.channel.layout;
  const host = el('div', {class:'blocks ' + (layout.theme==='ink'?'ink':'') + ' ' + (layout.density==='comfortable'?'comfortable':'')});
  for (const block of layout.blocks) {
    const record = snapshot.records.find(r=>r.source.channel_id === block.source.channel_id && r.source.resource_id === block.source.resource_id);
    host.append(renderBlock(block, record, snapshot.channel, options));
  }
  if (!layout.blocks.length) host.append(el('div', {class:'empty'}, el('h2', {}, 'No published blocks yet'), message('The publisher has not added content to this page.')));
  return host;
}
