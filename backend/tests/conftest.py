import os
from pathlib import Path


Path(".tmp").mkdir(exist_ok=True)
os.environ["NETTWIN_DISABLE_SCHEDULER"] = "1"
os.environ["NETTWIN_DATABASE_URL"] = "sqlite:///./.tmp/test_nettwin.db"
