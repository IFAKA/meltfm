"""Personal AI Radio — PWA server entry point."""
import logging
import socket
import uvicorn
from src.config import WEB_PORT
from src.web.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None

if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"\n  ♪  Personal Radio")
    print(f"  Local:   http://localhost:{WEB_PORT}")
    if local_ip:
        print(f"  Network: http://{local_ip}:{WEB_PORT}")
    print()
    uvicorn.run(create_app(), host="0.0.0.0", port=WEB_PORT, log_level="info")
