import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

def test_import():
    from bambooai import BambooAI
    from bambooai import models
    assert True

