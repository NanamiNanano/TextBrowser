// 从华为云 PyPI 镜像拉取 win_amd64 轮子（不依赖 pip；带进度与超时）
// 用法: node fetch_wheels.cjs <输出目录> <包名...>
const fs = require('fs');
const path = require('path');
const { pipeline } = require('stream/promises');
const { Readable } = require('stream');

const MIRROR = 'https://repo.huaweicloud.com/repository/pypi/simple/';
const outDir = process.argv[2];
const pkgs = process.argv.slice(3);
fs.mkdirSync(outDir, { recursive: true });

const parseVer = f => {
  // 轮子文件名形如 <name>-<version>-<pytag>-<abi>-<plat>.whl。
  // 版本可能是 6.12.0 / 2024.11 / 2024.8.26 等形态，统一取「名字后第一段」，
  // 原来写死 \d+\.\d+\.\d+ 会把 2024.11 这种两段式版本解析成 0，导致选到旧版本。
  const m = f.match(/^(.+?)-(\d[^-]*)-(py|cp|pp)\d/i);
  if (!m) return [0];
  return m[2].split('.').map(n => parseInt(n, 10) || 0);
};
const cmpVer = (a, b) => {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] || 0) - (b[i] || 0);
    if (d) return d;
  }
  return 0;
};
const score = f => {
  let s = 0;
  if (/cp312-cp312/.test(f)) s += 100;
  if (/abi3/.test(f)) s += 50;
  if (/none-win_amd64\.whl$/.test(f)) s += 45;
  if (/none-any\.whl$/.test(f)) s += 40;      // 纯 Python 包（pyinstaller 等）
  if (/cp312/.test(f)) s += 20;
  return s;
};

async function getPage(pkg) {
  const c = new AbortController();
  const id = setTimeout(() => c.abort(), 20000);
  const r = await fetch(MIRROR + pkg + '/', { signal: c.signal, redirect: 'follow' });
  clearTimeout(id);
  if (!r.ok) throw new Error(`index HTTP ${r.status}`);
  return await r.text();
}

function parseLinks(html, pageUrl) {
  // 只抓 .whl 链接：锚点里常有 data-requires-python=">=3.10" 这类含 '>' 的属性，
  // 按整段 <a ...> 解析会被截断，所以直接匹配 href 值。
  const out = [];
  const re = /href="([^"]*\.whl[^"]*)"/g;
  let m;
  while ((m = re.exec(html))) {
    let raw = m[1].replace(/&amp;/g, '&').split('#')[0];
    const href = new URL(raw, pageUrl).href;
    const name = decodeURIComponent(href.substring(href.lastIndexOf('/') + 1));
    out.push({ href, name });
  }
  return out;
}

async function headSize(url) {
  try {
    const c = new AbortController();
    const id = setTimeout(() => c.abort(), 20000);
    const r = await fetch(url, { method: 'HEAD', signal: c.signal, redirect: 'follow' });
    clearTimeout(id);
    return Number(r.headers.get('content-length') || 0);
  } catch (e) { return 0; }
}

async function download(url, dest, label) {
  const t0 = Date.now();
  const c = new AbortController();
  const id = setTimeout(() => c.abort(), 300000);
  const r = await fetch(url, { signal: c.signal, redirect: 'follow' });
  clearTimeout(id);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const total = Number(r.headers.get('content-length') || 0);
  let got = 0, last = 0;
  const ws = fs.createWriteStream(dest);
  const src = Readable.fromWeb(r.body);
  src.on('data', ch => {
    got += ch.length;
    if (got - last > 8 * 1048576 || got === total) {
      last = got;
      const sp = got / 1048576 / ((Date.now() - t0) / 1000);
      process.stdout.write(`  ${label}: ${(got / 1048576).toFixed(1)}/${(total / 1048576).toFixed(1)} MB  ${sp.toFixed(2)} MB/s\n`);
    }
  });
  await pipeline(src, ws);
  const dt = (Date.now() - t0) / 1000;
  console.log(`${label}: 完成 ${(got / 1048576).toFixed(1)} MB / ${dt.toFixed(1)}s`);
}

(async () => {
  for (const p of pkgs) {
    const html = await getPage(p);
    const links = parseLinks(html, MIRROR + p + '/').filter(l => /(win_amd64|none-any)\.whl$/.test(l.name));
    if (!links.length) { console.log(`${p}: 镜像里没有 win_amd64 轮子`); continue; }
    links.sort((a, b) => cmpVer(parseVer(b.name), parseVer(a.name)) || score(b.name) - score(a.name));
    const best = links.find(l => score(l.name) >= 40) || links[0];
    const dest = path.join(outDir, best.name);
    const expect = await headSize(best.href);
    const have = fs.existsSync(dest) ? fs.statSync(dest).size : -1;
    if (expect > 0 && have === expect) {
      console.log(`${p}: 已存在且大小校验通过 ${best.name} (${(have / 1048576).toFixed(1)} MB)`);
      continue;
    }
    if (have > 0) console.log(`${p}: 本地文件不完整 (${(have / 1048576).toFixed(1)}/${(expect / 1048576).toFixed(1)} MB)，重新下载`);
    console.log(`${p}: 选中 ${best.name}`);
    await download(best.href, dest, p);
  }
  console.log('\n本地轮子:');
  for (const f of fs.readdirSync(outDir).filter(f => f.endsWith('.whl'))) {
    console.log('  %s  %s MB', f.padEnd(62), (fs.statSync(path.join(outDir, f)).size / 1048576).toFixed(1));
  }
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
