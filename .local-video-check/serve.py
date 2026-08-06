from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB_SPEECH_SCRIPT = ROOT.parent / "docs" / "examples" / "web-speech-recognition.js"
HOST = "127.0.0.1"
PORT = 5173


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/web-speech-recognition.js":
            content = WEB_SPEECH_SCRIPT.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if path.startswith(("/join/", "/meetings/")):
            self.path = "/index.html"
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), FrontendHandler)
    print(f"Local test frontend: http://localhost:{PORT}")
    print("Stop: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nFrontend stopped.")
    finally:
        server.server_close()
