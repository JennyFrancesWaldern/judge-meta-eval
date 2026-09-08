"""Not yet implemented -- no experiment pipeline exists for this repo yet.

Write and get ANALYSIS_PLAN.md approved before this does anything real.
"""
import sys


def main() -> int:
    print(
        "No pipeline implemented yet. Write ANALYSIS_PLAN.md and get it"
        " approved before running anything.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
