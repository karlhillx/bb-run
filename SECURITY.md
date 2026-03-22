# Security policy

## Supported versions

We aim to support the latest release on [PyPI](https://pypi.org/project/bb-run/). Security fixes are applied to the current minor line when practical.

## Reporting a vulnerability

**Please do not open a public GitHub issue for undisclosed security problems.**

Instead, email **karlhillx@gmail.com** with:

- A short description of the issue
- Steps to reproduce (if possible)
- Affected bb-run version and environment (OS, Python version)

We will acknowledge receipt and work on a fix and release timeline.

## Scope notes

bb-run **executes commands defined in your `bitbucket-pipelines.yml`** (on the host or inside Docker). That is by design. Reports about “arbitrary code execution” through a malicious or compromised pipeline file are generally out of scope unless they involve a bug in bb-run itself (e.g. unintended execution, unsafe defaults, or injection outside the declared scripts).
