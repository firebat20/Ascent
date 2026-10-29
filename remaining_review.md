# Ascent Project Review — Remaining Files

## Summary

Cross-referenced [`README.md`](file:///c:/Codes/Ascent/README.md), [`.gitignore`](file:///c:/Codes/Ascent/.gitignore), and [`buildRelease.yml`](file:///c:/Codes/Ascent/.github/workflows/buildRelease.yml) against [`settings.json`](file:///c:/Codes/Ascent/src/settings.json). Found **6 issues**.

---

## 🔴 README Table Out of Sync with `settings.json`

The "Featuring" table in [`README.md`](file:///c:/Codes/Ascent/README.md#L33-L55) doesn't match the actual package definitions in `settings.json`. Here's what's wrong:

### 1. `ldn_mitm` is listed in the README Advanced column — but it's NOT in any `settings.json` package

The `ldn_mitm` module is defined in `moduleList` but **no package references it**. The README shows it as part of Advanced, which is incorrect.

> [!IMPORTANT]
> Either add `"ldn_mitm"` to the advanced package's modules list in `settings.json`, or remove it from the README table.

### 2. Broken markdown table rows — missing trailing column separators

Lines 49 and 50 have only 3 columns instead of 4, which breaks the table rendering:

```diff
 # README.md lines 49-50
-| [Status Monitor Overlay](https://github.com/masagrator/Status-Monitor-Overlay) | ✅ |  |
-| [sys-patch](https://github.com/impeeza/sys-patch) | ✅ |  |
+| [Status Monitor Overlay](https://github.com/masagrator/Status-Monitor-Overlay) | ✅ |  |  |
+| [sys-patch](https://github.com/impeeza/sys-patch) | ✅ |  |  |
```

### 3. Stale repo links in README

The README links to upstream repos, but `settings.json` uses forks for some modules:

| Module | README links to | `settings.json` uses |
|--------|----------------|---------------------|
| sys-clk | `retronx-team/sys-clk` | `exploitz86/sys-clk` |
| sys-con | `cathery/sys-con` | `exploitz86/sys-con` |

The README even notes these are "temporarily forked" (line 58), but the links in the table point to the **original** repos instead of the forks that are actually used. Consider updating:

```diff
-| [sys-clk](https://github.com/retronx-team/sys-clk) | ✅ |  |  |
+| [sys-clk](https://github.com/exploitz86/sys-clk) | ✅ |  |  |
-| [sys-con](https://github.com/cathery/sys-con) | ✅ |  |  |
+| [sys-con](https://github.com/exploitz86/sys-con) | ✅ |  |  |
```

---

## 🟡 `.gitignore` — Missing `src/menv/` entry

The gitignore covers `src/base/*`, `src/sd/*`, and `src/*.zip`, but **not** `src/menv/` — the temporary module environment directory used during builds. If someone runs the build locally and it errors mid-way, the `menv` directory would show up as untracked in git.

```diff
 src/base/*
 src/tmp/*
 src/sd/*
 src/*.zip
+src/menv/*
```

---

## 🟡 Workflow — `hub` CLI is deprecated

The workflow uses [`hub release create`](file:///c:/Codes/Ascent/.github/workflows/buildRelease.yml#L43-L45) to create releases. The `hub` CLI has been **deprecated** in favor of the official `gh` CLI, which comes pre-installed on GitHub-hosted runners. This means:
- `sudo apt install hub -y` is an unnecessary step that may eventually fail when the package is removed
- `gh` is already available — no install needed

> [!NOTE]
> This isn't broken *yet*, but `hub` hasn't been maintained since 2023. Worth migrating to `gh` when convenient.

---

## 🟢 Files That Look Good

- **`.gitignore`** — comprehensive Python gitignore, covers build artifacts correctly (except `menv`)
- **`assets/banner.png`** — present and referenced correctly by README
- **`CODE_OF_CONDUCT.md`** / **`LICENSE.md`** — standard files, no issues
- **Workflow trigger** — correctly fires on `src/version.json` changes (which you just bumped to `5.00.0`)

---

## Recommended Priority

| Priority | Issue | File | Action |
|----------|-------|------|--------|
| 🔴 **Fix now** | Table rows missing column separators | `README.md:49-50` | Add trailing ` \| ` |
| 🔴 **Fix now** | `ldn_mitm` in README but not in any package | `README.md:45` / `settings.json` | Add to advanced package or remove from table |
| 🟡 **Should fix** | sys-clk/sys-con links point to upstream, not forks | `README.md:51-52` | Update URLs to fork repos |
| 🟡 **Should fix** | Missing `src/menv/*` in gitignore | `.gitignore` | Add entry |
| 🟢 **Nice to have** | Migrate `hub` → `gh` CLI in workflow | `buildRelease.yml` | Replace when convenient |
