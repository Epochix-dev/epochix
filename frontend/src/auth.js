/**
 * auth.js — the access token a server started with EPOCHIX_AUTH_TOKEN wants.
 *
 * The server's read routes want `Authorization: Bearer <token>` and its live
 * feeds want `?token=<token>` (a browser cannot set a header on a WebSocket or
 * an EventSource). The dashboard sent neither, so with a token set it could
 * not load a run at all — while the docs described the token as the way to
 * run the dashboard remotely.
 *
 * How a reader supplies it: open any dashboard page once with `?token=<token>`.
 * The page takes the token out of the address bar straight away (so it is not
 * left in history, a bookmark, a copied link or a Referer), keeps it in memory
 * and in this tab's sessionStorage — which lives as long as the tab and is
 * never shared with other tabs or written to disk as a cookie would be — and
 * sends it on every request to the server. Links on the page never carry it;
 * the next page in the same tab reads it back from sessionStorage.
 *
 * An exported report is built by the server from the run, not from this page,
 * so the token has no way into one.
 */

const STORAGE_KEY = 'epochix-token';

/** @type {string|null} */
let _token = null;
let _loaded = false;

function _readStored() {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private window, sandboxed frame)
  }
}

function _store(token) {
  try {
    sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* memory only: the next page in this tab will need ?token= again */
  }
}

/**
 * Take `?token=` from the address bar, if the page was opened with one, and
 * remove it from the URL. Safe to call more than once.
 */
export function takeTokenFromUrl() {
  const url = new URL(location.href);
  const given = url.searchParams.get('token');
  if (given === null) return;
  url.searchParams.delete('token');
  try {
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  } catch {
    /* a sandboxed document may refuse; the token is still taken */
  }
  if (given) {
    _token = given;
    _loaded = true;
    _store(given);
  }
}

/** The token this tab holds, or null. */
export function authToken() {
  if (!_loaded) {
    _token = _readStored();
    _loaded = true;
  }
  return _token || null;
}

/** Forget the token (tests). */
export function resetAuthToken() {
  _token = null;
  _loaded = false;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing stored */
  }
}

/**
 * `fetch` with the token as a Bearer header, when one is held.
 * @param {string} url
 * @param {RequestInit} [init]
 */
export function apiFetch(url, init = {}) {
  const token = authToken();
  if (!token) return fetch(url, init);
  const headers = new Headers(init.headers ?? {});
  headers.set('Authorization', `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

/**
 * A live-feed URL with `token=` added, when one is held. For the WebSocket and
 * SSE URLs only — never for a link a reader can see, copy or follow.
 * @param {string} url  Absolute or root-relative.
 */
export function withToken(url) {
  const token = authToken();
  if (!token) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

/**
 * Save a server response as a download. The anchor points at a blob, so the
 * request that fetched it — and its token — leaves no trace in the page.
 * @param {Response} res
 * @param {string} fallbackName
 */
export async function saveResponse(res, fallbackName) {
  const m = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') || '');
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
