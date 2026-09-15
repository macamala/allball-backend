import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["NINKO_SKIP_STARTUP_INDEX"] = "1"
