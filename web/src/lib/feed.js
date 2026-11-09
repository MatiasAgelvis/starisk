// The request feed: a dated changelog of what people asked for and how it
// scored. Request-only by design — it is not a mirror of the whole catalogue.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' };

export function escapeXml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ESCAPES[character]);
}

/**
 * @param {Array<{ title: string, added_at: string, anchor: string, href: string,
 *   external?: boolean, summary?: string }>} rows newest first
 * @param {string} site absolute origin, e.g. `https://starisk.pages.dev`
 * @param {string | null} [snapshotAt] fallback `updated` for an empty feed
 */
export function buildFeed(rows, site, snapshotAt) {
  const base = String(site).replace(/\/+$/, '');
  const entries = rows.filter((row) => row.added_at).slice(0, 50);
  const updated = entries[0]?.added_at ?? snapshotAt ?? '1970-01-01T00:00:00Z';

  return `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Starisk — wanted</title>
  <subtitle>Courses readers asked for, and how they scored.</subtitle>
  <id>${base}/wanted</id>
  <link href="${base}/feed.xml" rel="self" />
  <link href="${base}/wanted" />
  <updated>${escapeXml(updated)}</updated>
  <author><name>Starisk</name></author>
${entries
  .map((row) => {
    const href = row.external ? row.href : `${base}${row.href}`;
    return `  <entry>
    <title>${escapeXml(row.title)}</title>
    <id>${base}/wanted#${escapeXml(row.anchor)}</id>
    <link href="${escapeXml(href)}" />
    <updated>${escapeXml(row.added_at)}</updated>
    <published>${escapeXml(row.added_at)}</published>
    <summary>${escapeXml(row.summary)}</summary>
  </entry>`;
  })
  .join('\n')}
</feed>
`;
}
