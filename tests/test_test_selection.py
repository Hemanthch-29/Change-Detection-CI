import random
from pathlib import Path

import pytest

from change_aware.models import ImpactAnalysisResult, ImpactedComponent, TestSelectionResult
from change_aware.test_selection import (
    REASON_CHANGED_TEST,
    REASON_DIRECT_IMPORT,
    REASON_NAMING,
    REASON_TRANSITIVE_IMPORT,
    TestDiscovery,
    TestSelectionError,
    TestSelector,
)

SOURCES = {
    "src/payment/__init__.py": "",
    "src/payment/service.py": "def calculate_total(): ...\n",
    "src/checkout/__init__.py": "",
    "src/checkout/service.py": "from payment.service import calculate_total\n",
    "src/user/__init__.py": "",
    "src/user/service.py": "",
}


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _impact(*components: tuple[str, int]) -> ImpactAnalysisResult:
    return ImpactAnalysisResult(
        changed_components=sorted(p for p, d in components if d == 0),
        impacted_components=[
            ImpactedComponent(path=p, depth=d, directly_changed=d == 0) for p, d in components
        ],
    )


def _select(repo: Path, *components: tuple[str, int]) -> TestSelectionResult:
    return TestSelector().select(repo, _impact(*components))


def _selected(result: TestSelectionResult) -> dict[str, tuple[str, ...]]:
    return {t.path: t.reasons for t in result.selected_tests}


# --- discovery -------------------------------------------------------------


def test_discovers_test_prefix_files(tmp_path: Path) -> None:
    _write(tmp_path, {"tests/test_a.py": "", "tests/pkg/test_b.py": "", "tests/helpers.py": ""})
    assert TestDiscovery().discover(tmp_path) == ["tests/pkg/test_b.py", "tests/test_a.py"]


def test_discovers_test_suffix_files(tmp_path: Path) -> None:
    _write(tmp_path, {"pkg/service_test.py": "", "pkg/service.py": "", "conftest.py": ""})
    assert TestDiscovery().discover(tmp_path) == ["pkg/service_test.py"]


def test_discovery_ignores_environments_and_caches(tmp_path: Path) -> None:
    _write(tmp_path, {
        "tests/test_real.py": "",
        ".venv/lib/test_x.py": "",
        "venv/test_x.py": "",
        "lib/site-packages/pkg/test_x.py": "",
        "tests/__pycache__/test_real.py": "",
        ".git/test_x.py": "",
    })
    assert TestDiscovery().discover(tmp_path) == ["tests/test_real.py"]


def test_no_tests_found(tmp_path: Path) -> None:
    repo = _write(tmp_path, SOURCES)
    result = _select(repo, ("src/payment/service.py", 0))

    assert result.total_tests == 0
    assert result.selected_tests == [] and result.skipped_tests == []


def test_zero_test_reduction_is_zero() -> None:
    result = TestSelectionResult()
    assert result.reduction_percentage == 0.0
    assert (result.total_tests, result.selected_count, result.skipped_count) == (0, 0, 0)


# --- selection strategies --------------------------------------------------


def test_import_statement_selects_test(tmp_path: Path) -> None:
    repo = _write(tmp_path, {**SOURCES, "tests/test_billing.py": "import payment.service\n"})
    result = _select(repo, ("src/payment/service.py", 0))

    assert _selected(result) == {"tests/test_billing.py": (REASON_DIRECT_IMPORT,)}
    assert result.selected_tests[0].impacted_by == ("src/payment/service.py",)


def test_from_import_selects_test(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/test_billing.py": "from payment.service import calculate_total\n",
    })
    result = _select(repo, ("src/payment/service.py", 0))
    assert _selected(result) == {"tests/test_billing.py": (REASON_DIRECT_IMPORT,)}


def test_relative_import_selects_test(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "shop/__init__.py": "",
        "shop/payment/__init__.py": "",
        "shop/payment/service.py": "",
        "shop/payment/billing_test.py": "from .service import calculate_total\n",
        "shop/tests/__init__.py": "",
        "shop/tests/test_payments.py": "from ..payment import service\n",
    })
    result = _select(repo, ("shop/payment/service.py", 0))

    assert _selected(result) == {
        "shop/payment/billing_test.py": (REASON_DIRECT_IMPORT,),
        "shop/tests/test_payments.py": (REASON_DIRECT_IMPORT,),
    }


