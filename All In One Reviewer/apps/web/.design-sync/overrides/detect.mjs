// forked from design-sync lib/detect.mjs - tolerate unreadable dirs (EPERM) during the storybook walk
//
// Why: apps/web contains a damaged `.pytest_cache` directory that exists but
// raises EPERM on scandir and cannot be deleted (Access denied), almost
// certainly filesystem damage from the repeated PC crashes in Aug 2026.
// The upstream walk lets that throw and kills the build before `cfg.shape`
// is ever applied, so pinning shape="package" cannot avoid it.
//
// The only change is the try/catch around the per-directory read. An
// unreadable directory is skipped with a warning instead of aborting the run.
// Once the filesystem is repaired (chkdsk) this fork can be deleted along with
// its cfg.libOverrides entry.

import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { ls } from '../../.ds-sync/lib/common.mjs';

// Enumerate .storybook/ config dirs under root (depth-limited, skips
// node_modules). Some DSes use `storybook/` (no dot) - match any dir with a
// main.* file.
export function findStorybookDirs(root, depth = 4) {
  const out = [];
  const isConfigDir = (p) =>
    ['ts', 'js', 'mjs', 'cjs'].some((e) => existsSync(join(p, `main.${e}`)));
  (function walk(d, lvl) {
    if (lvl > depth || !existsSync(d)) return;
    let entries;
    try {
      entries = ls(d, { withFileTypes: true });
    } catch (err) {
      console.error(`  [DETECT] skipping unreadable dir ${d} (${err.code ?? err.message})`);
      return;
    }
    for (const e of entries) {
      if (!e.isDirectory() || e.name === 'node_modules') continue;
      const p = join(d, e.name);
      if ((e.name === '.storybook' || e.name === 'storybook') && isConfigDir(p)) out.push(p);
      else walk(p, lvl + 1);
    }
  })(root, 0);
  return out;
}

export function detectShape({ INPUTS, SB_STATIC, SB_CONFIG_DIR }) {
  if (SB_STATIC || SB_CONFIG_DIR) {
    console.error(`[DETECT] shape=storybook (explicit ${SB_STATIC ? '--storybook-static' : '--storybook-config'})`);
    return 'storybook';
  }
  const found = findStorybookDirs(INPUTS, 4);
  const shape = found.length ? 'storybook' : 'package';
  console.error(`[DETECT] searched ${INPUTS} (depth 4), found .storybook at [${found.join(', ')}] → shape=${shape}`);
  return shape;
}
