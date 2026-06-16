"""
Ze Eval — run scenarios or view results.

Usage:
  python eval/run.py                    # routing accuracy only (cheap)
  python eval/run.py --judge            # + LLM quality scores
  python eval/run.py --tag routing      # filter by tag
  python eval/run.py report             # show last run summary
  python eval/run.py report --compare   # diff last two runs
"""
from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        sys.argv.pop(1)
        from ze_eval.report import main as report_main
        report_main()
    else:
        from ze_eval.runner import main as runner_main
        runner_main()


if __name__ == "__main__":
    main()
