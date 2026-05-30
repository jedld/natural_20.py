#!/usr/bin/env node
/**
 * Build minified JS/CSS for webapp/static.
 * - Writes side-by-side .min.js / .min.css files
 * - Skips outputs newer than sources (incremental)
 * - Records content hashes in manifest.assets.json for cache busting
 */
import { build } from 'esbuild';
import { createHash } from 'crypto';
import { promises as fs } from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const staticDir = path.join(root, 'webapp', 'static');
const scanDirs = ['', 'js'];

async function findSourceFiles(dir, ext) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const suffix = `.min${ext}`;
  return entries
    .filter(
      (e) =>
        e.isFile()
        && e.name.endsWith(ext)
        && !e.name.endsWith(suffix)
        && !e.name.endsWith('.test.js')
    )
    .map((e) => path.join(dir, e.name));
}

async function needsRebuild(srcFile, outFile) {
  try {
    const [srcStat, outStat] = await Promise.all([fs.stat(srcFile), fs.stat(outFile)]);
    return srcStat.mtimeMs > outStat.mtimeMs;
  } catch {
    return true;
  }
}

async function minifyJs(file) {
  const outFile = file.replace(/\.js$/, '.min.js');
  if (!(await needsRebuild(file, outFile))) {
    return { file, outFile, skipped: true };
  }
  await build({
    entryPoints: [file],
    outfile: outFile,
    bundle: false,
    minify: true,
    sourcemap: false,
    target: ['es2018'],
    legalComments: 'none',
  });
  return { file, outFile, skipped: false };
}

async function minifyCss(file) {
  const outFile = file.replace(/\.css$/, '.min.css');
  if (!(await needsRebuild(file, outFile))) {
    return { file, outFile, skipped: true };
  }
  await build({
    entryPoints: [file],
    outfile: outFile,
    bundle: false,
    minify: true,
    loader: { '.css': 'css' },
  });
  return { file, outFile, skipped: false };
}

async function hashFile(filePath) {
  const buf = await fs.readFile(filePath);
  return createHash('sha256').update(buf).digest('hex').slice(0, 10);
}

async function main() {
  const jsFiles = [];
  const cssFiles = [];
  for (const sub of scanDirs) {
    const dir = path.join(staticDir, sub);
    try {
      jsFiles.push(...(await findSourceFiles(dir, '.js')));
      cssFiles.push(...(await findSourceFiles(dir, '.css')));
    } catch {
      // missing subdir
    }
  }

  if (jsFiles.length === 0 && cssFiles.length === 0) {
    console.log('No JS/CSS files found to minify.');
    return;
  }

  const results = [];
  for (const file of jsFiles) {
    results.push(await minifyJs(file));
  }
  for (const file of cssFiles) {
    results.push(await minifyCss(file));
  }

  const manifest = { files: {}, versions: {} };
  let built = 0;
  let skipped = 0;

  for (const { file, outFile, skipped: wasSkipped } of results) {
    const relSrc = path.relative(staticDir, file).replace(/\\/g, '/');
    const relOut = path.relative(staticDir, outFile).replace(/\\/g, '/');
    manifest.files[relSrc] = relOut;
    manifest.versions[relOut] = await hashFile(outFile);
    if (wasSkipped) {
      skipped += 1;
    } else {
      built += 1;
    }
  }

  manifest.generatedAt = new Date().toISOString();
  manifest.buildVersion = createHash('sha256')
    .update(JSON.stringify(manifest.versions))
    .digest('hex')
    .slice(0, 12);

  const manifestPath = path.join(staticDir, 'manifest.assets.json');
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

  const reportLines = ['Asset build complete:', `  built: ${built}`, `  up-to-date: ${skipped}`];
  for (const { file, outFile, skipped: wasSkipped } of results) {
    if (wasSkipped) continue;
    const [srcSize, outSize] = await Promise.all([
      fs.stat(file).then((s) => s.size),
      fs.stat(outFile).then((s) => s.size),
    ]);
    const pct = srcSize ? Math.round((1 - outSize / srcSize) * 100) : 0;
    reportLines.push(
      `  ${path.relative(staticDir, file)} → ${path.relative(staticDir, outFile)} (${pct}% smaller)`
    );
  }
  console.log(reportLines.join('\n'));
  console.log(`Manifest: ${path.relative(root, manifestPath)} (v=${manifest.buildVersion})`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
