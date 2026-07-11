# Catalyst Deployment — What Actually Works (learned the hard way)

**LIVE:** https://kaveri-backend-50043711203.development.catalystappsail.in

This guide records the **real** constraints of Catalyst AppSail (Catalyst-Managed Python runtime),
discovered by deploying, failing, and diagnosing. If you're deploying a Python app on Catalyst,
read this before you burn five deploy cycles like we did.

---

## ⚠️ The three gotchas that break Python deploys on Catalyst

### 1. Catalyst does NOT run `pip install -r requirements.txt`
This is the big one. AppSail **copies your files and runs your startup command — that's it.**
No dependency installation happens. Your `requirements.txt` is ignored.

**Symptom:** deploy says "Success", but the app has **0 running instances** and **no logs at all**.
The URL returns `"Execution failed. Please check the startup command or port."` The app is dying on
its very first `import flask` before it can log anything.

**Fix:** bundle your dependencies with the app.
```bash
pip install --target=./vendor flask networkx jellyfish
```
Then, at the very top of `main.py`, **before any third-party import**:
```python
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "vendor"))   # MUST come first
from flask import Flask                             # now this works
```
⚠️ Build the `vendor/` folder on **Linux x86-64 with the same Python minor version (3.12)** as the
Catalyst runtime, or compiled extensions (`.so` files) won't load.

### 2. Disk is capped (256 MB by default) — the sklearn stack does NOT fit
`scikit-learn + numpy + scipy` = **~290 MB vendored**. Over the limit. It cannot be deployed.

**Fix:** we removed scikit-learn entirely. `06_retrieval/pure_tfidf.py` reimplements
`TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1)` + `cosine_similarity` in pure
Python with zero dependencies — and reproduces sklearn's output (verified: identical similarity
scores; ER still 1.000/1.000). **290 MB → 0 MB, no loss in results.**

Final deploy size: **25 MB**.

### 3. The startup command needs `python3`, and there is no shell
Catalyst's Linux runtime has `python3`, not `python`. And AppSail executes the startup command
**directly, with no shell**, so there's no PATH fallback.

Correct `app-config.json`:
```json
{
    "command": "python3 -u main.py",
    "build_path": ".",
    "stack": "python_3_12",
    "env_variables": {},
    "memory": 1024,
    "scripts": {}
}
```
The `-u` flag unbuffers output so Python errors actually reach the logs.

---

## Other things worth knowing
- **Port:** Catalyst provides it via env var `X_ZOHO_CATALYST_LISTEN_PORT` (default 9000). Read it:
  ```python
  port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", 9000))
  app.run(host="0.0.0.0", port=port)
  ```
- **App directory IS writable** (contrary to some doc phrasing) — but don't rely on it. We generate
  the synthetic CSVs at **build time** and ship them, so startup is fast (~2s) and does no I/O.
- **Console settings override `app-config.json`.** Check
  *Serverless → AppSail → your app → Startup Command / App Execution Settings*.
- **Build once at startup, not per request.** The graph build takes ~2s; do it at module load and
  hold it in memory. Every HTTP request then queries the already-built graph.
- **SQLite across threads:** a web server serves requests on worker threads, so an in-memory SQLite
  connection built at startup needs `check_same_thread=False` or every request crashes.

---

## 🔍 The debugging trick that actually solved it
When the deploy "succeeds" but there are no logs and no instances, deploy a **stdlib-only
diagnostic** — an app with *zero* third-party imports, so it cannot fail to start. Have it report
what the runtime actually has. It found the real bug in one shot after four wrong guesses.

See `diagnostic_main.py` (kept in the repo for exactly this purpose). It reports: Python version,
working directory, files present, whether the directory is writable, the port env var, and — the
key part — **which dependencies are actually importable.**

---

## Deploy steps
```bash
# 1. Generate the data CSVs (shipped with the app; not generated at runtime)
cd 01_data_generator && python generate.py && cd ..

# 2. Vendor the dependencies (MUST be Linux x86-64, Python 3.12)
pip install --target=./vendor flask networkx jellyfish

# 3. Deploy
catalyst deploy
```

## Verify the live deployment
- `/` → `{"status": "live", "cases_loaded": 500, "resolved_identity_groups": 5}`
- `/investigate/1` → full cited brief: network `[2,3,4,5,7,10,13]`, 13 near-repeat burglaries, 3 leads
- `/identity/17` → Kannada variants resolved: ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು
- `POST /query` → `{"query":"show the network for this case","case_id":1}`

## Still to do (production upgrades)
- **Neo4j** as a separate AppSail container (Cypher already written in `graph_store.py`)
- **Catalyst QuickML** served LLM (set `CATALYST_LLM_ENDPOINT` / `CATALYST_LLM_TOKEN`)
- **Catalyst Data Store** to replace SQLite; **Catalyst NoSQL** for durable audit
- **Frontend** on Catalyst Slate, wired to this API
- Flask's dev server is used; for real traffic bundle `waitress` into `vendor/` and serve with it.
