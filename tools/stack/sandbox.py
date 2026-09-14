"""Selective stand-ins for third-party packages the stack's processes import but never need.

tests/analyst/_stubs.py fakes a fixed list of packages whether or not they are installed. That is
right for the unit battery and wrong for the stack: on the box, with the real venv, the executor
must use the real pyarrow and plotly, and the web app the real SDKs. `install()` here installs
the same kind of stand-in, but only for packages that `importlib` cannot find, and reports what it
faked. On a full venv it installs nothing.
"""
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import types

CANDIDATES = ("pyarrow", "plotly", "termcolor", "IPython", "tiktoken", "anthropic", "openai", "groq", "mistralai",
              "ollama", "stripe", "rdflib", "selenium", "newspaper", "pinecone", "sweatstack", "yfinance", "geopandas",
              "fitparse", "jose", "kaleido", "nbformat", "seaborn", "lxml_html_clean", "httpx", "transformers",
              # dotted: a partial `google` namespace package may exist without these
              "google.cloud", "google.genai", "google.generativeai", "google.oauth2", "google.auth", "google.api_core")


class _Mod(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Mod(f"{self.__name__}.{name}")
        setattr(self, name, sub)
        return sub

    def __call__(self, *a, **k):
        return _Mod(self.__name__)

    def __iter__(self):
        return iter(())


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, names):
        self.names = set(names)

    def find_spec(self, fullname, path=None, target=None):
        for name in self.names:
            if fullname == name or fullname.startswith(name + "."):
                return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        m = _Mod(spec.name)
        m.__path__ = []
        return m

    def exec_module(self, module):
        pass


def install(extra=()):
    """Fake every candidate package that is not installed. Returns the names faked."""
    import pandas  # noqa: F401  pandas probes pyarrow at import; let it see the real absence first
    missing = []
    for n in tuple(CANDIDATES) + tuple(extra):
        try:
            found = importlib.util.find_spec(n) is not None
        except (ModuleNotFoundError, ValueError):
            found = False
        if not found:
            missing.append(n)
    if missing:
        sys.meta_path.insert(0, _Finder(missing))
        if "IPython" in missing:
            try:
                import IPython as _ip                       # matplotlib reads its version when switching backends
                _ip.version_info = (8, 30, 0)
                _ip.__version__ = "8.30.0"
            except Exception:                              # noqa: BLE001
                pass
    return missing
