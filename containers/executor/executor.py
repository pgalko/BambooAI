"""
Code-handling helpers for the inverted-core loop.

This module no longer runs code itself. Live execution is owned by
PersistentKernel (kernel.py), which runs generated code in a long-lived
in-process namespace. What remains here are the stateless utilities the
kernel and loop reuse: the import BLACKLIST for generated code, small
temp-file helpers, dataframe serialization, and code-fence extraction.
"""

import os
import re
import tempfile
import textwrap

from logger_config import get_logger

logger = get_logger(__name__)

# Modules banned from generated code (security)
BLACKLIST = [
    'subprocess', 'sys', 'exec', 'eval', 'socket', 'urllib',
    'shutil', 'pickle', 'ctypes', 'multiprocessing', 'tempfile',
    'pty', 'commands', 'cgi', 'builtins', 'importlib',
    'webbrowser', 'http', 'ftplib', 'smtplib', 'xmlrpc',
    'os.system', 'os.popen', 'os.exec', 'os.spawn',
    'os.remove', 'os.rmdir', 'os.unlink', '__import__',
]


def _cleanup_files(*paths):
    """Remove temp files, ignoring missing files and empty paths."""
    for path in paths:
        if not path:
            continue
        try:
            os.unlink(path)
        except OSError:
            pass


def _write_temp_text(content, *, suffix, prefix):
    """Write a UTF-8 text file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


def _serialize_dataframe(df):
    """Serialize the current DataFrame state to a temp file.

    Prefer pickle for fidelity and broad compatibility between the trusted
    parent and child processes. Fall back to parquet, then CSV only if needed.
    """
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix='.pkl', prefix='delve_')
        os.close(fd)
        df.to_pickle(path)
        return path
    except Exception:
        _cleanup_files(path)

    try:
        fd, path = tempfile.mkstemp(suffix='.parquet', prefix='delve_')
        os.close(fd)
        df.to_parquet(path)
        return path
    except Exception:
        _cleanup_files(path)

    fd, path = tempfile.mkstemp(suffix='.csv', prefix='delve_')
    os.close(fd)
    df.to_csv(path, index=False)
    return path


def extract_code(response):
    """Extract Python code from an LLM response."""
    if not response:
        return ""

    patterns = [
        r'```[Pp]ython\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
    ]

    segments = []
    for pattern in patterns:
        segments = re.findall(pattern, response, re.DOTALL)
        if segments:
            break

    if not segments:
        lines = response.split('\n')
        code_lines = []
        in_code = False
        for line in lines:
            stripped = line.strip()
            if not in_code and (
                stripped.startswith('import ')
                or stripped.startswith('from ')
                or stripped.startswith('import\t')
            ):
                in_code = True
            if in_code:
                if (
                    stripped
                    and not any(c in stripped for c in '=()[]{}:.,+-*/#%')
                    and len(stripped) > 60
                    and not stripped.startswith('#')
                ):
                    break
                code_lines.append(line)
        if len(code_lines) >= 3:
            segments = ['\n'.join(code_lines)]

    if not segments:
        return ""

    code = '\n\n'.join(textwrap.dedent(segment) for segment in segments).strip()

    for banned in BLACKLIST:
        pattern = r'\b' + re.escape(banned) + r'\b'
        if re.search(pattern, code):
            if banned == 'sys' and 'sys.' not in code:
                continue
            return (
                'print("Security notice: generated code contains restricted '
                f'module ({banned}) and cannot be executed.")'
            )

    lines = code.split('\n')
    processed = []
    in_main = False
    main_indent = 0
    for line in lines:
        if '__name__' in line and '__main__' in line:
            in_main = True
            base_indent = len(line) - len(line.lstrip())
            main_indent = base_indent + 4
            continue
        if in_main:
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= (main_indent - 4):
                in_main = False
                processed.append(line)
            else:
                if line.strip():
                    stripped = line[main_indent:] if len(line) > main_indent else line.lstrip()
                    processed.append(stripped)
                else:
                    processed.append('')
        else:
            processed.append(line)

    result = '\n'.join(processed)
    result = re.sub(r'n_jobs\s*=\s*-1', 'n_jobs=4', result)
    result = re.sub(r'n_jobs\s*=\s*None', 'n_jobs=4', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()