/**
 * ASTC 期貨篩選器 - Cloudflare Worker
 *
 * 簡單的靜態資源代理，從 GitHub Pages 提供前端頁面。
 * 個人使用，無需會員驗證。
 */

const GITHUB_PAGES_BASE = 'https://raw.githubusercontent.com/atomfey/futures-screener/main/docs';

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml',
};

export default {
  async fetch(request) {
    const url = new URL(request.url);
    let path = url.pathname;

    // Default to index.html
    if (path === '/' || path === '') {
      path = '/index.html';
    }

    // Determine MIME type
    const ext = path.substring(path.lastIndexOf('.'));
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    try {
      const resp = await fetch(`${GITHUB_PAGES_BASE}${path}`, {
        headers: { 'User-Agent': 'ASTC-Futures-Screener-Worker' },
      });

      if (!resp.ok) {
        // Try index.html for SPA-like routing
        if (ext === '' || !MIME_TYPES[ext]) {
          const fallback = await fetch(`${GITHUB_PAGES_BASE}/index.html`, {
            headers: { 'User-Agent': 'ASTC-Futures-Screener-Worker' },
          });
          return new Response(fallback.body, {
            status: 200,
            headers: {
              'Content-Type': 'text/html; charset=utf-8',
              'Cache-Control': 'no-cache',
              'Access-Control-Allow-Origin': '*',
            },
          });
        }
        return new Response('Not Found', { status: 404 });
      }

      const cacheControl = ext === '.json'
        ? 'no-cache'
        : 'public, max-age=3600';

      return new Response(resp.body, {
        status: 200,
        headers: {
          'Content-Type': contentType,
          'Cache-Control': cacheControl,
          'Access-Control-Allow-Origin': '*',
        },
      });
    } catch (err) {
      return new Response(`Error: ${err.message}`, { status: 500 });
    }
  },
};
