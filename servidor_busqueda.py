"""
servidor_busqueda.py
Servidor web para buscar en la base de periódicos oficiales (Turso)

Variables de entorno necesarias:
    TURSO_URL    = libsql://tu-base.turso.io
    TURSO_TOKEN  = tu-token

Uso local:
    set TURSO_URL=libsql://...
    set TURSO_TOKEN=...
    python servidor_busqueda.py

"""

import os
import json
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

TURSO_URL   = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "")
PORT        = int(os.environ.get("PORT", 8765))

def turso_query(sql, params=None):
    """Ejecuta una query en Turso via HTTP API."""
    # Convertir URL libsql:// a https://
    base_url = TURSO_URL.replace("libsql://", "https://")
    url = f"{base_url}/v2/pipeline"

    stmt = {"type": "execute", "stmt": {"sql": sql}}
    if params:
        stmt["stmt"]["args"] = [{"type": "text", "value": str(p)} for p in params]

    body = json.dumps({"requests": [stmt, {"type": "close"}]}).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    result = data["results"][0]["response"]["result"]
    cols   = [c["name"] for c in result["cols"]]
    rows   = [[cell.get("value", "") for cell in row] for row in result["rows"]]
    return rows

def buscar(termino, estado=None, fecha=None, limite=100):
    sql = """
        SELECT p.estado, p.fecha, p.seccion, p.texto, p.archivo_pdf
        FROM publicaciones p
        JOIN publicaciones_fts fts ON p.rowid = fts.rowid
        WHERE fts.texto MATCH ?
        {filtro_estado}
        {filtro_fecha}
        ORDER BY p.fecha DESC
        LIMIT ?
    """.format(
        filtro_estado="AND p.estado = ?" if estado else "",
        filtro_fecha="AND p.fecha = ?" if fecha else ""
    )

    params = [termino]
    if estado: params.append(estado)
    if fecha:  params.append(fecha)
    params.append(limite)

    try:
        rows = turso_query(sql, params)
        return rows, None
    except Exception as e:
        return [], str(e)

