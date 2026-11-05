import shutil, subprocess
from pathlib import Path
from analyzers.interface import AnalyzerResult

def analyze_static(source,flags=None):
    gcc=shutil.which("gcc")
    if not gcc: return AnalyzerResult("static_analysis","error",None,feedback="GCC not found.",error="gcc_missing")
    source_path=Path(source).resolve()
    if not source_path.is_file(): return AnalyzerResult("static_analysis","error",None,feedback="Source not found.",error="source_missing")
    flags=flags or ["-std=c11","-Wall","-Wextra","-Wpedantic","-fsyntax-only"]
    command=[gcc,*flags,str(source_path)]
    try: p=subprocess.run(command,capture_output=True,text=True,timeout=15)
    except (OSError,subprocess.TimeoutExpired) as exc:
        return AnalyzerResult("static_analysis","error",None,feedback=str(exc),error="analysis_failed")
    diag=(p.stdout+p.stderr).strip(); warnings=sum(": warning:" in x for x in diag.splitlines()); errors=sum(": error:" in x for x in diag.splitlines())
    evidence={"warnings":warnings,"errors":errors,"diagnostics":diag,"command":command}
    if p.returncode:
        return AnalyzerResult("static_analysis","error",None,evidence=evidence,feedback="Compiler diagnostics contain errors.",error="syntax_error")
    score=max(0,100-8*warnings)
    return AnalyzerResult("static_analysis","ok",score,evidence=evidence,feedback=f"{warnings} warning(s), {errors} error(s).")
