"""Pytest bootstrap: stub pyarrow.compute before pandas import.

Windows Application Control policy blocks pyarrow._compute DLL on this
machine. pandas 3.x imports pyarrow.compute at module load, breaking all
pandas imports. This conftest installs a Python-level stub so pandas core
works, and disables Arrow-backed strings (which need real pyarrow).

The blocked DLL is untouched; only the Python module is stubbed.
"""
import sys
import types


def _install_stub() -> None:
    """Install a safe pyarrow.compute stub if the real one cannot import."""
    try:
        import pyarrow.compute  # noqa: F401  (works if policy allows it)
        return
    except ImportError:
        pass

    class _StubModule(types.ModuleType):
        """Module whose unknown attributes resolve to no-op callables.

        Dunder attributes return sane defaults so inspect/importlib work.
        """

        def __getattr__(self, name):
            if name.startswith("__") and name.endswith("__"):
                if name == "__path__":
                    return []
                if name == "__file__":
                    return "<pyarrow.compute stub>"
                if name == "__name__":
                    return "pyarrow.compute"
                if name == "__spec__":
                    return None
                raise AttributeError(name)
            return lambda *a, **k: None

    fake = _StubModule("pyarrow.compute")
    sys.modules["pyarrow.compute"] = fake


_install_stub()

# pandas 3.x defaults to Arrow-backed strings, which need real pyarrow.
# Force the Python object backend so string ops work with the stub.
import pandas as pd  # noqa: E402

pd.options.future.infer_string = False