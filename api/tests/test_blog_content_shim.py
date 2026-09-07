"""The skill shim must run the QA gate on a bare `python3`, no virtualenv.

Someone checking a batch before publishing runs the script straight out of the
skill directory. If it ever needs `api/.venv`, that check stops happening.
"""
import os
import shutil
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _bind_db():
    """No database in the content engine. See test_blog_content_expand.py."""
    yield


TESTS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.abspath(os.path.join(TESTS_DIR, "..", ".."))
SHIM = os.path.join(REPO_ROOT, ".claude", "skills", "dothesis-content-pipeline",
                    "scripts", "qa_seeds.py")
PASSING_DIR = os.path.join(TESTS_DIR, "fixtures", "blog", "content", "passing")
FAILING_DIR = os.path.join(TESTS_DIR, "fixtures", "blog", "content", "failing")


def _run(seed_dir):
    python3 = shutil.which("python3")
    assert python3, "a system python3 is what the skill instructions tell people to use"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
    return subprocess.run([python3, SHIM, seed_dir], capture_output=True, text=True,
                          cwd=REPO_ROOT, env=env, timeout=120)


def test_shim_exists_and_is_executable():
    assert os.path.isfile(SHIM)
    assert os.access(SHIM, os.X_OK), "the skill documents running it directly"


def test_shim_passes_the_exemplar_batch():
    result = _run(PASSING_DIR)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failing" in result.stdout


def test_shim_fails_a_broken_batch():
    result = _run(FAILING_DIR)
    assert result.returncode == 1
    assert "FAIL" in result.stdout
