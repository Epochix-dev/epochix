/**
 * Tests for src/auth.js — the token a server started with EPOCHIX_AUTH_TOKEN
 * wants. The journey (a real server, a real browser) is driven by
 * tests/browser/test_dashboard_render.py; these pin the pieces.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

let auth;

beforeEach(async () => {
  vi.resetModules();
  sessionStorage.clear();
  history.replaceState(null, '', '/');
  auth = await import('../auth.js');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('takeTokenFromUrl', () => {
  it('takes ?token= out of the address bar and keeps the rest of it', () => {
    history.replaceState(null, '', '/v/run1?token=abc&locale=fr#sec-journey');
    auth.takeTokenFromUrl();
    expect(location.pathname + location.search + location.hash).toBe('/v/run1?locale=fr#sec-journey');
    expect(auth.authToken()).toBe('abc');
  });

  it('keeps the token for the next page in this tab', async () => {
    history.replaceState(null, '', '/?token=abc');
    auth.takeTokenFromUrl();
    // A navigation: the module starts again, the URL carries no token.
    vi.resetModules();
    history.replaceState(null, '', '/v/run1');
    const next = await import('../auth.js');
    next.takeTokenFromUrl();
    expect(next.authToken()).toBe('abc');
  });

  it('holds nothing when the page was opened without one', () => {
    history.replaceState(null, '', '/v/run1');
    auth.takeTokenFromUrl();
    expect(auth.authToken()).toBeNull();
  });
});

describe('requests', () => {
  it('sends the token as a Bearer header, and nothing without one', async () => {
    const seen = [];
    vi.stubGlobal('fetch', (url, init) => {
      seen.push(new Headers(init?.headers ?? {}).get('Authorization'));
      return Promise.resolve(new Response('{}'));
    });
    await auth.apiFetch('/api/runs');
    history.replaceState(null, '', '/?token=s3cret');
    auth.takeTokenFromUrl();
    await auth.apiFetch('/api/runs', { headers: { Accept: 'application/json' } });
    expect(seen).toEqual([null, 'Bearer s3cret']);
  });

  it('adds token= to a live-feed URL only when one is held', () => {
    expect(auth.withToken('/sse/live/r1?last_seq=3')).toBe('/sse/live/r1?last_seq=3');
    history.replaceState(null, '', '/?token=a%26b');
    auth.takeTokenFromUrl();
    expect(auth.withToken('/sse/live/r1?last_seq=3')).toBe('/sse/live/r1?last_seq=3&token=a%26b');
  });
});

describe('the live clients', () => {
  it('open the WebSocket and the SSE feed with the token', async () => {
    const opened = [];
    vi.stubGlobal('WebSocket', class {
      constructor(url) { opened.push(url); }
      close() {}
    });
    vi.stubGlobal('EventSource', class {
      constructor(url) { opened.push(url); }
      close() {}
    });
    history.replaceState(null, '', '/v/r1?token=s3cret');
    auth.takeTokenFromUrl();
    const { connect, disconnect } = await import('../ws-client.js');
    const { connectSSE, disconnectSSE } = await import('../sse-client.js');
    connect('r1', 4);
    connectSSE('r1', 4);
    disconnect();
    disconnectSSE();
    expect(opened).toHaveLength(2);
    expect(opened[0]).toMatch(/\/ws\/live\/r1\?last_seq=4&token=s3cret$/);
    expect(opened[1]).toBe('/sse/live/r1?last_seq=4&token=s3cret');
  });
});
