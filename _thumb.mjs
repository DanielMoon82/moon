// toon/cNN.jpg 썸네일 생성 — 표지 1080x1350 을 목록 페이지용으로 줄인다
import pw from 'file:///C:/Users/user/naver-blog-auto/node_modules/playwright/index.js';
import fs from 'fs';
const W = 360, H = 450;
const b = await pw.chromium.launch();
const page = await b.newPage({ viewport: { width: W, height: H } });
for (let i = 2; i < process.argv.length; i += 2) {
  const src = 'file:///' + process.argv[i].split(String.fromCharCode(92)).join('/');
  const out = process.argv[i + 1];
  const tmp = 'C:/Users/user/Desktop/moon/_thumb.html';
  fs.writeFileSync(tmp, `<!doctype html><meta charset=utf-8><style>*{margin:0}body{width:${W}px;height:${H}px;overflow:hidden}img{width:${W}px;height:${H}px;object-fit:cover;display:block}</style><img src="${src}">`, 'utf8');
  await page.goto('file:///' + tmp);
  await page.waitForTimeout(400);
  await page.screenshot({ path: out, type: 'jpeg', quality: 82 });
  console.log('thumb', out, fs.statSync(out).size, 'bytes');
}
await b.close();
