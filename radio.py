"""Personal AI Radio — PWA server entry point."""
import logging
import uvicorn
from src.config import WEB_PORT
from src.web.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    print(f"\n  ♪  Personal Radio")
    print(f"  http://localhost:{WEB_PORT}\n")
    uvicorn.run(create_app(), host="0.0.0.0", port=WEB_PORT, log_level="info")
