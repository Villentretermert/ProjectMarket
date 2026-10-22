// Credentials remain in an HttpOnly cookie; CSRF lives only in memory.
export let session = null;
export let workspaceID = null;
export function setWorkspace(value) { workspaceID = value; }
export function setSession(value) { if (session?.user.user_id !== value?.user.user_id) workspaceID=null; session = value; }
export class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
export async function api(path, {method = 'GET', body, key, signal} = {}) {
  const headers = {};
  if (workspaceID && session) headers['X-Workspace-ID'] = workspaceID;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && session) headers['X-CSRF-Token'] = session.csrf_token;
  if (key) headers['Idempotency-Key'] = key;
  let response;
  try {
    response = await fetch('/v1' + path, {method, headers, credentials:'same-origin',
      cache:'no-store', body:body === undefined ? undefined : JSON.stringify(body),
      signal:signal || AbortSignal.timeout(15000)});
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, 'offline', 'Connection unavailable. Reconnect and try again.');
  }
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      setSession(null); window.dispatchEvent(new Event('session-expired'));
    }
    const retry = Number(response.headers.get('Retry-After'));
    const hint = response.status===429 && Number.isInteger(retry) && retry>0 && retry<=3600 ? ` Wait ${retry} seconds before retrying.` : '';
    throw new ApiError(response.status, data.code, (data.message || 'Request failed.') + hint);
  }
  return data;
}
export async function all(path) {
  const items = []; let cursor = null;
  do {
    const page = await api(path + (path.includes('?') ? '&' : '?') + 'limit=100' +
      (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
    items.push(...page.items); cursor = page.next_cursor;
  } while (cursor);
  return items;
}
