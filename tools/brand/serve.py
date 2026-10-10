"""Static server for the icon page; POST /save?name=x.png stores a base64 data URL body in out/."""
import base64, http.server, sys, urllib.parse
from pathlib import Path

ROOT = Path(sys.argv[1])


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def do_POST(self):
        name = Path(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)["name"][0]).name
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        (ROOT / "out" / name).write_bytes(base64.b64decode(body.split(",", 1)[1]))
        self.send_response(204)
        self.end_headers()


http.server.ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
