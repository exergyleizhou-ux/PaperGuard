"""Bundled data artifacts (e.g. the T9 TF-IDF/LR classifier weights).

This is a package (not just a folder) so ``importlib.resources.files`` can
resolve bundled files such as ``t9_classifier.npz`` across wheel/sdist installs.
"""
