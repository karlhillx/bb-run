"""
Tests for PipelineValidator
"""

import pytest
import yaml
from bbrun.validator import PipelineValidator


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repo with a pipeline file."""
    return tmp_path


@pytest.fixture
def sample_pipeline():
    """Sample pipeline configuration."""
    return {
        'image': 'python:3.11',
        'pipelines': {
            'default': [
                {'step': {'name': 'test', 'script': ['python -m pytest']}}
            ],
            'branches': {
                'main': [
                    {'step': {'name': 'build', 'script': ['npm install', 'npm run build']}}
                ]
            }
        }
    }


def test_validator_loads_valid_yaml(temp_repo, sample_pipeline):
    """Test that validator loads a valid YAML file."""
    pipeline_file = temp_repo / 'bitbucket-pipelines.yml'
    with open(pipeline_file, 'w') as f:
        yaml.dump(sample_pipeline, f)
    
    validator = PipelineValidator(temp_repo)
    config = validator.load()
    
    assert config is not None
    assert config['image'] == 'python:3.11'


def test_validator_returns_none_for_missing_file(temp_repo):
    """Test that validator returns None for missing file."""
    validator = PipelineValidator(temp_repo)
    config = validator.load()
    
    assert config is None


def test_validator_validate_success(temp_repo, sample_pipeline):
    """Test successful validation."""
    pipeline_file = temp_repo / 'bitbucket-pipelines.yml'
    with open(pipeline_file, 'w') as f:
        yaml.dump(sample_pipeline, f)
    
    validator = PipelineValidator(temp_repo)
    assert validator.validate() is True


def test_validator_validate_missing_file(temp_repo):
    """Validation fails when the pipeline file is absent."""
    validator = PipelineValidator(temp_repo)
    assert validator.validate() is False


def test_validator_empty_file(temp_repo):
    """Empty YAML file is rejected."""
    pipeline_file = temp_repo / "bitbucket-pipelines.yml"
    pipeline_file.write_text("", encoding="utf-8")
    validator = PipelineValidator(temp_repo)
    assert validator.load() is None


def test_validator_list_root_not_mapping(temp_repo):
    """Root YAML must be a mapping, not a list."""
    pipeline_file = temp_repo / "bitbucket-pipelines.yml"
    pipeline_file.write_text("- item\n", encoding="utf-8")
    validator = PipelineValidator(temp_repo)
    assert validator.load() is None


def test_validator_validate_missing_pipelines_key(temp_repo):
    """Test validation fails when pipelines key is missing."""
    invalid_config = {'image': 'python:3.11'}
    pipeline_file = temp_repo / 'bitbucket-pipelines.yml'
    with open(pipeline_file, 'w') as f:
        yaml.dump(invalid_config, f)
    
    validator = PipelineValidator(temp_repo)
    assert validator.validate() is False


def test_validator_invalid_yaml(temp_repo):
    """Test validator handles invalid YAML."""
    pipeline_file = temp_repo / 'bitbucket-pipelines.yml'
    with open(pipeline_file, 'w') as f:
        f.write("invalid: yaml: content: [")
    
    validator = PipelineValidator(temp_repo)
    assert validator.load() is None