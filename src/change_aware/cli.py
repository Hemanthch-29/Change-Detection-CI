from __future__ import annotations

import argparse
import json
import logging
import sys

from change_aware.change_detection import ChangeDetectionError, ChangeDetector
from change_aware.dependency import DependencyAnalysisError, DependencyGraphBuilder
from change_aware.impact import ImpactAnalyzer
from change_aware.models import ChangedFile, ChangeType, ImpactAnalysisResult, TestSelectionResult
from change_aware.test_selection import TestSelectionError, TestSelector


def _format_change(change: ChangedFile) -> str:
    if change.change_type is ChangeType.RENAMED:
        target = f"{change.old_path} -> {change.new_path}"
    else:
        target = change.path
    return f"  {change.change_type.value:<8}  {target}"


def _detect_changes(repository: str, base: str, head: str) -> int:
    try:
        changes = ChangeDetector(repository).detect(base, head)
    except ChangeDetectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not changes:
        print("No files changed.")
        return 0
    print("Changed files:")
    for change in changes:
        print(_format_change(change))
    return 0


def _build_graph(repository: str) -> int:
    try:
        graph = DependencyGraphBuilder().build(repository)
    except DependencyAnalysisError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Dependency Graph")
    print("================")
    for node in graph.nodes():
        print()
        print(node.id)
        dependencies = graph.get_dependencies(node.id)
        for dependency in dependencies:
            print(f"  -> {dependency}")
        if not dependencies:
            print("  (no local dependencies)")
    print()
    print(f"{len(graph.nodes())} node(s), {len(graph.edges())} edge(s)")
    return 0


def _analyze_impact(repository: str, base: str, head: str) -> int:
    try:
        changes = ChangeDetector(repository).detect(base, head)
        graph = DependencyGraphBuilder().build(repository)
    except (ChangeDetectionError, DependencyAnalysisError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _print_impact(ImpactAnalyzer().analyze(changes, graph))
    return 0


def _print_impact(result: ImpactAnalysisResult) -> None:
    print("Impact Analysis")
    print("===============")
    print()
    print("Changed Components")
    print("------------------")
    for path in result.changed_components:
        print(path)
    if not result.changed_components:
        print("(none)")
    print()
    print("Impacted Components")
    print("-------------------")
    width = max((len(c.path) for c in result.impacted_components), default=0)
    for component in result.impacted_components:
        marker = "DIRECT" if component.directly_changed else ""
        print(f"[depth {component.depth}] {component.path:<{width}}  {marker}".rstrip())
    if not result.impacted_components:
        print("(none)")
    print()
    print("Summary")
    print("-------")
    print(f"Changed: {len(result.changed_components)}")
    print(f"Impacted: {result.total_impacted}")
    print(f"Maximum impact depth: {result.max_impact_depth}")


def _select_tests(repository: str, base: str, head: str, output_format: str) -> int:
    try:
        changes = ChangeDetector(repository).detect(base, head)
        graph = DependencyGraphBuilder().build(repository)
        impact = ImpactAnalyzer().analyze(changes, graph)
        selection = TestSelector().select(repository, impact)
    except (ChangeDetectionError, DependencyAnalysisError, TestSelectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if output_format == "json":
        print(json.dumps(_selection_to_dict(impact, selection), indent=2))
    else:
        _print_selection(impact, selection)
    return 0


def _selection_to_dict(impact: ImpactAnalysisResult, selection: TestSelectionResult) -> dict:
    return {
        "changed_components": impact.changed_components,
        "impacted_components": [
            {
                "path": c.path,
                "depth": c.depth,
                "directly_changed": c.directly_changed,
                "reason": c.reason,
            }
            for c in impact.impacted_components
        ],
        "selected_tests": [
            {"path": t.path, "reasons": list(t.reasons), "impacted_by": list(t.impacted_by)}
            for t in selection.selected_tests
        ],
        "skipped_tests": [t.path for t in selection.skipped_tests],
        "selected_test_paths": selection.selected_paths,
        "summary": {
            "total_tests": selection.total_tests,
            "selected": selection.selected_count,
            "skipped": selection.skipped_count,
            "reduction_percentage": round(selection.reduction_percentage, 1),
        },
    }


def _print_selection(impact: ImpactAnalysisResult, selection: TestSelectionResult) -> None:
    print("Test Selection")
    print("==============")
    print()
    print("Changed Components")
    print("------------------")
    for path in impact.changed_components:
        print(path)
    if not impact.changed_components:
        print("(none)")
    print()
    print("Impacted Components")
    print("-------------------")
    for component in impact.impacted_components:
        print(f"[depth {component.depth}] {component.path}")
    if not impact.impacted_components:
        print("(none)")
    print()
    print("Selected Tests")
    print("--------------")
    for test in selection.selected_tests:
        print(test.path)
        for reason in test.reasons:
            print(f"  Reason: {reason}")
        print(f"  Impacted by: {', '.join(test.impacted_by)}")
        print()
    if not selection.selected_tests:
        print("(none)")
        print()
    print("Skipped Tests")
    print("-------------")
    for test in selection.skipped_tests:
        print(test.path)
    if not selection.skipped_tests:
        print("(none)")
    print()
    print("Summary")
    print("-------")
    print(f"Total tests: {selection.total_tests}")
    print(f"Selected: {selection.selected_count}")
    print(f"Skipped: {selection.skipped_count}")
    print(f"Reduction: {selection.reduction_percentage:.1f}%")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="change_aware", description="Change-Aware Testing Agent")
    subparsers = parser.add_subparsers(dest="command")
    detect = subparsers.add_parser("detect-changes", help="List files changed between two commits.")
    detect.add_argument("repository")
    detect.add_argument("base_commit")
    detect.add_argument("head_commit")
    build = subparsers.add_parser("build-graph", help="Print the repository dependency graph.")
    build.add_argument("repository")
    impact = subparsers.add_parser(
        "analyze-impact", help="Show components impacted by changes between two commits."
    )
    impact.add_argument("repository")
    impact.add_argument("base_commit")
    impact.add_argument("head_commit")
    select = subparsers.add_parser(
        "select-tests", help="Select tests relevant to changes between two commits."
    )
    select.add_argument("repository")
    select.add_argument("base_commit")
    select.add_argument("head_commit")
    select.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "detect-changes":
        return _detect_changes(args.repository, args.base_commit, args.head_commit)
    if args.command == "build-graph":
        return _build_graph(args.repository)
    if args.command == "analyze-impact":
        return _analyze_impact(args.repository, args.base_commit, args.head_commit)
    if args.command == "select-tests":
        return _select_tests(args.repository, args.base_commit, args.head_commit, args.format)

    print("Change-Aware Testing Agent")
    return 0
