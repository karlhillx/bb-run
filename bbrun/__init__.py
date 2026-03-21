"""
bb-run - Bitbucket Pipelines Local Runner

Faithfully runs bitbucket-pipelines.yml locally using Docker or your host environment.
"""

from .cli import main

__version__ = "0.1.0"
__author__ = "Karl Hill"
__license__ = "MIT"

__all__ = ['main']
