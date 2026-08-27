# design-sync notes for andyhub-web

First sync: 2026-08-27. Project `Proof Garden`, id `a59a46bd-1bd0-46e8-837b-9655f7f6ef32`.

## Scope decision: tokens-only, deliberately

This package is a Next.js **application**, not a design-system package (`private: true`, no `main`, no `exports`, no `dist/`). `components/ui/` is empty; the 10 components under `components/` are feature-level screens (`StudySession`, `DeckWorkshop`, `GenerationTrace`), not composable primitives. Uploading them would hand the design agent finished screens it cannot build with.

Dawn chose a tokens-only sync on 2026-08-27. Every component is excluded via `componentSrcMap` nulls, so the build reports `[ZERO_MATCH] no component exports - treating as tokens-only DS`, which is the documented supported path. **That `[ZERO_MATCH]` line is expected, not a failure.**

`QueryProvider` is also excluded: it is React Query plumbing, not a design component.

## Gotchas that cost real time

- **`.pytest_cache` is damaged.** It exists, raises `EPERM` on scandir, and cannot be deleted (`rmdir` returns Access denied). Almost certainly filesystem damage from the repeated PC crashes in Aug 2026. `lib/detect.mjs` walks the tree **before** `cfg.shape` is applied, so pinning `shape: "package"` does not avoid it and the build dies. Worked around by the fork below. **A `chkdsk` on D: is the real fix**; once the directory is gone, delete `.design-sync/overrides/detect.mjs` and its `cfg.libOverrides` entry.
- **`lib/detect.mjs` fork** (`libOverrides`): wraps the per-directory read in try/catch so an unreadable directory is skipped with a warning instead of aborting. Only change from upstream, plus the import repointed at `../../.ds-sync/lib/common.mjs`.
- **The package must self-resolve.** `dts.mjs` computes `PKG_DIR` as `node_modules/<pkg>`, which npm never self-installs, so the build fails with `ENOENT ... node_modules/andyhub-web/package.json`. Fix is a junction:

  ```powershell
  New-Item -ItemType Junction -Path "node_modules\andyhub-web" -Target "D:\Personal Projects\All In One Reviewer\apps\web"
  ```

  **Remove it again after the sync.** A self-referential entry inside `node_modules` can send webpack/tsc file walkers into recursion. It is not committed and must be recreated on every sync.
- **Playwright**: chromium builds 1228 and 1234 were already cached under `%LOCALAPPDATA%\ms-playwright`, so no 200MB download was needed. `npm i playwright` into `.ds-sync/` pins build 1234, which matched. Do the same on re-sync rather than installing browsers.
- **Node 24.16.0**, npm 11.13.0, lockfile is `package-lock.json`.

## Known render warns

- `[FONT_REMOTE]` for "Atkinson Hyperlegible Next", "Familjen Grotesk", "IBM Plex Mono". Expected and correct: `globals.css` carries a Google Fonts `@import` that serves all three at runtime. No action, do not wire `extraFonts`.

## Re-sync risks

- **The conventions header is the deliverable here, more than the tokens.** `.design-sync/conventions.md` holds the anti-generated-design constraint list that gets inlined into the design agent's system prompt. It names 16 tokens; every one was verified against the built `_ds_bundle.css`. If `app/globals.css` gains or renames a token, the header goes stale silently and the agent will write vocabulary that does not resolve. Re-validate the names on every sync.
- **The scope decision expires.** If a real `components/ui/` primitives layer is ever built (extracted from the 1043 lines of CSS modules), the tokens-only decision should be revisited and components synced properly. That was scoped as a post-Aug-31 project, not abandoned.
- **Nothing was render-verified**, because there are zero component previews. `render check: 0/0` is honest, not a skipped gate.
- **The junction and the `.pytest_cache` fork are both environment state**, not repo truth. A different machine will not have the damaged directory and should not need the fork; a fresh clone will need the junction recreated.