def test_naming_convention_mirrored_directory(tmp_path: Path) -> None:
    repo = _write(tmp_path, {**SOURCES, "tests/payment/test_service.py": "import os\n"})
    result = _select(repo, ("src/payment/service.py", 0))

    assert _selected(result) == {"tests/payment/test_service.py": (REASON_NAMING,)}


def test_naming_convention_flattened_name(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/test_payment_service.py": "",
        "tests/test_service.py": "",  # ambiguous: must not match src/payment/service.py
        "tests/user/test_service.py": "",
    })
    result = _select(repo, ("src/payment/service.py", 0))

    assert _selected(result) == {"tests/test_payment_service.py": (REASON_NAMING,)}


def test_transitively_impacted_component_selects_its_test(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/test_checkout_flow.py": "from checkout.service import checkout\n",
    })
    result = _select(repo, ("src/payment/service.py", 0), ("src/checkout/service.py", 1))

    assert _selected(result) == {"tests/test_checkout_flow.py": (REASON_TRANSITIVE_IMPORT,)}
    assert result.selected_tests[0].impacted_by == ("src/checkout/service.py",)


def test_directly_changed_test_is_selected(tmp_path: Path) -> None:
    repo = _write(tmp_path, {**SOURCES, "tests/test_misc.py": ""})
    result = _select(repo, ("tests/test_misc.py", 0))
    assert _selected(result) == {"tests/test_misc.py": (REASON_CHANGED_TEST,)}


def test_unrelated_test_is_skipped(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/payment/test_service.py": "from payment.service import calculate_total\n",
        "tests/user/test_service.py": "from user.service import something\n",
    })
    result = _select(repo, ("src/payment/service.py", 0))

    assert [t.path for t in result.skipped_tests] == ["tests/user/test_service.py"]
    assert not result.skipped_tests[0].selected
    assert result.skipped_tests[0].reasons == ()


def test_multiple_impacted_components(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/payment/test_service.py": "from payment.service import calculate_total\n",
        "tests/user/test_service.py": "from user.service import something\n",
        "tests/test_other.py": "",
    })
    result = _select(repo, ("src/payment/service.py", 0), ("src/user/service.py", 0))

    assert result.selected_paths == ["tests/payment/test_service.py", "tests/user/test_service.py"]
    assert [t.path for t in result.skipped_tests] == ["tests/test_other.py"]


def test_multiple_reasons_do_not_duplicate_test(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/payment/test_service.py": (
            "import payment.service\n"
            "from payment.service import calculate_total\n"
            "from checkout.service import checkout\n"
        ),
    })
    result = _select(repo, ("src/payment/service.py", 0), ("src/checkout/service.py", 1))

    assert result.selected_paths == ["tests/payment/test_service.py"]
    test = result.selected_tests[0]
    assert test.reasons == (REASON_DIRECT_IMPORT, REASON_TRANSITIVE_IMPORT, REASON_NAMING)
    assert test.impacted_by == ("src/checkout/service.py", "src/payment/service.py")


def test_selection_reasons_are_present(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/payment/test_service.py": "",
        "tests/checkout/test_flow.py": "from checkout.service import checkout\n",
        "tests/test_billing.py": "import payment.service\n",
    })
    result = _select(repo, ("src/payment/service.py", 0), ("src/checkout/service.py", 1))

    assert result.selected_count == 3
    for test in result.selected_tests:
        assert test.selected and test.reason and test.impacted_by


def test_deterministic_ordering_and_counts(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        **SOURCES,
        "tests/z/test_checkout.py": "from checkout.service import checkout\n",
        "tests/a/test_checkout.py": "from checkout.service import checkout\n",
        "tests/y/test_pay.py": "import payment.service\n",
        "tests/b/test_pay.py": "import payment.service\n",
        "tests/test_user.py": "",
    })
    components = [("src/payment/service.py", 0), ("src/checkout/service.py", 1)]
    expected = [  # closest impact depth first, then path
        "tests/b/test_pay.py",
        "tests/y/test_pay.py",
        "tests/a/test_checkout.py",
        "tests/z/test_checkout.py",
    ]
    rng = random.Random(0)
    for _ in range(3):
        rng.shuffle(components)
        result = _select(repo, *components)
        assert result.selected_paths == expected
        assert [t.path for t in result.skipped_tests] == ["tests/test_user.py"]

    assert (result.total_tests, result.selected_count, result.skipped_count) == (5, 4, 1)
    assert result.reduction_percentage == pytest.approx(20.0)


def test_missing_repository_raises(tmp_path: Path) -> None:
    with pytest.raises(TestSelectionError):
        TestSelector().select(tmp_path / "missing", ImpactAnalysisResult())