def get_estados():
    try:
        rows = turso_query("SELECT DISTINCT estado FROM publicaciones ORDER BY estado")
        return [r[0] for r in rows]
    except:
        return []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/buscar":
            qs      = parse_qs(parsed.query)
            termino = qs.get("q", [""])[0].strip()
            estado  = qs.get("estado", [""])[0].strip() or None
            fecha   = qs.get("fecha", [""])[0].strip() or None

            if not termino:
                self.responder_json({"resultados": [], "total": 0})
                return

            filas, error = buscar(termino, estado, fecha)
            if error:
                self.responder_json({"resultados": [], "total": 0, "error": error})
                return

            resultados = []
            for estado_r, fecha_r, seccion, texto, archivo in filas:
                idx = texto.lower().find(termino.lower())
                if idx >= 0:
                    inicio    = max(0, idx - 150)
                    fin       = min(len(texto), idx + 300)
                    fragmento = ("..." if inicio > 0 else "") + texto[inicio:fin] + ("..." if fin < len(texto) else "")
                else:
                    fragmento = texto[:300] + "..."
                resultados.append({
                    "estado":    estado_r,
                    "fecha":     fecha_r,
                    "seccion":   seccion or "",
                    "fragmento": fragmento,
                    "archivo":   archivo,
                })
            self.responder_json({"resultados": resultados, "total": len(resultados)})

        elif parsed.path == "/estados":
            self.responder_json({"estados": get_estados()})

        else:
            self.responder_html(HTML)

    def responder_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def responder_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Periódicos Oficiales</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
  :root {
    --bg: #0f0f0f; --surface: #1a1a1a; --border: #2a2a2a;
    --accent: #c8a96e; --accent2: #7eb8c8;
    --text: #e8e0d0; --muted: #6a6560;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'IBM Plex Sans', sans-serif; min-height: 100vh; padding: 2rem; }
  header { border-bottom: 1px solid var(--border); padding-bottom: 1.5rem; margin-bottom: 2rem; display: flex; align-items: baseline; gap: 1rem; }
  h1 { font-family: 'Playfair Display', serif; font-size: 1.8rem; color: var(--accent); letter-spacing: -0.02em; }
  .subtitulo { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; }
  .busqueda { display: grid; grid-template-columns: 1fr auto auto auto; gap: 0.75rem; margin-bottom: 2rem; align-items: center; }
  input, select { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.75rem 1rem; font-family: 'IBM Plex Sans', sans-serif; font-size: 0.95rem; outline: none; transition: border-color 0.2s; }
  input:focus, select:focus { border-color: var(--accent); }
  select { cursor: pointer; } select option { background: var(--surface); }
  button { background: var(--accent); color: #0f0f0f; border: none; padding: 0.75rem 1.5rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; font-weight: 500; letter-spacing: 0.05em; cursor: pointer; text-transform: uppercase; transition: opacity 0.2s; }
  button:hover { opacity: 0.85; } button:disabled { opacity: 0.4; cursor: not-allowed; }
  .info { font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--muted); margin-bottom: 1.5rem; letter-spacing: 0.05em; }
  .info span { color: var(--accent); }
  .resultado { border: 1px solid var(--border); padding: 1.25rem 1.5rem; margin-bottom: 0.75rem; transition: border-color 0.2s; }
  .resultado:hover { border-color: var(--accent); }
  .meta { display: flex; gap: 1rem; margin-bottom: 0.75rem; flex-wrap: wrap; align-items: center; }
  .estado { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; color: var(--accent); font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; }
  .fecha { font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--accent2); }
  .seccion { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .archivo { font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--muted); margin-left: auto; }
  .fragmento { font-size: 0.9rem; line-height: 1.7; color: #c8c0b0; }
  .fragmento mark { background: rgba(200,169,110,0.25); color: var(--accent); padding: 0 2px; border-radius: 2px; font-weight: 500; }
  .spinner { display: none; font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; color: var(--muted); margin: 2rem 0; letter-spacing: 0.1em; }
  .spinner.visible { display: block; }
  .vacio { text-align: center; padding: 3rem; color: var(--muted); font-family: 'IBM Plex Mono', monospace; font-size: 0.85rem; letter-spacing: 0.05em; display: none; }
  .vacio.visible { display: block; }
  @media (max-width: 700px) { .busqueda { grid-template-columns: 1fr; } .archivo { margin-left: 0; } }
</style>
</head>
<body>
<header>
  <h1>Periódicos Oficiales</h1>
  <span class="subtitulo">31 estados · búsqueda de texto completo</span>
</header>
<div class="busqueda">
  <input type="text" id="q" placeholder="Buscar palabra clave..." autofocus>
  <select id="estado"><option value="">Todos los estados</option></select>
  <input type="date" id="fecha">
  <button onclick="buscar()">Buscar</button>
</div>
<div class="info" id="info"></div>
<div class="spinner" id="spinner">Buscando...</div>
<div class="vacio" id="vacio">No se encontraron resultados.</div>
<div id="resultados"></div>
<script>
fetch('/estados').then(r=>r.json()).then(data=>{
  const sel=document.getElementById('estado');
  data.estados.forEach(e=>{const opt=document.createElement('option');opt.value=e;opt.textContent=e;sel.appendChild(opt);});
});
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')buscar();});
function resaltar(texto,termino){
  const re=new RegExp(`(${termino.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')})`,'gi');
  return texto.replace(re,'<mark>$1</mark>');
}
async function buscar(){
  const q=document.getElementById('q').value.trim();
  const estado=document.getElementById('estado').value;
  const fecha=document.getElementById('fecha').value;
  if(!q)return;
  document.getElementById('spinner').classList.add('visible');
  document.getElementById('vacio').classList.remove('visible');
  document.getElementById('resultados').innerHTML='';
  document.getElementById('info').innerHTML='';
  const params=new URLSearchParams({q});
  if(estado)params.append('estado',estado);
  if(fecha)params.append('fecha',fecha);
  const res=await fetch('/buscar?'+params);
  const data=await res.json();
  document.getElementById('spinner').classList.remove('visible');
  if(!data.resultados.length){document.getElementById('vacio').classList.add('visible');return;}
  document.getElementById('info').innerHTML=`<span>${data.total}</span> resultado${data.total!==1?'s':''} para "<span>${q}</span>"`;
  const cont=document.getElementById('resultados');
  data.resultados.forEach(r=>{
    const div=document.createElement('div');div.className='resultado';
    div.innerHTML=`<div class="meta"><span class="estado">${r.estado}</span><span class="fecha">${r.fecha}</span>${r.seccion?`<span class="seccion">${r.seccion}</span>`:''}<span class="archivo">${r.archivo}</span></div><div class="fragmento">${resaltar(r.fragmento,q)}</div>`;
    cont.appendChild(div);
  });
}
</script>
</body>
</html>"""

if __name__ == "__main__":
    if not TURSO_URL or not TURSO_TOKEN:
        print(" Faltan variables de entorno TURSO_URL y TURSO_TOKEN")
        print("   Ejecútalas antes de correr el servidor:")
        print("   set TURSO_URL=libsql://tu-base.turso.io")
        print("   set TURSO_TOKEN=tu-token")
        exit(1)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n Servidor corriendo en http://localhost:{PORT}")
    print(f"   Presiona Ctrl+C para detener\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
