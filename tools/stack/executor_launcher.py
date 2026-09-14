"""Run the REAL executor (containers/executor/code_executor_api.py) as a local process.

    python3 tools/stack/executor_launcher.py --port 5055 --workdir /tmp/bamboo_stack/executor

Nothing in the executor is changed. Two shims make it run outside its Docker image in a
sandbox that cannot install packages:
  * sandbox.py fakes the third-party packages the executor imports but this machine lacks
    (sweatstack, fitparse, yfinance, geopandas, pyarrow...) - only the missing ones, so on a
    full venv nothing is faked;
  * pandas.read_csv / read_parquet fall back to the default engine when pyarrow is absent
    (the executor's /upload_dataset asks for engine='pyarrow').
The kernel worker is a separate interpreter started by the executor's own PersistentKernel;
it imports only pandas, numpy and matplotlib, so it runs unshimmed.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5055)
    ap.add_argument("--workdir", default=os.path.join("/tmp", "bamboo_stack", "executor"))
    a = ap.parse_args()

    os.makedirs(a.workdir, exist_ok=True)
    os.chdir(a.workdir)                       # datasets/, temp/, iframe_figures/ land here, as in /app
    sys.path[:0] = [HERE, os.path.join(ROOT, "containers", "executor")]
    import sandbox
    faked = sandbox.install()                 # only packages that are not installed; nothing on a full venv

    import pandas as pd
    try:
        import pyarrow
        have_pyarrow = isinstance(getattr(pyarrow, "__version__", None), str)   # the stub has no version
    except Exception:                                   # noqa: BLE001
        have_pyarrow = False
    if not have_pyarrow:
        _read_csv, _read_parquet = pd.read_csv, pd.read_parquet

        def read_csv(*args, **kw):
            if kw.get("engine") == "pyarrow":
                kw.pop("engine")
            return _read_csv(*args, **kw)

        def read_parquet(*args, **kw):
            kw.pop("engine", None)
            return _read_parquet(*args, **kw)
        pd.read_csv, pd.read_parquet = read_csv, read_parquet

    import code_executor_api                            # the real module; registers the kernel blueprint
    print(f"[executor] build {code_executor_api.EXECUTOR_BUILD}; kernel service {code_executor_api.KERNEL_SERVICE}; "
          f"workdir {a.workdir}; port {a.port}; faked packages: {faked or 'none'}", flush=True)
    code_executor_api.app.run(host="127.0.0.1", port=a.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
