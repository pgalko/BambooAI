import os
import sys
import json
import matplotlib
import matplotlib.pyplot as plt
import base64
from datetime import datetime

from logger_config import get_logger
logger = get_logger(__name__)

class CodeExecutor:
    def __init__(self, mode='local', api_client=None, user_id=None):
        self.mode = mode
        self.plots_dir = os.path.join("iframe_figures", user_id) if user_id else "iframe_figures"
        self.log_dir = os.path.join('logs', user_id) if user_id else 'logs'
        os.makedirs(self.log_dir, exist_ok=True)

        self.api_client = api_client

        BAMBOO_PLOT_FORMAT = os.environ.get('BAMBOO_PLOT_FORMAT')
        if BAMBOO_PLOT_FORMAT is None:
            BAMBOO_PLOT_FORMAT = 'json'

        self.html_patch_code = """
import plotly.io as pio
original_show = pio.show
def show(fig, *args, **kwargs):
    fig.update_layout(template='plotly_dark', dragmode='pan', hovermode='closest', autosize=True)

    # Force override template again (this will fix most issues)
    fig.layout.template = 'plotly_dark'
    
    # Quick fix for legend and annotations
    if fig.layout.legend:
        fig.layout.legend.bgcolor = 'rgba(0,0,0,0.3)'
    for ann in fig.layout.annotations or []:
        ann.bgcolor = 'rgba(0,0,0,0.3)'
        
    # numbered in the order shown: the executors read the files sorted by name, and a name made of id(fig) alone put the
    # figures in the order of their addresses (2026-10-13: a run's two figures swapped places from one run to the next)
    filename = f'{_plots_dir}/figure_{len(_generated_files):03d}_{id(fig)}.html'
    fig.write_html(filename)
    _generated_files.append(filename)
pio.show = show
"""
        self.json_patch_code = """
import plotly.io as pio
original_show = pio.show
def show(fig, *args, **kwargs):
    # Apply basic settings
    fig.update_layout(template='plotly_dark', dragmode='pan', hovermode='closest', autosize=True)
    
    # Force override template again (this will fix most issues)
    fig.layout.template = 'plotly_dark'
    
    # Quick fix for legend and annotations
    if fig.layout.legend:
        fig.layout.legend.bgcolor = 'rgba(0,0,0,0.3)'
    for ann in fig.layout.annotations or []:
        ann.bgcolor = 'rgba(0,0,0,0.3)'
    
    # numbered in the order shown: the executors read the files sorted by name, and a name made of id(fig) alone put the
    # figures in the order of their addresses (2026-10-13: a run's two figures swapped places from one run to the next)
    filename = f'{_plots_dir}/figure_{len(_generated_files):03d}_{id(fig)}.json'
    fig.write_json(filename)
    _generated_files.append(filename)
pio.show = show
"""
        if BAMBOO_PLOT_FORMAT == 'html':
            self.patch_code = self.html_patch_code
        elif BAMBOO_PLOT_FORMAT == 'json':
            self.patch_code = self.json_patch_code

        self.plot_format = BAMBOO_PLOT_FORMAT

        # Cross-platform directory handling
        if not os.path.isdir(self.plots_dir):
            try:
                os.makedirs(self.plots_dir)
            except Exception:
                # If directory creation fails for any reason but directory exists
                if not os.path.isdir(self.plots_dir):
                    raise  # Re-raise if directory doesn't exist

        matplotlib.use('Agg')        # figures are drawn to files, never to a window: the host runs in a server
        plt.ioff()

    def log_to_file(self, message):
        """Write log message to file with timestamp"""

        LOG_DIR = self.log_dir
        LOG_FILE = os.path.join(LOG_DIR, 'code_executor.log')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(LOG_FILE, 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")

    def execute(self, output_manager, kill_signal, code, df=None, df_id=None, generated_datasets_path=None,
                persist_df=True, timeout=None, step_timeout=None):
        # step_timeout: the seconds the script may take where it runs on this machine - the kernel's own limit where
        # none is given (the draft of the figures, 2026-11-18: a look ahead that is not to take the time of an analysis)
        if self.mode == 'local':
            return self._execute_local(code, df, generated_datasets_path, step_timeout)
        elif self.mode == 'api':
            return self._execute_via_api_client(code, df, df_id, generated_datasets_path, output_manager, kill_signal,
                                                persist_df=persist_df, timeout=timeout)
        else:
            raise ValueError("Invalid mode. Choose 'local' or 'api'.")
        
    def _execute_local(self, code, df=None, generated_datasets_path=None, step_timeout=None):
        """The reproduction run on this machine (docs/OSS_DESIGN.md D5, 2026-09-14): a fresh
        PersistentKernel in a subprocess, the same kernel the analysis runs in, with the frame
        loaded and the plotly capture the executor uses. Never exec() in the web app's process:
        a runaway script would stall or crash the server. Returns (df, results, error,
        plot_images, generated_datasets) like the executor path."""
        import base64
        import glob
        import shutil
        import tempfile
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(here, 'delve') not in sys.path:
            sys.path.insert(0, os.path.join(here, 'delve'))
        from kernel import PersistentKernel
        plot_images, generated_datasets = [], []
        tmp = tempfile.mkdtemp(prefix="bamboo_replay_")
        plots_dir = os.path.join(tmp, "plots")
        os.makedirs(plots_dir, exist_ok=True)
        if generated_datasets_path is not None:
            os.makedirs(generated_datasets_path, exist_ok=True)
        prelude = f"import os\n_plots_dir = {plots_dir!r}\n_generated_files = []\n"
        # the plotly capture is optional here: a machine without plotly still reproduces prints and matplotlib figures
        patch = "try:\n" + "".join("    " + line + "\n" for line in self.patch_code.splitlines()) + "except ImportError:\n    pass\n"
        # the analysis kernel makes Figure.show a no-op (no display there); the reproduction run must reach the
        # capture patch, as it does through the executor - so fig.show() goes to pio.show again (2026-09-14)
        patch += ("try:\n    import plotly.graph_objects as _go\n    import plotly.io as _pio\n"
                  "    _go.Figure.show = lambda self, *a, **k: _pio.show(self, *a, **k)\nexcept Exception:\n    pass\n")
        script = prelude + patch + "\n" + code
        kernel = None
        try:
            kernel = PersistentKernel(df=df, generated_dir=generated_datasets_path,   # DS.save in the replay (2026-10-06)
                                      **({"step_timeout": step_timeout} if step_timeout else {}))
            stdout, error, plots = kernel.execute(script, analysis_dir=os.path.join(tmp, "analysis"))
            if error:
                # the traceback's line numbers back in the caller's code, which the prelude and the patch pushed down - as the
                # executor's filter does with its patch (2026-10-11: a routine's run named its failed cell one too high here)
                import re as _re
                offset = (prelude + patch + "\n").count("\n")
                error = _re.sub(r'(File "<string>", line )(\d+)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - offset)), str(error))
            for path in plots or []:                                    # matplotlib figures the kernel saved
                try:
                    with open(path, "rb") as fh:
                        plot_images.append({'data': base64.b64encode(fh.read()).decode('utf-8'), 'format': 'png'})
                except Exception as e:                                  # noqa: BLE001
                    logger.error(f"Error reading figure {path}: {e}")
            for path in sorted(glob.glob(os.path.join(plots_dir, "figure_*"))):   # plotly figures via the patch
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    if self.plot_format == 'json':
                        json.loads(content)
                    plot_images.append({'data': content, 'format': self.plot_format})
                except Exception as e:                                  # noqa: BLE001
                    logger.error(f"Error reading figure {path}: {e}")
            if generated_datasets_path is not None and os.path.isdir(generated_datasets_path):
                generated_datasets = [os.path.join(generated_datasets_path, f) for f in os.listdir(generated_datasets_path)
                                      if os.path.isfile(os.path.join(generated_datasets_path, f))]
                if not generated_datasets:
                    try:
                        os.rmdir(generated_datasets_path)
                    except OSError:
                        pass
            return df, stdout or "", (error or None), plot_images, generated_datasets
        except Exception as e:                                          # noqa: BLE001
            return df, None, str(e), [], []
        finally:
            if kernel is not None:
                try:
                    kernel.cleanup()
                except Exception:                                       # noqa: BLE001
                    pass
            shutil.rmtree(tmp, ignore_errors=True)

    def _execute_via_api_client(self, code, df=None, df_id=None, generated_datasets_path=None, output_manager=None, kill_signal=None, persist_df=True, timeout=None):
        """Execute code via executor API client"""
        try:
            response = self.api_client.execute_code(
                output_manager=output_manager,
                kill_signal=kill_signal,
                code=code,
                df_id=df_id,
                patch_code=self.patch_code,
                plots_dir=self.plots_dir,
                plot_format=self.plot_format,
                generated_datasets_path=generated_datasets_path,
                persist_df=persist_df,
                timeout=timeout
            )
            
            return (
                df,  # Return original df reference
                response.get('results'),
                response.get('error'),
                response.get('plot_images', []),
                response.get('generated_datasets', [])
            )
            
        except Exception as e:
            self.log_to_file(f"Error executing via API client: {str(e)}")
            return df, None, str(e), [], []
