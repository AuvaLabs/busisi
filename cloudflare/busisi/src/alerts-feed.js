import { SITE } from './prelaunch-config.js';

const xml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&apos;');

const absolute = (path) => new URL(path, SITE.origin).toString();

const item = (record) => `<item>
  <title>${xml(record.title)}</title>
  <link>${xml(absolute(record.url))}</link>
  <guid isPermaLink="false">${xml(`busisi:${record.id}`)}</guid>
  <pubDate>${xml(new Date(record.published_at).toUTCString())}</pubDate>
  <category>${xml(record.kind)}</category>
  <description>${xml(`${record.summary} ${record.boundary}`)}</description>
</item>`;

export const alertsRss = (records) => {
  const latest = records[0]?.published_at || '2026-01-01T00:00:00Z';
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>Busisi evidence updates</title>
  <link>${SITE.origin}/watch/</link>
  <description>Checked source, coverage, evidence, and review-question updates from Busisi.</description>
  <language>en-PH</language>
  <lastBuildDate>${xml(new Date(latest).toUTCString())}</lastBuildDate>
  <atom:link href="${SITE.origin}/feeds/updates.xml" rel="self" type="application/rss+xml" />
  ${records.map(item).join('\n  ')}
</channel>
</rss>\n`;
};
