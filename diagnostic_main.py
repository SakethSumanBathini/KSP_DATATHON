"""
KAVERI — Catalyst DIAGNOSTIC.
Uses ONLY Python standard library (zero third-party imports), so it WILL start if the
platform/startup-command/port are working at all. It then reports what the runtime
actually has, which tells us exactly why the real app won't boot.
"""
import os, sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer


def check(mod):
    try:
        m = __import__(mod)
        v = getattr(m, "__version__", "?")
        return f"OK ({v})"
    except Exception as e:
        return f"MISSING -> {type(e).__name__}: {e}"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            files = sorted(os.listdir("."))
        except Exception as e:
            files = [f"listdir failed: {e}"]

        # can we see the component folders and the CSVs?
        gen_dir = os.path.join(os.getcwd(), "01_data_generator")
        csvs = []
        if os.path.isdir(gen_dir):
            csvs = sorted(f for f in os.listdir(gen_dir) if f.endswith(".csv"))

        # is the app dir writable? (Catalyst says no — confirm)
        writable = "unknown"
        try:
            p = os.path.join(os.getcwd(), "_write_test.tmp")
            with open(p, "w") as fh:
                fh.write("x")
            os.remove(p)
            writable = "YES (writes allowed)"
        except Exception as e:
            writable = f"NO -> {type(e).__name__}: {e}"

        info = {
            "DIAGNOSTIC": "if you can read this, the platform + startup command + port all WORK",
            "python_version": sys.version,
            "cwd": os.getcwd(),
            "files_in_app_dir": files[:50],
            "csv_files_found": len(csvs),
            "csv_sample": csvs[:5],
            "app_dir_writable": writable,
            "X_ZOHO_CATALYST_LISTEN_PORT": os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", "NOT SET"),
            "DEPENDENCIES": {
                "flask": check("flask"),
                "networkx": check("networkx"),
                "jellyfish": check("jellyfish"),
                "sklearn": check("sklearn"),
                "numpy": check("numpy"),
                "scipy": check("scipy"),
                "faker": check("faker"),
            },
        }
        body = json.dumps(info, indent=2, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", os.environ.get("PORT", 9000)))
    print(f"[DIAG] starting on 0.0.0.0:{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
