"""ASan/UBSan runtime checking; findings are limited to executed paths."""
import os, shutil, subprocess, tempfile
from pathlib import Path
from analyzers.interface import AnalyzerResult
from src.runner import run_compiled_program


def check_memory_safety(source,cases,timeout=2.0,memory_limit_mb=None,params=None,sources=None):
    params=params or {}; gcc=shutil.which("gcc")
    if not gcc: return AnalyzerResult("memory_safety","error",None,feedback="GCC not found.",error="gcc_missing")
    src=Path(source).resolve()
    source_list=[Path(x).resolve() for x in (sources or [src])]
    if not source_list or any(not x.is_file() for x in source_list): return AnalyzerResult("memory_safety","error",None,feedback="One or more source files are missing.",error="source_missing")
    flags=params.get("flags",["-fsanitize=address,undefined"])
    if isinstance(flags,str): flags=flags.split()
    with tempfile.TemporaryDirectory(prefix="autograder_asan_") as td:
        exe=Path(td)/("instrumented.exe" if os.name=="nt" else "instrumented")
        try:
            built=subprocess.run([gcc,"-std=c11","-g","-O1","-fno-omit-frame-pointer",*flags,*[str(x) for x in source_list],"-o",str(exe)],
                                 capture_output=True,text=True,timeout=20)
        except (OSError,subprocess.TimeoutExpired) as exc:
            return AnalyzerResult("memory_safety","error",None,feedback=f"Sanitizer compilation unavailable: {exc}",error="build_failed")
        if built.returncode:
            return AnalyzerResult("memory_safety","error",None,evidence={"compiler_stderr":built.stderr},
                                  feedback="Sanitizer build failed; this is not itself evidence of a student memory bug.",error="sanitizer_build_failed")
        findings=[]
        for i,case in enumerate(cases):
            with tempfile.TemporaryDirectory(prefix="autograder_asan_case_") as case_dir:
                for rel, content in (case.get("files") or {}).items():
                    target=(Path(case_dir)/rel).resolve()
                    if not target.is_relative_to(Path(case_dir).resolve()): continue
                    target.parent.mkdir(parents=True,exist_ok=True); target.write_text(str(content),encoding="utf-8")
                run=run_compiled_program(exe,case.get("input",""),timeout=timeout,
                    memory_limit_mb=None if os.name=="posix" else memory_limit_mb,
                    args=case.get("args",[]),cwd=case_dir)
            diag=run.get("stderr","") or ""
            tool_unavailable=any(x in diag for x in ("ASan runtime does not come first", "Shadow memory range interleaves", "AddressSanitizer: failed to allocate"))
            asan=any(x in diag for x in ("AddressSanitizer", "runtime error:", "LeakSanitizer"))
            status="timeout" if run["status"]=="timeout" else ("tool_unavailable" if tool_unavailable else ("memory_error" if asan else ("runtime_error" if run["status"]=="error" else "clean")))
            findings.append({"name":case.get("name",f"case_{i+1}"),"input":case.get("input",""),"status":status,
                             "returncode":run.get("returncode"),"diagnostic":diag[-3000:]})
        if any(x["status"]=="tool_unavailable" for x in findings):
            return AnalyzerResult("memory_safety","error",None,evidence={"cases":findings},
              feedback="Sanitizer runtime is unavailable/incompatible in this environment; this is not a student memory-safety verdict.",error="sanitizer_runtime_unavailable")
        issue_count=sum(x["status"] in {"memory_error","runtime_error"} for x in findings)
        score=100.0 if not findings else round(100*(len(findings)-issue_count)/len(findings),2)
        return AnalyzerResult("memory_safety","ok",score,evidence={"issues_detected":issue_count,"cases":findings},
          feedback=f"Detected runtime/sanitizer issues in {issue_count}/{len(findings)} test runs. A clean run is not proof of memory safety.")
