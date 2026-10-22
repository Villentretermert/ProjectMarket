import {api, session} from './api.js';
import {el, button, modal, message, errorBox} from './dom.js';

const terminal = new Set(['confirmed', 'failed', 'cancelled']);
const labels = {queued:'Queued', processing:'Processing', confirmed:'Confirmed', failed:'Declined',
  unknown:'Awaiting confirmation', cancelled:'Cancelled'};
const memory = new Map();
const prefix = 'marketob-request:';
export function clearRequests() {
  memory.clear();
  try { for (const key of Object.keys(sessionStorage)) if (key.startsWith(prefix)) sessionStorage.removeItem(key); }
  catch { /* Browsers may disable session storage. In-memory recovery still works. */ }
}
function read(key) {
  if (memory.has(key)) return memory.get(key);
  try { const value = JSON.parse(sessionStorage.getItem(key)); if (value) memory.set(key, value); }
  catch { /* Treat unavailable or corrupt tab storage as empty. */ }
  return memory.get(key);
}
function write(key, value) {
  memory.set(key, value);
  // Persist references only, never private titles, prices, summaries or credentials.
  const {route, body, idempotency, requestID} = value;
  try { sessionStorage.setItem(key, JSON.stringify({route, body, idempotency, requestID})); } catch { /* memory fallback */ }
}
export function purchaseControls(channel, block, record, onAccessLost) {
  const host = el('div', {class:'stack'});
  const action = channel.actions.find(x => block.action_ids.includes(x.action_id) &&
    x.resource_id === record.source.resource_id && x.kind === 'request_purchase');
  if (!action) return host;
  if (!session) { host.append(message('Sign in to request this item.')); return host; }
  const user = session.user.user_id;
  const storageKey = prefix + user + ':' + channel.channel_id + ':' + action.action_id;
  let current = read(storageKey), busy = false;
  const show = () => {
    host.replaceChildren();
    if (current) {
      host.append(el('div', {class:'status', role:'status', 'data-state':current.result?.state || 'unknown'},
        el('strong', {}, labels[current.result?.state] || 'Awaiting confirmation'),
        current.result?.summary ? el('div', {}, current.result.summary) : message('The final outcome is not yet known.'),
        button('Check status', check, {disabled:busy})));
      if (terminal.has(current.result?.state)) host.append(button('New request', () => {
        current = null; memory.delete(storageKey);
        try { sessionStorage.removeItem(storageKey); } catch { /* memory cleared */ }
        show();
      }));
    } else host.append(button('Request purchase', confirm, {
      class:'primary', disabled:record.content.availability !== 'in_stock' || busy}));
  };
  async function check() {
    if (busy || !current || session?.user.user_id !== user) return;
    busy = true; show();
    try {
      const value = current.requestID ? await api('/action-requests/' + encodeURIComponent(current.requestID)) :
        await api(current.route, {method:'POST', body:current.body, key:current.idempotency});
      if (session?.user.user_id !== user) return;
      current.requestID = value.action_request_id; current.result = value; write(storageKey, current);
    } catch (error) {
      if ([401,403,404].includes(error.status)) { onAccessLost(); return; }
      if (error.status >= 400 && error.status < 500 && ![408,429].includes(error.status)) {
        current = null; memory.delete(storageKey);
        try { sessionStorage.removeItem(storageKey); } catch { /* memory cleared */ }
        busy = false; show(); host.append(errorBox(error), button('Refresh channel',onAccessLost)); return;
      }
      // A lost response retains the identical input and key for safe recovery.
      busy = false; show(); host.append(errorBox(error)); return;
    } finally { busy = false; }
    show();
  }
  function confirm() {
    modal('Confirm purchase request', el('div', {}, el('h3', {}, record.content.title),
      message('Quantity: 1'), el('p', {class:'notice'}, 'This sends a request to the bot. No money will be charged.')),
    close => [button('Send request', () => {
      close();
      current = {route:'/channels/' + channel.channel_id + '/actions', idempotency:crypto.randomUUID(),
        body:{action_id:action.action_id, resource_id:record.source.resource_id,
          observed_source_revision:record.source_revision, quantity:1}};
      write(storageKey, current); check();
    }, {class:'primary'})]);
  }
  show(); return host;
}
