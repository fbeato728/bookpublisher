'use strict';

const API = '/publisher/api';

/**
 * Thin fetch wrapper for all JSON API calls.
 * @param {string} method  'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
 * @param {string} path    API-relative path, e.g. '/projects/mybook/chapters'
 * @param {*}      body    Plain object → JSON; FormData → multipart; omit for GET
 * @returns {Promise<any>} Parsed JSON response
 * @throws  {Error}        If HTTP status is not ok (error message from server when available)
 */
async function apiFetch(method, path, body) {
    const opts = { method };
    if (body instanceof FormData) {
        opts.body = body;
    } else if (body !== undefined) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(`${API}${path}`, opts);
    if (!res.ok) {
        let msg = `${method} ${path} → ${res.status}`;
        try { const d = await res.clone().json(); msg = d.error || msg; } catch {}
        throw new Error(msg);
    }
    return res.json();
}
