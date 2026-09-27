"""Startup hook for Python processes that Codex runs inside its Windows sandbox.

Python 3.13+ on Windows turns ``os.mkdir(path, 0o700)`` (what ``tempfile.mkdtemp``
uses) into an owner-only ACL. Codex's restricted-token sandbox can't then use the
folder it just created, which breaks pytest's ``tmp_path``, ``venv``/``ensurepip``
and anything else built on temporary directories. Those directories are created
with ordinary permissions instead. Nothing else changes, and the sandbox stays on.
"""

import os

if os.name == "nt":
    _mkdir = os.mkdir

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if mode == 0o700:
            mode = 0o777
        return _mkdir(path, mode) if dir_fd is None else _mkdir(path, mode, dir_fd=dir_fd)

    os.mkdir = mkdir
