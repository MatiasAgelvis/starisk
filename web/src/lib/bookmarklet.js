// The `javascript:` bookmarklet, as source (IDEAS.md I1).
//
// Kept out of the page so the page does not hold a 4 KB string literal, and so
// the source is readable in the repository. `pages/bookmarklet.astro` turns it
// into the drag target.
//
// Two things make this possible at all, both verified against the live site:
//
//   - Coursera sends `content-security-policy: frame-ancestors 'self'` and
//     nothing else, so neither the `javascript:` URL nor a cross-origin fetch is
//     restricted by the page it runs on.
//   - `/data/badge.json` answers with `access-control-allow-origin: *`, and the
//     payload is ~24 KB gzipped instead of 765 KB for `/data/scores.json`.
//
// The only DOM coupling is Coursera's stable component names (`cds-*`) and the
// product hrefs. The hashed `css-*` classes are never referenced: they change
// every deploy. Every step is defensive — the failure mode is "no badge", never
// a broken page.

/**
 * @param {string} origin the deployed site, without a trailing slash
 * @returns {string} the bookmarklet body, ready to be percent-encoded
 */
export function bookmarkletSource(origin) {
  const base = String(origin).replace(/\/+$/, '');

  return `(function () {
  var ORIGIN = '${base}';
  var ATTR = 'data-starisk';
  var PRODUCT = /^\\/(learn|specializations|professional-certificates)\\/([a-z0-9][a-z0-9-]*)/;
  var FONT = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var NAVY = '#111827';
  var GOLD = '#fbbf24';

  function el(tag, css, text) {
    var node = document.createElement(tag);
    if (css) node.setAttribute('style', css);
    if (text != null) node.textContent = text;
    return node;
  }

  function tone(gap, onDark) {
    if (gap == null) return onDark ? '#9ca3af' : '#4b5563';
    if (gap >= 1.5) return onDark ? '#fca5a5' : '#b91c1c';
    if (gap >= 0.5) return onDark ? '#fdba74' : '#a64b08';
    return onDark ? '#86efac' : '#15803d';
  }

  function keyOf(path) {
    var match = PRODUCT.exec(path || '');
    return match ? match[1] + '/' + match[2] : null;
  }

  function siteHref(key) {
    return ORIGIN + (key.indexOf('learn/') === 0 ? '/' + key : '/programs/' + key);
  }

  function record(key) {
    var data = window.__stariskData;
    if (!data || !key) return null;
    return data.courses[key] || data.programs[key] || null;
  }

  function gapOf(item) {
    return item && typeof item.c === 'number' ? item.c - item.s : null;
  }

  function mark(size, plate) {
    // The favicon's mark, inlined: SVG in a page we do not own cannot come from a
    // component, and an <img> would be a second request and a second CSP surface.
    // plate false draws only the gold glyph, for places that are already navy.
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 32 32');
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('style', 'display:block;flex:none');

    if (plate !== false) {
      var rect = document.createElementNS(SVG_NS, 'rect');
      rect.setAttribute('width', '32');
      rect.setAttribute('height', '32');
      rect.setAttribute('rx', '7');
      rect.setAttribute('fill', NAVY);
      svg.appendChild(rect);
    }

    var glyph = document.createElementNS(SVG_NS, 'g');
    glyph.setAttribute('fill', 'none');
    glyph.setAttribute('stroke', GOLD);
    glyph.setAttribute('stroke-width', '3.2');
    glyph.setAttribute('stroke-linecap', 'round');

    ['M16 7.5v17', 'M8.6 11.7l14.8 8.6', 'M23.4 11.7l-14.8 8.6'].forEach(function (d) {
      var path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      glyph.appendChild(path);
    });

    svg.appendChild(glyph);
    return svg;
  }

  function chipFor(item, key) {
    var gap = gapOf(item);
    var chip = el('a', 'display:inline-flex;align-items:center;gap:5px;margin-top:4px;padding:1px 8px 1px 6px;border-radius:999px;background:' + NAVY + ';color:#fff;font:600 11px/1.7 ' + FONT + ';text-decoration:none;white-space:nowrap', null);
    chip.href = siteHref(key);
    chip.target = '_blank';
    chip.rel = 'noopener';
    chip.title = 'Starisk reads the upvoted reviews. ' +
      (gap == null ? 'No Coursera headline rating to compare.' : 'Coursera is ' + gap.toFixed(1) + ' higher.');
    chip.setAttribute(ATTR, '');
    chip.appendChild(mark(12, false));
    chip.appendChild(el('span', null, 'Starisk ' + item.s.toFixed(1)));
    if (gap != null) chip.appendChild(el('span', 'color:' + tone(gap, true) + ';font-weight:700', 'gap ' + gap.toFixed(1)));
    return chip;
  }

  function panel(key) {
    if (window.__stariskPanelKey === key) return;
    var existing = document.querySelector('[data-starisk-panel]');
    if (existing) existing.remove();
    window.__stariskPanelKey = key;

    var item = record(key);
    var gap = gapOf(item);
    var box = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483000;width:250px;box-sizing:border-box;padding:12px 14px;border:1px solid rgba(17,24,39,.14);border-radius:12px;background:#fdfdfc;color:' + NAVY + ';font:13px/1.5 ' + FONT + ';box-shadow:0 12px 32px rgba(17,24,39,.2);text-align:left', null);
    box.setAttribute('data-starisk-panel', '');

    var head = el('div', 'display:flex;align-items:center;gap:6px', null);
    head.appendChild(mark(16));
    head.appendChild(el('span', 'font:700 12px/1 ' + FONT + ';letter-spacing:.02em', 'Starisk'));
    var close = el('button', 'margin-left:auto;border:0;background:none;padding:0 2px;color:#9ca3af;font:400 16px/1 ' + FONT + ';cursor:pointer', '\\u00d7');
    close.type = 'button';
    close.title = 'Close';
    close.onclick = function () { box.remove(); };
    head.appendChild(close);
    box.appendChild(head);

    if (!item) {
      box.appendChild(el('div', 'margin-top:10px;font-size:12px;color:#6b7280', 'Not scored yet.'));
      var asked = window.__stariskData && window.__stariskData.wanted && window.__stariskData.wanted.indexOf(key) > -1;
      var ask = el('button', 'margin-top:10px;border:0;border-radius:8px;background:' + NAVY + ';color:#fff;font:600 12px/1 ' + FONT + ';padding:8px 12px;cursor:pointer', asked ? 'Already on the list' : 'Request a score');
      ask.type = 'button';
      if (asked) {
        ask.disabled = true;
        ask.style.opacity = '0.6';
        ask.style.cursor = 'default';
      } else {
        ask.onclick = function () {
          window.open(ORIGIN + '/request?key=' + encodeURIComponent(key), '_blank', 'noopener');
          ask.textContent = 'Requested';
          ask.disabled = true;
          ask.style.opacity = '0.6';
          ask.style.cursor = 'default';
        };
      }
      box.appendChild(ask);
      document.body.appendChild(box);
      return;
    }

    var line = el('div', 'display:flex;align-items:baseline;gap:6px;margin-top:10px', null);
    if (typeof item.c === 'number') {
      line.appendChild(el('span', 'color:#6b7280;font-size:12px', 'Coursera ' + item.c.toFixed(1)));
      line.appendChild(el('span', 'color:#9ca3af', '\\u2192'));
    }
    line.appendChild(el('span', 'font:700 18px/1.2 ' + FONT, item.s.toFixed(1)));
    box.appendChild(line);

    var bits = [];
    if (gap != null) bits.push('gap ' + gap.toFixed(1));
    if (typeof item.m === 'number') bits.push(item.n + ' of ' + item.m + ' courses read');
    else if (typeof item.n === 'number') bits.push(item.n + (item.n === 1 ? ' review read' : ' reviews read'));
    box.appendChild(el('div', 'margin-top:4px;font-size:12px;color:#6b7280', bits.join(' \\u00b7 ')));

    if (item.l) {
      box.appendChild(el('div', 'margin-top:4px;font-size:12px;color:#a64b08', 'Small sample: a hint, not a verdict.'));
    }

    var link = el('a', 'display:inline-block;margin-top:10px;font:600 12px/1 ' + FONT + ';color:#a64b08;text-decoration:none', 'See the reviews \\u2192');
    link.href = siteHref(key);
    link.target = '_blank';
    link.rel = 'noopener';
    box.appendChild(link);

    document.body.appendChild(box);
  }

  function countText(read, total) {
    return read === 0
      ? 'Starisk has read none of these ' + total
      : 'Starisk has read ' + read + ' of these ' + total;
  }

  function summary(total, read) {
    var existing = document.querySelector('[data-starisk-summary]');
    if (total === 0) {
      if (existing) existing.remove();
      return;
    }
    if (existing) {
      var out = existing.querySelector('[data-starisk-count]');
      if (out) out.textContent = countText(read, total);
      return;
    }

    var bar = el('div', 'position:fixed;right:16px;bottom:16px;z-index:2147483000;display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid rgba(17,24,39,.14);border-radius:999px;background:#fdfdfc;color:' + NAVY + ';font:600 12px/1 ' + FONT + ';box-shadow:0 12px 32px rgba(17,24,39,.2)', null);
    bar.setAttribute('data-starisk-summary', '');
    bar.appendChild(mark(16));

    var text = el('span', null, countText(read, total));
    text.setAttribute('data-starisk-count', '');
    bar.appendChild(text);

    var close = el('button', 'margin-left:2px;border:0;background:none;padding:0 2px;color:#9ca3af;font:400 14px/1 ' + FONT + ';cursor:pointer', '\\u00d7');
    close.type = 'button';
    close.title = 'Close';
    close.onclick = function () { bar.remove(); };
    bar.appendChild(close);

    document.body.appendChild(bar);
  }

  function scan() {
    var titles = document.querySelectorAll('a[href] > h3');
    var seen = {};
    var total = 0;
    var read = 0;

    for (var i = 0; i < titles.length; i++) {
      var link = titles[i].parentElement;
      if (!link) continue;
      var key = keyOf(link.getAttribute('href'));
      if (!key || seen[key]) continue;
      seen[key] = true;
      total++;

      var item = record(key);
      if (!item) continue;
      read++;

      var card = link.closest('[class*="cds-ProductCard"]');
      var host = (card && card.querySelector('.cds-CommonCard-metadata')) || link.parentElement;
      if (!host || host.querySelector('[' + ATTR + ']')) continue;
      host.appendChild(chipFor(item, key));
    }

    summary(total, read);
  }

  function render() {
    if (!window.__stariskData) return;

    var key = keyOf(location.pathname);
    if (key) {
      panel(key);
      return;
    }

    window.__stariskPanelKey = null;
    var existing = document.querySelector('[data-starisk-panel]');
    if (existing) existing.remove();
    scan();
  }

  function schedule() {
    if (window.__stariskTimer) return;
    window.__stariskTimer = setTimeout(function () {
      window.__stariskTimer = null;
      render();
    }, 600);
  }

  function boot() {
    if (window.__stariskData) {
      // A second click on the same page re-opens a panel that was closed. The
      // observer still skips re-adding it, because that path does not reset this.
      window.__stariskPanelKey = null;
      render();
      return;
    }

    fetch(ORIGIN + '/data/badge.json', { credentials: 'omit' })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) return;
        window.__stariskData = data;
        render();
        if (!window.__stariskObserver) {
          // Coursera is a single-page app and "Show more" appends cards, so the
          // scan has to run again. Debounced, and every insert is idempotent.
          window.__stariskObserver = new MutationObserver(schedule);
          window.__stariskObserver.observe(document.body, { childList: true, subtree: true });
        }
      })
      .catch(function () {});
  }

  window.__stariskBadge = boot;
  boot();
})();`;
}
