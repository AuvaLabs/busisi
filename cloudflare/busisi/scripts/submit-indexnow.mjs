import { INDEX_NOW_KEY, SITE } from '../src/prelaunch-config.js';

const origin = process.env.BUSISI_ORIGIN ?? SITE.origin;
const key = INDEX_NOW_KEY;
const keyLocation = `${origin}/${key}.txt`;
const paths = [
  '/',
  '/explore/',
  '/agencies/',
  '/changes/',
  '/signals/',
  '/integrity/',
  '/methodology/',
  '/projects/corazon-2022-combined/',
  '/projects/agoncillo-2023/',
  '/projects/corazon-2024-phase-1/',
  '/projects/corazon-2024-phase-2/',
  '/projects/corazon-2025-completion/',
];
const urlList = paths.map((path) => `${origin}${path}`);

const verifyKey = async () => {
  const response = await fetch(keyLocation);
  if (!response.ok || (await response.text()).trim() !== key) {
    throw new Error(`IndexNow key verification failed with HTTP ${response.status}`);
  }
};

const submit = async () => {
  await verifyKey();
  const response = await fetch('https://api.indexnow.org/indexnow', {
    method: 'POST',
    headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify({
      host: new URL(origin).hostname,
      key,
      keyLocation,
      urlList,
    }),
  });
  if (![200, 202].includes(response.status)) {
    throw new Error(`IndexNow submission failed with HTTP ${response.status}`);
  }
  console.log(JSON.stringify({ passed: true, status: response.status, urlList }, null, 2));
};

submit().catch((error) => {
  console.error(JSON.stringify({ passed: false, error: error.message }, null, 2));
  process.exitCode = 1;
});
