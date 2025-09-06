#!/usr/bin/env node
/**
 * Minify JS assets in webapp/static into .min.js files using esbuild.
 * - Processes top-level JS files and files under webapp/static/js
 * - Writes side-by-side .min.js files and a small manifest.json for debugging
 */
import { build } from 'esbuild';
import { promises as fs } from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const staticDir = path.join(root, 'webapp', 'static');
const subDirs = ['', 'js'];

async function findJsFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries
    .filter(e => e.isFile() && e.name.endsWith('.js') && !e.name.endsWith('.min.js') && !e.name.endsWith('.test.js'))
    .map(e => path.join(dir, e.name));
}

async function main() {
  const files = [];
  for (const sd of subDirs) {
    const dir = path.join(staticDir, sd);
    try {
      const found = await findJsFiles(dir);
      files.push(...found);
    } catch (e) {
      // ignore missing subdir
    }
  }

  if (files.length === 0) {
    console.log('No JS files found to minify.');
    return;
  }

  const manifest = {};
  await Promise.all(files.map(async (file) => {
    const outFile = file.replace(/\.js$/, '.min.js');
    await build({
      entryPoints: [file],
      outfile: outFile,
      bundle: false,
      minify: true,
      sourcemap: false,
      target: ['es2018']
    });
    manifest[path.relative(staticDir, file)] = path.relative(staticDir, outFile);
  }));

  const manifestPath = path.join(staticDir, 'manifest.assets.json');
  await fs.writeFile(manifestPath, JSON.stringify({ generatedAt: new Date().toISOString(), files: manifest }, null, 2));
  console.log(`Minified ${files.length} files. Manifest at ${path.relative(root, manifestPath)}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
