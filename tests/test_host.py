"""
Tests for HostRunner
"""

import pytest
import yaml
from bbrun.host import HostRunner


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repo with a pipeline file."""
    pipeline = {
        'image': 'python:3.11',
        'pipelines': {
            'default': [
                {'step': {'name': 'test', 'script': ['echo hello', 'echo world']}}
            ]
        }
    }
    pipeline_file = tmp_path / 'bitbucket-pipelines.yml'
    with open(pipeline_file, 'w') as f:
        yaml.dump(pipeline, f)
    return tmp_path


def test_host_runner_initialization(temp_repo):
    """Test HostRunner initializes correctly."""
    runner = HostRunner(temp_repo)
    assert runner.repo_path == temp_repo


def test_host_runner_get_steps(temp_repo):
    """Test getting steps from config."""
    runner = HostRunner(temp_repo)
    config = runner.validator.load()
    
    steps = runner._get_steps(config, 'default')
    assert len(steps) == 1
    assert steps[0]['step']['name'] == 'test'


def test_host_runner_build_env(temp_repo):
    """Test environment variable building."""
    runner = HostRunner(temp_repo)
    env = runner._build_env('feature-branch')
    
    assert env['BITBUCKET_BRANCH'] == 'feature-branch'
    assert 'BITBUCKET_REPO_SLUG' in env
    assert 'BITBUCKET_WORKSPACE' in env


def test_host_runner_translate_python(temp_repo, monkeypatch):
    """Test command translation for python."""
    monkeypatch.setattr('bbrun.host.shutil.which', lambda x: None if x == 'python' else '/usr/bin/python3')
    
    runner = HostRunner(temp_repo)
    translated = runner._translate_command('python -m pytest')
    
    assert translated == 'python3 -m pytest'


def test_host_runner_translate_pip(temp_repo, monkeypatch):
    """Test command translation for pip."""
    monkeypatch.setattr('bbrun.host.shutil.which', lambda x: None if x == 'pip' else '/usr/bin/pip3')
    
    runner = HostRunner(temp_repo)
    translated = runner._translate_command('pip install pytest')
    
    assert translated == 'pip3 install --break-system-packages pytest'


def test_host_runner_pip3_still_gets_break_system_packages(temp_repo, monkeypatch):
    """Test pip3 install still gets --break-system-packages for PEP 668."""
    monkeypatch.setattr('bbrun.host.shutil.which', lambda x: '/usr/bin/pip3')
    
    runner = HostRunner(temp_repo)
    translated = runner._translate_command('pip3 install pytest')
    
    # --break-system-packages is always added for PEP 668 macOS compatibility
    assert '--break-system-packages' in translated
    assert 'pip3 install --break-system-packages pytest' == translated