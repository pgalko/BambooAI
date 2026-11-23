"""The name the provider adapters still import their unused search function under; it goes with that function in
the clean-up after 0335. The seat is bambooai/web_search.py."""
from bambooai.web_search import WebSearch as SmartSearchOrchestrator      # noqa: F401
