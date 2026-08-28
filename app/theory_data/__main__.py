import argparse
from pathlib import Path

from app.theory_data.validator import TheoryValidationError, validate_theory_repository


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate checked-in theory JSON files.")
    parser.add_argument("--root", type=Path, default=Path("data/theory"))
    args = parser.parse_args()
    try:
        report = validate_theory_repository(args.root)
    except TheoryValidationError as exc:
        print(f"Theory validation failed:\n{exc}")
        return 1
    print(
        "Theory validation passed: "
        f"directories={report.topic_directories}, "
        f"knowledge={report.knowledge_elements}, "
        f"questions={report.questions}, "
        f"demo_directories={report.demo_directories}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
