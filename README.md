# Change-Aware Testing Agent

When a developer opens a Pull Request, the Change-Aware Testing Agent will look at the code changes, work out which parts of the repository could be affected, find the relevant tests, run only those tests, and report the results. This is a proof of concept. Change detection, dependency analysis, impact analysis, test selection and CI test execution are implemented.

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

## GitHub Actions

The [change-aware-testing.yml](.github/workflows/change-aware-testing.yml) workflow runs when a Pull Request is opened, updated (new commits pushed) or reopened. It:

1. Detects the files changed between the PR's base SHA and head SHA.
2. Builds the repository's dependency graph.
3. Works out which components are impacted.
4. Selects the relevant test files.
5. Runs **only** those tests with `pytest`. The job fails if they fail.
6. Falls back to the **full test suite** if no tests are selected (or the analysis fails), so the job never passes without running tests.

The workflow is only an integration layer. It reads the JSON from `python -m change_aware select-tests <repo> <base> <head> --format json` (field `selected_test_paths`) through [.github/scripts/run_change_aware_tests.py](.github/scripts/run_change_aware_tests.py). You can run the same script locally:

```bash
python .github/scripts/run_change_aware_tests.py --repo . --base <base_sha> --head <head_sha>
```

Illustrative example (not a measured result):

```
100 total tests
12 selected
88 skipped
12 executed
```
