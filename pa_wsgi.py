import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(os.environ["HOME"]) / "torqued" / ".env")

sys.path.insert(0, os.path.join(os.environ["HOME"], "torqued", "backend-src"))

from wsgi import application  # noqa: E402
