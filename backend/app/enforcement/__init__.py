"""ASTRA e-challan & penalty management.

Sub-modules are deliberately import-light: ``signal`` and ``red_light`` have no
FastAPI / MongoDB / YOLO dependencies so they can be reused from SUMO scripts
and unit tests.  Heavier pieces (``video``, ``anpr``, ``store`` ...) import
their dependencies lazily.
"""
