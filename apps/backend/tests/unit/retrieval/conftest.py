"""Pytest configuration for retrieval unit tests.

This conftest is specifically for retrieval unit tests and avoids
importing the full app to prevent database initialization errors.
"""

import pytest