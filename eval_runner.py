import json
import os
import re
import tempfile

from eval_cases import EVAL_CASES
from reviewer import run_reviewer_agent


MAX_REVIEW_WORDS = 900


NEW_ACTION_STATES = (
    "Needs revision",
    "Open decision",
    "Can defer",
)

OLD_ACTION_STATES = (
    "Critical",
    "Important",
    "Process",
)


REQUIRED_HEADINGS = (
    "Review Summary",
    "Key Review Findings",
    "Questions to Resolve",
    "What Is Solid",
)


def get_output_text(result):
    if result.get("status") == "REVIEW":
        return result.get("review", "")

    if result.get("status") == "ASK":
        return result.get("message", "")

    return result.get("message", "")


def count_key_issues(text):
    pattern = (
        r"^\*\*\[(Needs revision|Open decision|Can defer)\]"
    )

    return len(
        re.findall(
            pattern,
            text,
            flags=(
                re.MULTILINE
                | re.IGNORECASE
            )
        )
    )


def extract_section(text, heading):
    pattern = (
        rf"## {re.escape(heading)}\s*(.*?)"
        rf"(?=\n## |\Z)"
    )

    match = re.search(
        pattern,
        text,
        flags=(
            re.DOTALL
            | re.IGNORECASE
        )
    )

    if not match:
        return ""

    return match.group(1).strip()


def count_questions(text):
    section = extract_section(
        text,
        "Questions to Resolve"
    )

    if not section:
        return 0

    return len(
        re.findall(
            r"^\s*\d+\.",
            section,
            flags=re.MULTILINE
        )
    )


def has_required_headings(text):
    return all(
        re.search(
            rf"^## {re.escape(heading)}\s*$",
            text,
            flags=(
                re.MULTILINE
                | re.IGNORECASE
            )
        )
        for heading in REQUIRED_HEADINGS
    )


def uses_old_action_states(text):
    pattern = (
        r"^\*\*\[(Critical|Important|Process)\]"
    )

    return bool(
        re.search(
            pattern,
            text,
            flags=(
                re.MULTILINE
                | re.IGNORECASE
            )
        )
    )


def extract_overall_status(text):
    summary = extract_section(
        text,
        "Review Summary"
    )

    target = summary or text

    for state in (
        "Ready to proceed with open decisions",
        "Ready to proceed",
        "Needs revision",
    ):
        if re.search(
            re.escape(state),
            target,
            flags=re.IGNORECASE
        ):
            return state

    return ""


def readiness_is_consistent(text):
    overall = extract_overall_status(
        text
    )

    has_needs_revision = bool(
        re.search(
            r"^\*\*\[Needs revision\]",
            text,
            flags=(
                re.MULTILINE
                | re.IGNORECASE
            )
        )
    )

    if (
        overall.startswith("Ready to proceed")
        and has_needs_revision
    ):
        return False

    return bool(overall)


def run_case(case):
    support_path = None

    try:
        supporting_text = case.get(
            "supporting_text",
            ""
        )

        if supporting_text:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8"
            ) as temp_file:
                temp_file.write(
                    supporting_text
                )
                support_path = (
                    temp_file.name
                )

        result = run_reviewer_agent(
            case["prd_text"],
            support_path or ""
        )

        output_text = get_output_text(
            result
        )

        actual_status = result.get(
            "status"
        )

        evidence_used = bool(
            result.get(
                "supporting_evidence_used",
                False
            )
        )

        checks = {}

        checks["status"] = (
            actual_status
            == case["expected_status"]
        )

        checks["tool_use"] = (
            evidence_used
            == case["expected_tool_use"]
        )

        if actual_status == "REVIEW":

            issue_count = count_key_issues(
                output_text
            )

            question_count = count_questions(
                output_text
            )

            word_count = len(
                output_text.split()
            )

            checks["required_headings"] = (
                has_required_headings(
                    output_text
                )
            )

            checks["max_6_findings"] = (
                issue_count <= 6
            )

            checks["max_3_questions"] = (
                question_count <= 3
            )

            checks["new_action_states"] = (
                not uses_old_action_states(
                    output_text
                )
            )

            checks["readiness_consistency"] = (
                readiness_is_consistent(
                    output_text
                )
            )

            checks["reasonable_length"] = (
                word_count <= MAX_REVIEW_WORDS
            )

        else:
            issue_count = None
            question_count = None
            word_count = len(
                output_text.split()
            )

        structural_pass = all(
            checks.values()
        )

        return {
            "id": case["id"],
            "name": case["name"],
            "purpose": case["purpose"],
            "expected_status": case[
                "expected_status"
            ],
            "actual_status": actual_status,
            "expected_tool_use": case[
                "expected_tool_use"
            ],
            "actual_tool_use": evidence_used,
            "actions": result.get(
                "actions",
                []
            ),
            "issue_count": issue_count,
            "question_count": question_count,
            "word_count": word_count,
            "checks": checks,
            "structural_pass": structural_pass,
            "output": output_text,
        }

    finally:
        if (
            support_path
            and os.path.exists(
                support_path
            )
        ):
            os.remove(
                support_path
            )


def main():
    results = []

    print("\nPM REVIEWER EVALUATION")
    print("=" * 72)

    for case in EVAL_CASES:

        print(
            f"\nRunning {case['id']} - "
            f"{case['name']}..."
        )

        try:
            result = run_case(
                case
            )
            results.append(
                result
            )

            verdict = (
                "PASS"
                if result[
                    "structural_pass"
                ]
                else "FAIL"
            )

            print(
                f"{case['id']} | "
                f"Expected: "
                f"{result['expected_status']} | "
                f"Actual: "
                f"{result['actual_status']} | "
                f"Tool: "
                f"{result['actual_tool_use']} | "
                f"{verdict}"
            )

            failed_checks = [
                name
                for name, passed
                in result["checks"].items()
                if not passed
            ]

            if failed_checks:
                print(
                    "  Failed checks:",
                    ", ".join(
                        failed_checks
                    )
                )

        except Exception as e:

            print(
                f"{case['id']} | ERROR | {e}"
            )

            results.append({
                "id": case["id"],
                "name": case["name"],
                "error": str(e),
                "structural_pass": False,
            })

    with open(
        "eval_results.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            results,
            file,
            indent=2,
            ensure_ascii=False
        )

    passed = sum(
        1
        for result in results
        if result.get(
            "structural_pass"
        )
    )

    print("\n" + "=" * 72)
    print(
        f"Structural checks passed: "
        f"{passed}/{len(results)}"
    )

    print(
        "\nFull outputs saved to: "
        "eval_results.json"
    )


if __name__ == "__main__":
    main()
