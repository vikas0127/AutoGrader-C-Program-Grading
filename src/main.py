import argparse, json, sys
from src.coordinator import evaluate_submission

def main():
    p=argparse.ArgumentParser(description="Rule-driven C program grader")
    p.add_argument("--source",required=True); p.add_argument("--tests",required=True)
    p.add_argument("--rules",default="rules/rules.json"); p.add_argument("--output-dir",default="reports")
    p.add_argument("--timeout",type=float,default=2.0); p.add_argument("--reference",action="append",default=[])
    p.add_argument("--reference-program", help="Trusted C reference executable source used as a correctness oracle")
    a=p.parse_args()
    try:
        r=evaluate_submission(a.source,a.tests,a.rules,a.output_dir,a.timeout,a.reference,
                              reference_program=a.reference_program)
        print(json.dumps({"overall_score":r["overall_score"],"report_paths":r["report_paths"],"errors":r["errors"]},indent=2))
        return 0 if r["overall_score"] is not None else 2
    except (OSError,ValueError,json.JSONDecodeError) as e:
        print(f"AutoGrader error: {e}",file=sys.stderr); return 1
if __name__=="__main__": raise SystemExit(main())
