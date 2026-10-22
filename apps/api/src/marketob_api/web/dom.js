// Data is always text, never interpreted as HTML, CSS or executable expressions.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (key === 'value') node.value = value;
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  node.append(...children.flat().filter(x => x !== null && x !== undefined));
  return node;
}
export const button = (text, action, attrs = {}) => el('button', {type:'button', onclick:action, ...attrs}, text);
export const link = (text, href, attrs = {}) => el('a', {href, ...attrs}, text);
export const message = text => el('p', {class:'muted'}, text);
let toastTimer;
export function toast(text) {
  document.querySelector('#toast').textContent = text;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => document.querySelector('#toast').textContent = '', 5000);
}
export function errorBox(error, retry) {
  return el('div', {class:'error', role:'alert'}, el('p', {}, error.message || String(error)),
    retry ? button('Try again', retry) : null);
}
export function field(label, attrs = {}) {
  const input = el('input', attrs);
  return {input, node:el('label', {}, label, input)};
}
export function safeURL(raw) {
  try { const u = new URL(raw); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; }
  catch { return null; }
}
export function plainText(text) {
  const node = el('div', {class:'body-text'});
  for (const part of String(text).split(/(https:\/\/[^\s<>]+)/g)) {
    const url = safeURL(part);
    node.append(url ? link(part, url, {target:'_blank', rel:'noopener noreferrer'}) : document.createTextNode(part));
  }
  return node;
}
export function heading(title, subtitle, ...actions) {
  return el('div', {class:'page-head'}, el('div', {}, el('div', {class:'eyebrow'}, 'Your bots, one space'),
    el('h1', {}, title), message(subtitle)), el('div', {class:'toolbar'}, actions));
}
export function modal(title, content, actions) {
  const titleID = 'dialog-' + crypto.randomUUID();
  const dialog = el('dialog', {'aria-labelledby':titleID}, el('h2', {id:titleID}, title), content);
  const close = () => dialog.close();
  dialog.append(el('div', {class:'toolbar'}, button('Cancel', close), ...actions(close)));
  dialog.addEventListener('close', () => dialog.remove());
  document.body.append(dialog); dialog.showModal(); return dialog;
}
