"""Make missing third-party packages importable so BambooAI's own modules can
be loaded in isolation. Only names absent from the sandbox are faked; anything
genuinely installed (pandas, numpy, flask, requests) is untouched."""
import sys, types, importlib.abc, importlib.machinery

# pandas probes for pyarrow at import time; let it resolve the REAL absence
# before any stub is installed, or it reads a fake __version__ and dies.
# dotenv is deliberately NOT faked either: flask calls dotenv_values() during
# app.run() and a generic stub returns a non-mapping, killing the server.
import pandas  # noqa: F401

FAKE = {"pyarrow", "plotly", "termcolor", "IPython", "tiktoken", "anthropic",
        "openai", "groq", "mistralai", "ollama", "supabase", "stripe", "rdflib",
        "selenium", "newspaper", "pinecone", "sweatstack", "yfinance",
        "geopandas", "fitparse", "google", "jose", "kaleido", "nbformat",
        "seaborn", "lxml_html_clean", "httpx"}


class _Mod(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Mod(f"{self.__name__}.{name}")
        setattr(self, name, sub)
        return sub

    def __call__(self, *a, **k):
        return _Mod(self.__name__)


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in FAKE:
            return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        m = _Mod(spec.name)
        # Submodule imports (pyarrow.parquet) need the parent to look like a
        # package, or Python refuses before the loader is consulted.
        m.__path__ = []
        return m

    def exec_module(self, module):
        pass


sys.meta_path.insert(0, _Finder())

# matplotlib inspects IPython.version_info when switching backends; give the
# fake a real tuple so `matplotlib.use("Agg")` takes its normal path.
try:
    import IPython as _ip
    _ip.version_info = (8, 30, 0)
    _ip.__version__ = "8.30.0"
except Exception:
    pass
