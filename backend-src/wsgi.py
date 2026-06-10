"""
PythonAnywhere WSGI entry point.

In the PythonAnywhere web tab, set the WSGI configuration file to this file,
or paste the following into the auto-generated WSGI file:

    import sys
    sys.path.insert(0, '/home/<your-username>/torqued/backend-src')
    from wsgi import application
"""
import sys
import os
from pathlib import Path

_here = Path(__file__).parent          # backend-src/
_root = _here.parent                   # project root

if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

os.environ.setdefault("DB_PATH", str(_root / "data" / "garage.db"))
os.environ["FLASK_DEBUG"] = "0"

from torqued import create_app

application = create_app()
