#!/usr/bin/env python3
"""
Setup script for bb-run
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="bb-run",
    version="0.1.0",
    author="Karl Hill",
    author_email="karlhillx@gmail.com",
    description="Run Bitbucket Pipelines locally",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/karlhillx/bb-run",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
        "Topic :: DevOps",
    ],
    python_requires=">=3.8",
    install_requires=[
        "PyYAML>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bb-run=bbrun.cli:main",
        ],
    },
    package_data={
        "bbrun": ["py.typed"],
    },
    include_package_data=True,
)