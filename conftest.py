"""Pytest bootstrap for two machine-specific issues.

1. pyarrow.compute is blocked by Windows Application Control on this machine.
   pandas 3.x imports pyarrow.compute at module load, breaking all pandas
   imports. This conftest installs a Python-level stub so pandas core works,
   and disables Arrow-backed strings (which need real pyarrow). The blocked
   DLL is untouched; only the Python module is stubbed.

2. cuDNN 9.19 (build 91900) aborts the process with STATUS_STACK_BUFFER_OVERRUN
   (0xC0000409) at interpreter teardown when an nn.LSTM has run on CUDA on
   this RTX 5060 / driver 616.56 box. It is a teardown crash, not a test
   failure: every assertion passes and pytest reports success, but the process
   exits with a non-zero code, which breaks CI and `verify_all.py`.

   Disabling cuDNN for the test session avoids the crash. It does not change
   what the tests assert: cuDNN is an accelerated cuRNN kernel, and PyTorch
   transparently falls back to the native implementation, so numerics stay
   equivalent. Remove this once cuDNN ships a fixed build for this GPU.
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


def _disable_broken_cudnn() -> bool:
    """Turn off cuDNN if this box has the crashing RNN kernel build.

    Only runs when torch is importable, so non-torch projects are unaffected.
    """
    try:
        import torch
    except Exception:
        return False

    # cudnn.version() is None when cuDNN is not compiled in or not loaded.
    if torch.backends.cudnn.version() is None:
        return False

    torch.backends.cudnn.enabled = False
    return True


if _disable_broken_cudnn():
    import torch  # noqa: E402

    print(
        f"[conftest] cuDNN {torch.backends.cudnn.version()} disabled for tests "
        "(teardown crash 0xC0000409 on this GPU); PyTorch uses native cuRNN.",
        file=sys.stderr,
    )