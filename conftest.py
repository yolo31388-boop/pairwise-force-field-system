"""Pytest bootstrap.

The legacy test classes use ``unittest``-style ``self.assert*`` helpers
without inheriting from ``unittest.TestCase``. The test files must not be
modified, so the assertion helpers are injected here after collection.
"""

import unittest


def _install_assertions(cls):
    for name in dir(unittest.TestCase):
        if name.startswith("assert") or name in ("fail", "_formatMessage"):
            setattr(cls, name, getattr(unittest.TestCase, name))
    cls.failureException = AssertionError
    cls.longMessage = True


def pytest_collection_modifyitems(items):
    patched = set()
    for item in items:
        cls = getattr(item, "cls", None)
        if cls is None or cls in patched:
            continue
        if not issubclass(cls, unittest.TestCase):
            _install_assertions(cls)
        patched.add(cls)
