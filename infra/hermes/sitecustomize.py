"""Install Mentor dispatcher at the Hermes gateway import boundary."""

from __future__ import annotations

import importlib.abc
import sys


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "gateway.run":
            return None
        for finder in tuple(sys.meta_path):
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is None or spec.loader is None:
                continue
            loader = spec.loader

            class _Loader(importlib.abc.Loader):
                def __init__(self, wrapped):
                    self._wrapped = wrapped

                def create_module(self, spec):
                    create = getattr(self._wrapped, "create_module", None)
                    return create(spec) if create else None

                def exec_module(self, module):
                    self._wrapped.exec_module(module)
                    from mentor_telegram_dispatcher import install

                    install(module)

            spec.loader = _Loader(loader)
            return spec
        return None


if not any(isinstance(f, _Finder) for f in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
