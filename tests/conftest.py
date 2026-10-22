import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

# app.py opens its database at import time: point it at a throwaway file first.
os.environ["BGCOACH_DB"] = os.path.join(tempfile.mkdtemp(prefix="bgcoach-test-"), "test.sqlite")
# Never call the real Claude API from tests.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
