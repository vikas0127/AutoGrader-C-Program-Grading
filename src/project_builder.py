"""Configurable, shell-free builder for arbitrary C source projects."""
from __future__ import annotations
import os, shutil, subprocess
from pathlib import Path

ALLOWED_TOOLS = {"gcc", "clang", "flex", "bison"}

def _run(command, cwd, timeout):
    try:
        p = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
        return {"command": command, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"command": command, "returncode": None, "stdout": "", "stderr": f"Build step timed out after {timeout}s: {exc}"}
    except OSError as exc:
        return {"command": command, "returncode": None, "stdout": "", "stderr": str(exc)}

def build_project(project_dir, build_dir, config=None, timeout=30):
    """Build a project using auto/gcc/flex_bison/custom argv configuration.

    Custom steps are argument arrays (never shell strings), and executable tools
    are allow-listed. Placeholders: {project}, {build}, {exe}.
    """
    project, build = Path(project_dir).resolve(), Path(build_dir).resolve()
    config = config or {}
    build.mkdir(parents=True, exist_ok=True)
    files = [p for p in project.rglob("*") if p.is_file() and build not in p.parents]
    c_files = sorted(p for p in files if p.suffix.lower() == ".c")
    lex_files = sorted(p for p in files if p.suffix.lower() == ".l")
    yacc_files = sorted(p for p in files if p.suffix.lower() in {".y", ".yy"})
    mode = str(config.get("build_system", "auto")).lower()
    if mode == "auto": mode = "flex_bison" if lex_files and yacc_files else "gcc"
    if mode not in {"gcc", "flex_bison", "custom"}:
        return {"status":"error","error":"invalid_build_mode","stderr":f"Unsupported build_system: {mode}"}
    if not files:
        return {"status":"error","error":"empty_project","stderr":"The uploaded project contains no files."}
    exe = build / ("submission.exe" if os.name == "nt" else "submission")
    logs = []
    def fail(kind):
        return {"status":"error","error":kind,"stderr":"\n".join(x["stderr"] for x in logs),"build_steps":logs,"build_kind":mode}
    if mode == "custom":
        steps = config.get("steps")
        if not isinstance(steps, list) or not steps:
            return {"status":"error","error":"missing_build_steps","stderr":"Custom mode needs a non-empty steps array of argv arrays."}
        for step in steps:
            if not isinstance(step, list) or not step or not isinstance(step[0], str):
                return {"status":"error","error":"invalid_build_step","stderr":"Each build step must be an argv array."}
            tool = Path(step[0]).name
            if tool not in ALLOWED_TOOLS:
                return {"status":"error","error":"disallowed_build_tool","stderr":f"Build tool '{tool}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_TOOLS))}."}
            argv = [str(x).replace("{project}", str(project)).replace("{build}", str(build)).replace("{exe}", str(exe)) for x in step]
            resolved = shutil.which(argv[0])
            if not resolved:
                return {"status":"error","error":"toolchain_missing","stderr":f"Required tool not found: {argv[0]}"}
            argv[0] = resolved
            log = _run(argv, project, timeout); logs.append(log)
            if log["returncode"] != 0: return fail("build_step_failed")
        if not exe.is_file(): return fail("executable_missing")
    else:
        if mode == "flex_bison":
            if len(lex_files) != 1 or len(yacc_files) != 1:
                return {"status":"error","error":"project_layout","stderr":"Flex/Bison mode requires exactly one .l and one .y/.yy file."}
            flex, bison = shutil.which("flex"), shutil.which("bison")
            if not flex or not bison:
                return {"status":"error","error":"toolchain_missing","stderr":"Install Flex and Bison: sudo apt install flex bison"}
            parser_c, lexer_c = build/"parser.tab.c", build/"lexer.yy.c"
            for cmd in ([bison, "-d", "-o", str(parser_c), str(yacc_files[0])], [flex, "-o", str(lexer_c), str(lex_files[0])]):
                log = _run(cmd, project, timeout); logs.append(log)
                if log["returncode"] != 0: return fail("generator_failed")
            c_files += [lexer_c, parser_c]
        if not c_files:
            return {"status":"error","error":"no_c_sources","stderr":"No .c source files found."}
        compiler_name = str(config.get("compiler", "gcc"))
        if Path(compiler_name).name not in {"gcc", "clang"}:
            return {"status":"error","error":"disallowed_compiler","stderr":"Only gcc and clang are supported."}
        compiler = shutil.which(compiler_name)
        if not compiler: return {"status":"error","error":"toolchain_missing","stderr":f"{compiler_name} not found on PATH."}
        flags = config.get("flags", ["-std=c11", "-O2", "-Wall", "-Wextra"])
        if not isinstance(flags, list) or any(not isinstance(x, str) for x in flags):
            return {"status":"error","error":"invalid_flags","stderr":"Compiler flags must be a JSON array of strings."}
        include_dirs = sorted({str(p.parent) for p in files if p.suffix.lower() in {".h", ".hpp"}} | {str(build)})
        cmd = [compiler, *flags, *[f"-I{x}" for x in include_dirs], *[str(p) for p in c_files], "-o", str(exe)]
        log = _run(cmd, project, timeout); logs.append(log)
        if log["returncode"] != 0: return fail("compile_failed")
    return {"status":"ok","executable_path":str(exe),"returncode":0,
            "stdout":"\n".join(x["stdout"] for x in logs),"stderr":"\n".join(x["stderr"] for x in logs),
            "build_steps":logs,"build_kind":mode,
            "source_files":[str(p.relative_to(project)) for p in files if p.suffix.lower() in {".c",".h",".l",".y",".yy"}],
            "compile_sources":[str(p) for p in c_files]}

# Backward-compatible import for earlier project versions.
def build_flex_bison_project(project_dir, build_dir, timeout=30):
    return build_project(project_dir, build_dir, {"build_system":"flex_bison"}, timeout)
