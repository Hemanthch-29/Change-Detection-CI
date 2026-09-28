from __future__ import annotations

import argparse
import logging
import sys

from change_aware.change_detection import ChangeDetectionError, ChangeDetector
from change_aware.dependency import DependencyAnalysisError, DependencyGraphBuilder
from change_aware.models import ChangedFile, ChangeType


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="change_aware", description="Change-Aware Testing Agent")
    subparsers = parser.add_subparsers(dest="command")
    detect = subparsers.add_parser("detect-changes", help="List files changed between two commits.")
    detect.add_argument("repository")
    detect.add_argument("base_commit")
    detect.add_argument("head_commit")
    build = subparsers.add_parser("build-graph", help="Print the repository dependency graph.")
    build.add_argument("repository")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "detect-changes":
        return _detect_changes(args.repository, args.base_commit, args.head_commit)
    if args.command == "build-graph":
        return _build_graph(args.repository)

    print("Change-Aware Testing Agent")
    return 0
