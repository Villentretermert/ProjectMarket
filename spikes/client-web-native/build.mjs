import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';

await mkdir('dist', { recursive: true });
await build({entryPoints: ['web/app.js'], bundle: true, format: 'esm', outfile: 'dist/app.js', minify: true});
for (const name of ['index.html', 'styles.css', 'sw.js']) await copyFile(`web/${name}`, `dist/${name}`);
console.log('Local Web bundle ready in dist; no CDN resources.');
