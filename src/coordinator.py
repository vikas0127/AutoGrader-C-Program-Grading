import json, re, tempfile, hashlib, shutil, platform
from pathlib import Path
from src.runner import compile_c_program, run_compiled_program
from src.scoring import load_rules, calculate_score
from src.reporting import write_reports
from analyzers.correctness import evaluate_correctness
from analyzers.memory_safety import check_memory_safety
from analyzers.static_analysis import analyze_static
from analyzers.syntax import analyze_syntax
from analyzers.complexity import analyze_complexity
from analyzers.similarity import analyze_similarity
from analyzers.originality import analyze_originality
from analyzers.modularity import analyze_modularity
from analyzers.logical import analyze_logical
from analyzers.readability import analyze_readability
from analyzers.structure import analyze_structure

EXECUTION_METRICS={"correctness","logical","complexity","memory_safety"}
SOURCE_METRICS={"syntax","structure","modularity","readability","originality"}


def _static_sanity(source):
    text=Path(source).read_text(encoding="utf-8",errors="replace")
    clean=re.sub(r"/\*.*?\*/|//[^\n]*", " ",text,flags=re.S)
    checks={"main_present":bool(re.search(r"\bmain\s*\(",clean)),
            "reader_present":bool(re.search(r"\b(scanf|fscanf|getchar|fgets|read)\s*\(",clean)),
            "writer_present":bool(re.search(r"\b(printf|fprintf|putchar|puts|write)\s*\(",clean)),
            "return_present":bool(re.search(r"\breturn\b",clean))}
    return checks


def _result(name,status="skipped",feedback="Skipped by first-pass policy."):
    return {"name":name,"status":status,"score":None,"max_score":100,"evidence":None,"feedback":feedback,"error":None}


