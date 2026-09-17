#!/usr/bin/env python3
"""Receptor local de PDFs para la extensión de Chrome (Jalisco).

Corre en la Mac:  python3 receptor_jalisco.py
  GET  /pendientes?n=25  → lista de tocas pendientes (JSON)
  POST /recibe           → {id, file, b64} escribe el PDF y marca hecho

Reanudable: los hechos viven en data/jalisco/estado_fase2.json.
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DIR = Path(__file__).resolve().parent.parent / "data" / "jalisco"
IDS = DIR / "ids.jsonl"
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado_fase2.json"
LOCK = threading.Lock()


def cargar():
    todo = []
    for line in IDS.read_text().strip().split("\n"):
        try:
            d = json.loads(line)
            if d.get("file"):
                todo.append({"id": str(d["id"]), "file": d["file"]})
        except Exception:
            pass
    hechos = set()
    if ESTADO.exists():
        try:
            hechos = set(json.loads(ESTADO.read_text()))
        except Exception:
            pass
    return todo, hechos


def marcar(file_name: str) -> None:
    with LOCK:
        todo, hechos = cargar()
        hechos.add(file_name)
        ESTADO.write_text(json.dumps(sorted(hechos), ensure_ascii=False))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        n = int(q.get("n", ["25"])[0])
        todo, hechos = cargar()
        pend = [t for t in todo if t["file"] not in hechos][:n]
        self._json(pend)

    def do_POST(self):
        if urlparse(self.path).path != "/recibe":
            return self._json({"error": "ruta"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(length))
            raw = base64.b64decode(d["b64"])
            if raw[:4] != b"%PDF":
                return self._json({"ok": False, "error": "no-pdf"}, 400)
            dest = PDFS / d["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            marcar(d["file"])
            self._json({"ok": True})
        except Exception as e:
            self._json({"ok": False, "error": str(e)[:100]}, 400)


if __name__ == "__main__":
    PDFS.mkdir(parents=True, exist_ok=True)
    print("Receptor en http://127.0.0.1:8765 — Ctrl+C para detener")
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
