# Change-Aware Testing Agent

When a developer opens a Pull Request, the Change-Aware Testing Agent will look at the code changes, work out which parts of the repository could be affected, find the relevant tests, run only those tests, and report the results. This repository currently holds only the initial project skeleton.

## Architecture

The core engine is a standalone Python package (`src/change_aware`). CI systems such as GitHub Actions only invoke it; they are integration layers. The engine is split into separate modules: models, change detection, dependency, impact, test selection, and CLI.

## Planned Workflow

```
PR
→ Change Detection
→ Dependency Analysis
→ Impact Analysis
→ Test Selection
→ Test Execution
→ Reporting
```
