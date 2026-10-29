# Ascent Python Code Review

## Summary

I reviewed all 4 Python scripts: [`fs.py`](file:///c:/Codes/Ascent/src/fs.py), [`gh.py`](file:///c:/Codes/Ascent/src/gh.py), [`start.py`](file:///c:/Codes/Ascent/src/start.py), and [`version_tracker.py`](file:///c:/Codes/Ascent/src/version_tracker.py), plus the [`settings.json`](file:///c:/Codes/Ascent/src/settings.json) configuration. Found **1 bug**, **3 data issues**, and **several code quality improvements**.

---

## 🐛 Bug

### 1. Typo in `settings.json` — `"createDir"` should be `"create_dir"` (hekate module)

The `executeStep` method in [`fs.py`](file:///c:/Codes/Ascent/src/fs.py#L25-L46) uses `create_dir` (with underscore), but the hekate module in [`settings.json`](file:///c:/Codes/Ascent/src/settings.json#L125) uses `createDir` (camelCase). **This step silently does nothing** — no directory is created and no error is raised because `executeStep` uses a chain of independent `if` statements.

```diff
 # settings.json, line 125 (hekate steps)
-                "name": "createDir",
+                "name": "create_dir",
```

> [!CAUTION]
> This means the hekate module's `atmosphere` directory is never explicitly created during its processing. It may still work if the directory happens to exist from a prior extract step or from the atmosphere module running first, but it's unreliable and order-dependent.

---

## ⚠️ Data/Config Issues

### 2. `gh.py` — bare `except` clause swallows all exceptions

In [`gh.py:16`](file:///c:/Codes/Ascent/src/gh.py#L16), the bare `except:` catches everything including `KeyboardInterrupt` and `SystemExit`. Should be `except Exception:`.

```diff
 # gh.py, line 16
-        except:
+        except Exception:
```

### 3. `gh.py` — `downloadReleaseAssets` inconsistent return values

[`downloadReleaseAssets`](file:///c:/Codes/Ascent/src/gh.py#L13-L44) returns `True` on success but implicitly returns `None` on all error paths (lines 18, 23, 35). The caller in `start.py` never checks the return value, so this isn't breaking, but it's sloppy — a failed download silently continues to the build phase and will produce a broken/incomplete package.

### 4. `fs.py` — `__replaceFileContent` doesn't use context managers

[`__replaceFileContent`](file:///c:/Codes/Ascent/src/fs.py#L83-L90) opens the file twice without `with` statements. If an error occurs between reads/writes, the file handle leaks.

```diff
     def __replaceFileContent(self, source, search, replace):
-        fin = open(f"./menv/{source}", "rt")
-        data = fin.read()
-        data = data.replace(search, replace)
-        fin.close()
-        fin = open(f"./menv/{source}", "wt")
-        fin.write(data)
-        fin.close()
+        with open(f"./menv/{source}", "rt") as fin:
+            data = fin.read()
+        data = data.replace(search, replace)
+        with open(f"./menv/{source}", "wt") as fout:
+            fout.write(data)
```

---

## 💡 Code Quality Improvements

### 5. `fs.py` — `executeStep` should use `elif` chain or a dispatch dict

The [chain of independent `if` statements](file:///c:/Codes/Ascent/src/fs.py#L25-L46) means every condition is checked even after a match. This also contributed to the silent bug above — an unrecognized step name just falls through. An `elif` chain with a final `else` would catch unknown steps:

```python
def executeStep(self, module, step):
    name = step["name"]
    args = step["arguments"]

    if name == "extract":
        self.__extract(args[0])
    elif name == "create_dir":
        self.__createDir(args[0])
    elif name == "create_file":
        self.__createFile(args[0], args[1])
    elif name == "replace_content":
        self.__replaceFileContent(args[0], args[1], args[2])
    elif name == "delete":
        self.__delete(args[0])
    elif name == "copy":
        self.__copy(args[0], args[1])
    elif name == "move":
        self.__copy(args[0], args[1])
        self.__delete(args[0])
    else:
        logging.warning(f"Unknown step: {name}")
```

### 6. `start.py` — inconsistent indentation (2 spaces vs 4)

[`start.py`](file:///c:/Codes/Ascent/src/start.py) uses **2-space indentation** throughout, while all other files use **4-space indentation** (PEP 8 standard). Not breaking, but inconsistent across the project.

### 7. `fs.py` — unused `logging` import

[`logging`](file:///c:/Codes/Ascent/src/fs.py#L1) is imported but never used in `fs.py`. Minor cleanup, but would become useful if the `else` clause from suggestion #5 is added.

### 8. `gh.py` — `urllib.request` for downloads (no auth, no progress)

[`urllib.request.urlretrieve`](file:///c:/Codes/Ascent/src/gh.py#L43) downloads assets without authentication. This works for public repos, but will fail for private release assets. Since you already have a `Github` instance, you could use the PyGithub API or pass the token as a header for authenticated downloads.

---

## ✅ Things That Look Good

- **`version_tracker.py`** — well-structured, proper exception handling, good docstrings, and clean separation of concerns
- **Overall architecture** — clean module separation between FS operations, GitHub interactions, and orchestration
- **`settings.json`** — well-organized configuration with clear module definitions and step sequences
- **GitHub Actions workflow** — solid CI/CD setup with draft releases, version overrides, and auto-commit of version tracking

---

## Recommended Priority

| Priority | Issue | File | Impact |
|----------|-------|------|--------|
| 🔴 **Fix now** | `createDir` → `create_dir` typo | `settings.json:125` | Hekate step silently skipped |
| 🟡 **Should fix** | Bare `except` clause | `gh.py:16` | Can mask real errors |
| 🟡 **Should fix** | File handle leak in `__replaceFileContent` | `fs.py:83-90` | Resource leak on error |
| 🟢 **Nice to have** | `elif` chain + unknown step warning | `fs.py:25-46` | Prevents future silent bugs |
| 🟢 **Nice to have** | Consistent indentation | `start.py` | Code style consistency |