def evaluate_submission(source,tests,rules_path="rules/rules.json",output_dir="reports",timeout=2.0,references=None,memory_limit_mb=None,prebuilt_executable=None,project_mode=False,prebuild_result=None,source_paths=None,sanitizer_sources=None,reference_program=None):
    src=Path(source).resolve(); cases=json.loads(Path(tests).read_text(encoding="utf-8"))
    if not isinstance(cases,list) or any(not isinstance(c,dict) or
            ("expected_output" not in c and reference_program is None) for c in cases):
        raise ValueError("Tests must be a JSON list; each case needs expected_output unless --reference-program is supplied")
    rules=load_rules(rules_path); metric_rules=rules["metrics"]
    time_limit=float(rules.get("time_limit_s",timeout)); memory_limit_mb=memory_limit_mb or rules.get("memory_limit_mb",64)
    sandbox_mode = rules.get("execution", {}).get("sandbox_mode", "off")
    source_paths=[Path(x).resolve() for x in (source_paths or [src]) if Path(x).is_file()] or [src]
    results=[]; errors=[]; first_pass={"compiled":False,"smoke_ok":False,"suspected_infinite_loop":False,"static_sanity":None}
    with tempfile.TemporaryDirectory(prefix="autograder_") as td:
        comp=(prebuild_result if prebuild_result is not None else
              ({"status":"ok","executable_path":str(Path(prebuilt_executable).resolve()),"returncode":0,
                "stdout":"","stderr":"","build_kind":"flex_bison_project"}
               if prebuilt_executable else compile_c_program(src,td,flags=rules.get("compile_flags",["-O2","-Wall","-Wextra","-std=c11"]))))
        reference_comp = None
        if reference_program:
            reference_comp = compile_c_program(reference_program, Path(td) / "trusted_reference",
                timeout=float(rules.get("compile_timeout_s", 15)),
                flags=rules.get("compile_flags", ["-O2", "-Wall", "-Wextra", "-std=c11"]))
            if reference_comp.get("status") != "ok":
                raise ValueError("Trusted reference program failed to compile: " + reference_comp.get("stderr", ""))
        first_pass["compiled"]=comp["status"]=="ok"
        first_pass["project_mode"] = bool(project_mode)
        if comp["status"]=="ok":
            first_pass["static_sanity"]=_static_sanity(src)
            # Mirror the first trusted case's execution context, including argv
            # and staged files, so the smoke check also works for file-driven tasks.
            smoke_case = cases[0] if cases else {}
            smoke_input = smoke_case.get("input", "")
            smoke_args = smoke_case.get("args", [])
            with tempfile.TemporaryDirectory(prefix="autograder_smoke_") as smoke_dir:
                try:
                    for rel, content in (smoke_case.get("files") or {}).items():
                        target = (Path(smoke_dir) / rel).resolve()
                        if not target.is_relative_to(Path(smoke_dir).resolve()):
                            raise ValueError(f"Unsafe smoke input file path: {rel}")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(str(content), encoding="utf-8")
                    smoke = run_compiled_program(
                        comp["executable_path"], smoke_input,
                        timeout=min(time_limit, 1.0), memory_limit_mb=memory_limit_mb,
                        args=smoke_args, cwd=smoke_dir, sandbox_mode=sandbox_mode)
                except (OSError, ValueError, TypeError) as exc:
                    smoke = {"status": "error", "error": "invalid_smoke_case", "stderr": str(exc)}
            first_pass["smoke_ok"] = smoke["status"] == "ok"
            first_pass["suspected_infinite_loop"] = smoke["status"] == "timeout"
            first_pass["smoke_status"] = smoke["status"]
            first_pass["smoke_error"] = smoke.get("error")
            first_pass["smoke_stderr"] = smoke.get("stderr", "")
        # Dispatch only enabled rubric analyzers; execution metrics are skipped on failed first pass.
        for name,config in metric_rules.items():
            if not config.get("enabled",False):
                results.append(_result(name,"skipped","Metric disabled by rules.")); continue
            params=config.get("params",{})
            if comp["status"]!="ok" and name in EXECUTION_METRICS:
                results.append(_result(name,"skipped","Compilation failed; execution analyzer not run.")); continue
            if name in EXECUTION_METRICS and not first_pass["smoke_ok"]:
                results.append(_result(name,"skipped","First-pass smoke test failed; execution analyzer skipped.")); continue
            if name=="correctness":
                r=evaluate_correctness(comp["executable_path"],cases,time_limit,memory_limit_mb,
                    reference_executable=(reference_comp or {}).get("executable_path"),
                    sandbox_mode=sandbox_mode)
            elif name in {"syntax", "structure", "modularity", "complexity", "readability"}:
                analyzer_map={"syntax":analyze_syntax,"structure":analyze_structure,
                    "modularity":analyze_modularity,"complexity":analyze_complexity,
                    "readability":analyze_readability}
                per_file=[analyzer_map[name](path,params) for path in source_paths]
                score_values=[float(x.score) for x in per_file if x.status=="ok" and isinstance(x.score,(int,float))]
                combined_status="ok" if score_values else "error"
                combined_score=round(sum(score_values)/len(score_values),2) if score_values else None
                r=_result(name,combined_status,"Aggregated across all submitted C source files.")
                r["score"]=combined_score
                r["evidence"]={"files":[{"path":str(path),"status":item.status,"score":item.score,"evidence":item.evidence,"feedback":item.feedback} for path,item in zip(source_paths,per_file)]}
                r["feedback"]=f"Analyzed {len(per_file)} source file(s); mean score {combined_score:.2f}." if score_values else "No source file could be analyzed."
            elif name=="logical": r=analyze_logical(comp["executable_path"],cases,time_limit,memory_limit_mb,params)
            elif name=="memory_safety":
                if project_mode and (prebuild_result or {}).get("build_kind") == "flex_bison":
                    r=_result(name,"skipped","ASan/UBSan instrumentation for generated Flex/Bison sources is not enabled; ordinary multi-file C projects are instrumented.")
                else:
                    r=check_memory_safety(src,cases,time_limit,memory_limit_mb,params,sources=(sanitizer_sources or source_paths))
            elif name=="originality":
                refs=list(references or [])
                corpus=params.get("corpus_dir")
                if not refs and corpus:
                    corpus_path=Path(corpus)
                    if not corpus_path.is_absolute(): corpus_path=Path.cwd()/corpus_path
                    if corpus_path.is_dir(): refs=[str(x) for x in sorted(corpus_path.glob("*.c")) if x.resolve()!=src]
                if project_mode and len(source_paths) > 1:
                    with tempfile.NamedTemporaryFile(mode="w",suffix=".c",encoding="utf-8",delete=False) as combined:
                        combined_path=Path(combined.name)
                        for source_path in source_paths:
                            combined.write("\n/* FILE: "+source_path.name+" */\n")
                            combined.write(source_path.read_text(encoding="utf-8",errors="replace"))
                    try: r=analyze_originality(combined_path,refs,params)
                    finally: combined_path.unlink(missing_ok=True)
                else:
                    r=analyze_originality(src,refs,params)
            else: r=_result(name,"skipped",f"Unknown analyzer '{config.get('analyzer',name)}'.")
            results.append(r.to_dict() if hasattr(r, "to_dict") else r)
    if comp["status"]!="ok":
        first_pass["correctness_verification"] = "not_run_compile_failure"
        errors.extend(["Compilation failed",comp.get("stderr","")])
    errors.extend(f"{r['name']}: {r.get('feedback','')}" for r in results if r["status"]=="error")
    try: scored=calculate_score(rules,results); overall=scored["overall_score"]
    except ValueError as exc: scored=None; overall=None; errors.append("Overall score not calculated: "+str(exc))
    grade_status="complete"
    if comp["status"]!="ok" and scored is not None:
        compile_cap=float(rules.get("grading_policy",{}).get("compile_failure_score",0))
        scored["overall_score"]=compile_cap
        scored["score_cap"]=compile_cap
        scored["cap_applied"]=True
        scored["cap_reason"]="Submission did not compile; source-only metrics are reported as diagnostic evidence."
        overall=compile_cap
        grade_status="compile_failure"
    elif not first_pass["smoke_ok"]:
        grade_status="execution_blocked"
        # A failed smoke test means correctness was never evaluated. Apply an
        # explicit configurable cap instead of silently awarding a high score
        # from source-only metrics.
        smoke_policy = rules.get("grading_policy", {}).get("first_pass_failure", {})
        trigger_statuses = set(smoke_policy.get("trigger_statuses", ["timeout", "crash", "error"]))
        smoke_status = first_pass.get("smoke_status", "error")
        if (scored is not None and smoke_policy.get("enabled", True)
                and smoke_status in trigger_statuses):
            cap = float(smoke_policy.get("score_cap", 20))
            raw_score = float(scored.get("overall_score", overall or 0))
            scored["raw_weighted_score"] = raw_score
            scored["overall_score"] = min(raw_score, cap)
            scored["score_cap"] = cap
            scored["cap_applied"] = True
            scored["cap_reason"] = (
                f"First-pass smoke test failed with status '{smoke_status}'; "
                "functional correctness could not be verified."
            )
            overall = scored["overall_score"]
        first_pass["correctness_verification"] = "not_run"
        first_pass["grading_warning"] = (
            "First-pass execution failed. Correctness was not evaluated; "
            "the reported score is capped diagnostic credit only."
        )
    else:
        first_pass["correctness_verification"] = "evaluated"
    # Correctness-first policy: award full credit when all configured correctness
    # cases pass and the initial smoke test succeeded. Quality metrics remain in
    # the report as feedback, but do not reduce this default grade.
    correctness_first = rules.get("grading_policy", {}).get("correctness_first", False)
    correctness_result = next((r for r in results if r.get("name") == "correctness"), None)
    correctness_evidence = (correctness_result or {}).get("evidence") or {}
    all_cases_passed = (
        correctness_result is not None
        and correctness_result.get("status") == "ok"
        and isinstance(correctness_evidence.get("cases"), list)
        and len(correctness_evidence["cases"]) > 0
        and all(case.get("passed") is True for case in correctness_evidence["cases"])
    )
    if (grade_status == "complete" and correctness_first and first_pass["smoke_ok"]
            and all_cases_passed and scored is not None):
        scored["raw_weighted_score"] = scored["overall_score"]
        scored["overall_score"] = 100.0
        scored["correctness_first_award"] = True
        scored["correctness_first_reason"] = "All configured correctness tests passed and the smoke test succeeded."
        overall = 100.0
    elif scored is not None:
        scored["correctness_first_award"] = False
    details=scored.get("metrics",{}) if scored else {}; results_by_name={r["name"]:r for r in results}; metrics={}
    for name,config in metric_rules.items():
        r=results_by_name.get(name,_result(name)); d=details.get(name,{})
        metrics[name]={"status":r["status"],"score":r.get("score"),"weight":config.get("weight",0),
          "threshold":config.get("threshold",0),"threshold_met":d.get("threshold_met"),
          "effective_weight":d.get("effective_weight",0),"contribution":d.get("contribution"),
          "evidence":r.get("evidence"),"feedback":r.get("feedback"),"error":r.get("error")}
    score_summary=None if scored is None else {"raw_weighted_score":scored["raw_weighted_score"],"final_score":scored["overall_score"],
      "score_cap":scored.get("score_cap"),"cap_applied":scored.get("cap_applied",False),"cap_reason":scored.get("cap_reason")}
    def _sha256(path):
        try: return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError: return None
    flags=[]
    if first_pass.get("suspected_infinite_loop"):
        flags.append({"type":"suspected_infinite_loop","evidence":"First-pass smoke test timed out.",
          "note":"Correctness tests were not run. Score is limited by the configured first-pass failure cap."})
    elif comp["status"] == "ok" and not first_pass.get("smoke_ok"):
        flags.append({"type":"first_pass_execution_failure","evidence":first_pass.get("smoke_status"),
          "note":"Correctness was not verified because the initial execution did not complete."})
    originality=metrics.get("originality",{})
    originality_evidence=originality.get("evidence") or {}
    if originality_evidence.get("suspected_copying_flag"):
        flags.append({"type":"suspected_similarity","metric":"originality",
          "similarity_percent":originality_evidence.get("best_similarity_percent"),
          "threshold_percent":originality_evidence.get("flag_threshold_percent"),
          "note":"Requires human review; similarity is not proof of copying or LLM use."})
    # A separate diagnostic/quality score excludes functional correctness and
    # the optional logical metric (which can duplicate correctness evidence).
    quality_items = []
    for metric_name, metric in metrics.items():
        if metric_name in {"correctness", "logical"}:
            continue
        if metric.get("status") == "ok" and isinstance(metric.get("score"), (int, float)):
            quality_items.append((float(metric.get("weight", 0)), float(metric["score"])))
    quality_weight = sum(weight for weight, _ in quality_items if weight > 0)
    quality_score = (round(sum(weight * value for weight, value in quality_items if weight > 0) / quality_weight, 2)
                     if quality_weight > 0 else None)
    report={"source_file":str(src),"source_sha256":_sha256(src),"rules_sha256":_sha256(rules_path),
      "overall_score":overall,"quality_score":quality_score,
      "quality_score_note":"Weighted average of scoreable non-correctness quality/diagnostic metrics; skipped metrics are excluded and remaining weights are renormalized.",
      "grade_status":grade_status,"first_pass":first_pass,"metrics":metrics,"flags":flags,"errors":errors,
      "compilation":comp,"score_calculation":scored,"score_summary":score_summary,"test_cases_total":len(cases),
      "rules_file":str(Path(rules_path).resolve()),"rules":rules,
      "submission_mode":"multi_file_project" if project_mode else "standalone_c",
      "source_files_analyzed":[str(x) for x in source_paths],
      "source_sha256_by_file":{str(x):_sha256(x) for x in source_paths},
      "tool_versions":{"python":platform.python_version(),"gcc":shutil.which("gcc")},
      "usefulness_limitations":{"usefulness":[
        {"use_case":"Large programming courses","example":"Apply one test suite and rubric to hundreds of submissions.","benefit":"Consistent, repeatable grading and faster feedback."},
        {"use_case":"Introductory programming feedback","example":"Show an input that causes a wrong answer with expected and actual output.","benefit":"Students can reproduce and debug failures."},
        {"use_case":"Code-quality screening","example":"Report warning, structure, modularity and readability indicators.","benefit":"Instructor can assess more than output correctness."},
        {"use_case":"Originality triage","example":"Flag submissions above a configurable source similarity threshold.","benefit":"Focus human review on candidate pairs; does not prove copying."}],
        "limitations":[
        {"limitation":"Finite tests do not prove correctness","example":"A program passes supplied tests but fails an untested extreme input."},
        {"limitation":"Sanitizers only detect executed defects","example":"An invalid access exists in a branch none of the supplied inputs reach."},
        {"limitation":"Similarity can have false positives and negatives","example":"A short mandated solution looks similar, or copied code is heavily refactored."},
        {"limitation":"Heuristic source analyzers can misestimate properties","example":"A loop bound depends on input in a way the lexical estimator does not recognize."}]},
      "limitations":["POSIX resource limits are not a complete security sandbox; use a disposable lab container/VM for untrusted code.",
        "Sanitizers detect only errors triggered by supplied test inputs.","Complexity, structure, readability and similarity are heuristic.",
        "A similarity flag is not proof of plagiarism or LLM use."]}
    return report | {"report_paths":write_reports(report,output_dir)}
