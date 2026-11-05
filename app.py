"""Polished Streamlit interface for the rule-driven C AutoGrader."""
from __future__ import annotations
import json, tempfile, io, zipfile, csv
from pathlib import Path
import streamlit as st
from src.coordinator import evaluate_submission
from src.project_builder import build_project

ROOT = Path(__file__).resolve().parent
DEFAULT_RULES = ROOT / "rules" / "rules.json"

st.set_page_config(page_title="AutoGrader | DAA Lab", page_icon="🧪", layout="wide", initial_sidebar_state="expanded")

st.markdown(r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --ag-bg:#0b1020; --ag-panel:#111a2e; --ag-line:rgba(148,163,184,.17); --ag-muted:#93a4bd; --ag-text:#e8eef9; --ag-accent:#6ee7c2; --ag-blue:#7c9cff; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background: radial-gradient(ellipse at 80% -15%, rgba(67,97,238,.16), transparent 38%), var(--ag-bg); color:var(--ag-text); }
.block-container { padding-top:1.8rem; max-width:1500px; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#10182b,#0d1424); border-right:1px solid var(--ag-line); }
[data-testid="stSidebar"] .block-container { padding-top:1.3rem; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif!important; letter-spacing:-.035em; }
.ag-hero { padding:1.35rem 1.55rem; border:1px solid var(--ag-line); border-radius:22px; background:linear-gradient(120deg,rgba(24,37,64,.96),rgba(16,25,44,.88)); box-shadow:0 18px 50px rgba(0,0,0,.18); margin-bottom:1.25rem; }
.ag-eyebrow { color:var(--ag-accent); font-size:.75rem; text-transform:uppercase; letter-spacing:.16em; font-weight:700; }
.ag-title { font:700 2.15rem 'Space Grotesk',sans-serif; margin:.35rem 0 .3rem; color:#f3f7ff; }
.ag-sub { color:var(--ag-muted); font-size:.98rem; }
.ag-step { border:1px solid var(--ag-line); border-radius:17px; padding:1rem 1.15rem; background:rgba(17,26,46,.74); margin:.2rem 0 .8rem; }
.ag-step-head { display:flex; align-items:center; gap:.65rem; font-weight:700; font-size:1.08rem; }
.ag-num { display:inline-flex; width:1.8rem;height:1.8rem;align-items:center;justify-content:center;border-radius:9px;background:rgba(110,231,194,.13);color:var(--ag-accent);font-weight:700; }
.ag-muted { color:var(--ag-muted); }
.ag-card { background:linear-gradient(140deg,rgba(21,32,54,.95),rgba(15,23,40,.94)); border:1px solid var(--ag-line); border-radius:16px; padding:1rem 1.1rem; }
.ag-kpi-label { color:var(--ag-muted); font-size:.8rem; font-weight:600; }
.ag-kpi-value { color:#f4f7ff; font:700 1.65rem 'Space Grotesk',sans-serif; margin-top:.25rem; }
.ag-kpi-foot { color:var(--ag-muted); font-size:.75rem; margin-top:.25rem; }
.stButton>button[kind="primary"] { border:0; border-radius:12px; background:linear-gradient(90deg,#5ce1b5,#78a0ff); color:#071322; font-weight:800; min-height:3rem; box-shadow:0 8px 25px rgba(92,225,181,.16); }
.stButton>button { border-radius:10px; }
[data-testid="stFileUploader"] section { border:1px dashed rgba(124,156,255,.42); background:rgba(25,39,66,.42); border-radius:14px; }
[data-testid="stDataFrame"] { border:1px solid var(--ag-line); border-radius:12px; overflow:hidden; }
.stTabs [data-baseweb="tab-list"] { gap:.45rem; border-bottom:1px solid var(--ag-line); }
.stTabs [data-baseweb="tab"] { border-radius:9px 9px 0 0; padding:.7rem 1rem; }
.stExpander { border:1px solid var(--ag-line)!important; border-radius:12px!important; background:rgba(15,23,40,.35); }
hr { border-color:var(--ag-line); }
.small-note { color:var(--ag-muted); font-size:.82rem; }
</style>
""", unsafe_allow_html=True)

# State and rubric load
if "rules_text" not in st.session_state:
    st.session_state.rules_text = DEFAULT_RULES.read_text(encoding="utf-8")
if "test_cases_text" not in st.session_state:
    # Never silently apply tests from an unrelated assignment.
    # Instructor must import or enter a matching trusted test suite.
    st.session_state.test_cases_text = "[]"
    st.session_state.generator_metadata = None

# Sidebar: project settings
with st.sidebar:
    st.markdown("<div class='ag-eyebrow'>Instructor console</div>", unsafe_allow_html=True)
    st.markdown("## Grading configuration")
    rules_upload = st.file_uploader("Import rubric (.json)", type=["json"], key="rules_upload")
    if rules_upload is not None:
        try:
            imported = json.loads(rules_upload.getvalue().decode("utf-8"))
            if not isinstance(imported, dict) or not isinstance(imported.get("metrics"), dict):
                raise ValueError("Rubric must contain a metrics object.")
            st.session_state.rules_text = json.dumps(imported, indent=2)
            st.success("Rubric loaded")
        except Exception as exc:
            st.error(f"Could not load rubric: {exc}")
    try:
        rules_obj = json.loads(st.session_state.rules_text)
        if not isinstance(rules_obj, dict) or not isinstance(rules_obj.get("metrics"), dict):
            raise ValueError("Rubric needs a metrics object")
        rules_valid = True
    except Exception as exc:
        rules_valid = False
        st.error(f"Rubric JSON issue: {exc}")
        rules_obj = {}

    if rules_valid:
        gp = rules_obj.setdefault("grading_policy", {})
        st.markdown("#### Grade philosophy")
        gp["correctness_first"] = st.toggle(
            "Correctness-first scoring", value=bool(gp.get("correctness_first", False)),
            help="Optional override: award 100 when all trusted correctness tests pass. Otherwise use the weighted rubric."
        )
        gp["compile_failure_score"] = st.number_input("Compile failure score", min_value=0, max_value=100,
            value=int(gp.get("compile_failure_score", 0)), step=5)
        smoke_policy = gp.setdefault("first_pass_failure", {})
        smoke_policy["enabled"] = st.checkbox(
            "Cap score when first execution fails",
            value=bool(smoke_policy.get("enabled", True)),
            help="If the smoke test times out, crashes or errors, correctness is marked not run and the weighted diagnostic score is capped."
        )
        smoke_policy["score_cap"] = st.slider(
            "First-pass failure score cap", 0, 100,
            int(smoke_policy.get("score_cap", 20)), 5,
            disabled=not smoke_policy["enabled"]
        )
        st.markdown("#### Metric controls")
        metric_names = list(rules_obj["metrics"].keys())
        enabled_count = 0
        for name in metric_names:
            cfg = rules_obj["metrics"][name]
            with st.expander(f"{'●' if cfg.get('enabled') else '○'} {name.replace('_',' ').title()}", expanded=False):
                cfg["enabled"] = st.checkbox("Include metric", value=bool(cfg.get("enabled", False)), key=f"enabled_{name}")
                if cfg["enabled"]: enabled_count += 1
                cfg["weight"] = st.slider("Weight", 0.0, 1.0, float(cfg.get("weight", 0.0)), .05, key=f"weight_{name}")
                cfg["threshold"] = st.slider("Threshold", 0, 100, int(cfg.get("threshold", 0)), 5, key=f"threshold_{name}")
        total_weight = sum(float(c.get("weight",0)) for c in rules_obj["metrics"].values() if c.get("enabled"))
        if total_weight > 0:
            if st.button("Normalize enabled weights", use_container_width=True):
                for cfg in rules_obj["metrics"].values():
                    if cfg.get("enabled"):
                        cfg["weight"] = float(cfg.get("weight",0))/total_weight
                st.success("Enabled metric weights normalized")
        else:
            st.warning("Enable at least one metric with positive weight.")
        st.caption(f"Enabled metrics: {sum(bool(c.get('enabled')) for c in rules_obj['metrics'].values())} · Weight sum: {total_weight:.2f}")
        st.session_state.rules_text = json.dumps(rules_obj, indent=2)
        with st.expander("Advanced rubric JSON", expanded=False):
            edited = st.text_area("JSON", value=st.session_state.rules_text, height=300, key="advanced_rules")
            try:
                advanced_obj = json.loads(edited)
                if not isinstance(advanced_obj.get("metrics"), dict): raise ValueError("metrics must be an object")
                rules_obj = advanced_obj
                st.session_state.rules_text = json.dumps(rules_obj, indent=2)
                rules_valid = True
            except Exception as exc:
                rules_valid = False
                st.error(f"Invalid JSON: {exc}")
        st.download_button("Export current rubric", data=st.session_state.rules_text, file_name="autograder-rubric.json",
                           mime="application/json", use_container_width=True, disabled=not rules_valid)
    st.divider()
    st.markdown("<div class='small-note'>A grader's resource limits are not a complete sandbox. Use an isolated disposable VM/container for untrusted submissions.</div>", unsafe_allow_html=True)

# Hero
st.markdown("""
<div class="ag-hero">
 <div class="ag-eyebrow">DAA Lab · Automated assessment workspace</div>
 <div class="ag-title">AutoGrader <span style="color:#6ee7c2">/</span> C Assignment Evaluator</div>
 <div class="ag-sub">Compile, test, inspect quality signals, and deliver reproducible feedback from one workspace.</div>
</div>
""", unsafe_allow_html=True)

# Migrate the previous release's submission mode value.
if st.session_state.get("submission_mode") == "Flex/Bison compiler project (.zip)":
    st.session_state["submission_mode"] = "Multi-file C project (.zip)"

# workflow tabs
upload_tab, cases_tab, execution_tab = st.tabs(["① Submission", "② Test suite", "③ Runtime & references"])
with upload_tab:
    st.markdown("<div class='ag-step'><div class='ag-step-head'><span class='ag-num'>1</span> Submit any C assignment</div><p class='ag-muted'>Upload one C file or a ZIP containing a multi-file C project. Build behaviour is configured separately; Makefiles and shell scripts are never executed automatically.</p></div>", unsafe_allow_html=True)
    submission_mode = st.radio("Submission type", ["Standalone C program", "Multi-file C project (.zip)"], horizontal=True, key="submission_mode")
    source_file = None
    project_zip = None
    build_config = {"build_system":"auto", "compiler":"gcc", "flags":["-std=c11","-O2","-Wall","-Wextra"]}
    if submission_mode == "Standalone C program":
        source_file = st.file_uploader("Choose one .c source file", type=["c"], key="source_file", label_visibility="collapsed")
        if source_file:
            st.success(f"Ready: {source_file.name} · {len(source_file.getvalue()):,} bytes")
            with st.expander("Preview source", expanded=False):
                st.code(source_file.getvalue().decode("utf-8", errors="replace"), language="c")
    else:
        project_zip = st.file_uploader("Upload project ZIP (.c, .h, .l, .y/.yy and subfolders)", type=["zip"], key="project_zip")
        build_mode = st.selectbox("Project build system", ["auto", "gcc", "flex_bison", "custom"], help="Auto detects a Flex/Bison pair; otherwise compiles all C files recursively.")
        default_build_json = json.dumps({"build_system":build_mode,"compiler":"gcc","flags":["-std=c11","-O2","-Wall","-Wextra"]}, indent=2)
        build_json = st.text_area("Build configuration (JSON)", value=default_build_json, height=150, key="project_build_json")
        try:
            build_config = json.loads(build_json)
            if not isinstance(build_config, dict): raise ValueError("Build configuration must be a JSON object.")
            build_config["build_system"] = build_mode
            build_config_valid = True
        except Exception as exc:
            build_config_valid = False
            st.error(f"Build configuration: {exc}")
        if project_zip:
            st.success(f"Project received: {project_zip.name} · {len(project_zip.getvalue()):,} bytes")
            st.info("The ZIP may contain nested source folders. Auto mode supports ordinary multi-file C and conventional Flex/Bison projects. Custom mode accepts allow-listed argv build steps, never shell commands.")
with cases_tab:
    st.markdown("<div class='ag-step'><div class='ag-step-head'><span class='ag-num'>2</span> Configure assignment test cases</div><p class='ag-muted'>Use the instructor-provided test suite or enter trusted test cases for the assignment being graded. This grader is not tied to any particular C problem.</p></div>", unsafe_allow_html=True)
    st.warning("Universal C grading: no problem template is selected. The grader can compile and execute many kinds of C programs, but it cannot infer what an arbitrary program is supposed to do. Correctness scoring requires trusted expected outputs from the assignment specification, instructor, or a verified reference implementation.")
    st.markdown("**Test case fields**")
    st.markdown("- `input`: text sent to standard input (optional if args/files are used).")
    st.markdown("- `args`: command-line arguments as a JSON array.")
    st.markdown("- `files`: input files staged in a fresh working directory.")
    st.markdown("- `expected_output`: trusted expected standard output (required).")
    st.markdown("- `expected_files`: expected contents of files the program should create (optional).")
    st.info("For compiler assignments (such as Flex/Bison projects), provide source-language test programs as `input` and the verified compiler output as `expected_output`. For file-producing programs, use `files` and `expected_files` as needed.")
    imported_suite = st.file_uploader("Import instructor test suite (.json)", type=["json"], key="test_suite_upload")
    if imported_suite is not None:
        try:
            parsed_suite = json.loads(imported_suite.getvalue().decode("utf-8"))
            if not isinstance(parsed_suite, list) or not parsed_suite or any(
                not isinstance(c, dict) or "expected_output" not in c or
                not any(k in c for k in ("input", "args", "files")) or
                not isinstance(c.get("args", []), list) or not isinstance(c.get("files", {}), dict) or
                not isinstance(c.get("expected_files", {}), dict) for c in parsed_suite
            ):
                raise ValueError("Each case needs expected_output and at least one of input, args or files. Optional args must be an array and files/expected_files must be objects.")
            st.session_state.test_cases_text = json.dumps(parsed_suite, indent=2)
            st.session_state.generator_metadata = {"suite_source": "instructor_imported", "test_cases": len(parsed_suite)}
            st.success(f"Imported {len(parsed_suite)} trusted test cases.")
        except Exception as exc:
            st.error(f"Could not import test suite: {exc}")
    st.text_area(
        "Test cases (JSON)",
        key="test_cases_text",
        height=380,
        help="Enter the exact test cases for this assignment. Each case needs expected_output and at least one of input, args or files."
    )
    ca, cb = st.columns(2)
    ca.download_button("Download test suite", data=st.session_state.test_cases_text, file_name="test-cases.json", mime="application/json", use_container_width=True)
    cb.caption("Import or enter the trusted test suite and configure the build for the assignment being graded.")
with execution_tab:
    st.markdown("<div class='ag-step'><div class='ag-step-head'><span class='ag-num'>3</span> Runtime controls</div><p class='ag-muted'>Choose conservative limits for your environment. Use a sandbox for submissions you do not trust.</p></div>", unsafe_allow_html=True)
    ea, eb, ec = st.columns(3)
    timeout = ea.number_input("Timeout (seconds)", min_value=.1, max_value=60.0, value=2.0, step=.1)
    memory_mb = eb.number_input("Memory (MB)", min_value=16, max_value=4096, value=64, step=16)
    refs = ec.text_input("Reference C files (optional)", placeholder="/path/ref.c, /path/another.c", help="Accessible paths in the grader's WSL filesystem.")

try:
    test_cases = json.loads(st.session_state.test_cases_text)
    test_cases_valid = isinstance(test_cases, list) and bool(test_cases) and all(
        isinstance(c, dict) and "expected_output" in c and
        ("input" in c or "args" in c or "files" in c) and
        isinstance(c.get("args", []), list) and isinstance(c.get("files", {}), dict) and
        isinstance(c.get("expected_files", {}), dict) for c in test_cases)
    if not test_cases_valid: raise ValueError("Add at least one test case. Each case must include expected_output and one of input, args, or files.")
except Exception as exc:
    test_cases_valid = False
    if st.session_state.test_cases_text.strip() in ("", "[]", "null"):
        st.info("No test suite configured yet. Import the instructor test cases or create a matching suite in the Test suite tab.")
    else:
        st.warning(f"Test suite not ready: {exc}")

# status summary and action
k1,k2,k3 = st.columns(3)
with k1:
    _ready = bool(source_file) if submission_mode == "Standalone C program" else bool(project_zip)
    _label = source_file.name if source_file else (project_zip.name if project_zip else "Upload a submission above")
    st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Submission</div><div class='ag-kpi-value'>{'Ready' if _ready else 'Waiting'}</div><div class='ag-kpi-foot'>{_label}</div></div>", unsafe_allow_html=True)
with k2: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Test suite</div><div class='ag-kpi-value'>{len(test_cases) if test_cases_valid else '—'}</div><div class='ag-kpi-foot'>{'Cases validated' if test_cases_valid else 'Fix JSON validation'}</div></div>", unsafe_allow_html=True)
with k3: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Rubric</div><div class='ag-kpi-value'>{'Valid' if rules_valid else 'Invalid'}</div><div class='ag-kpi-foot'>{'Correctness-first' if rules_obj.get('grading_policy',{}).get('correctness_first') else 'Weighted rubric'}</div></div>", unsafe_allow_html=True)

st.write("")
# Test suites are assignment-specific and independent of any built-in
# problem template. No template-selection state is required.
submission_ready = (source_file is not None) if submission_mode == "Standalone C program" else (project_zip is not None)
can_grade = submission_ready and test_cases_valid and rules_valid and (submission_mode == "Standalone C program" or build_config_valid)

if not submission_ready:
    st.info("Upload a submission in the Submission tab to enable grading.")
elif not test_cases_valid:
    st.warning("Import or enter a valid assignment-specific test suite in the Test suite tab. Correctness grading requires trusted expected_output values for every case.")
if st.button("Run grading pipeline  →", type="primary", disabled=not can_grade, use_container_width=True):
    with st.status("Running assessment pipeline…", expanded=True) as status:
        st.write("Compiling with configured GCC flags")
        with tempfile.TemporaryDirectory(prefix="autograder_ui_") as td:
            tp=Path(td); testp=tp/"test_cases.json"; rulep=tp/"rules.json"; out=tp/"reports"
            testp.write_text(json.dumps(test_cases,indent=2),encoding="utf-8"); rulep.write_text(json.dumps(rules_obj,indent=2),encoding="utf-8")
            prebuilt_executable=None; project_mode=(submission_mode == "Multi-file C project (.zip)")
            build_result=None; project_source_paths=[]
            if project_mode:
                project_dir=tp/"project"; project_dir.mkdir()
                try:
                    with zipfile.ZipFile(io.BytesIO(project_zip.getvalue())) as zf:
                        infos=zf.infolist()
                        if len(infos)>500 or sum(x.file_size for x in infos)>50*1024*1024:
                            raise ValueError("Project ZIP exceeds safety limits (500 entries / 50 MB uncompressed).")
                        for member in infos:
                            target=(project_dir/member.filename).resolve()
                            if not target.is_relative_to(project_dir.resolve()):
                                raise ValueError("Unsafe ZIP path detected; archive extraction stopped.")
                            if member.is_dir(): target.mkdir(parents=True,exist_ok=True)
                            else:
                                target.parent.mkdir(parents=True,exist_ok=True)
                                target.write_bytes(zf.read(member))
                    c_sources=sorted(project_dir.rglob("*.c"))
                    project_source_paths=[str(x) for x in c_sources]
                    if not c_sources:
                        raise ValueError("No .c source files found in the project ZIP.")
                    build_dir=tp/"build"
                    build_result=build_project(project_dir,build_dir,build_config,timeout=30)
                    src=next((p for p in c_sources if p.name.lower() in {"main.c","driver.c"}),c_sources[0])
                    if build_result.get("status")=="ok":
                        prebuilt_executable=build_result["executable_path"]
                        st.success(f"Project built successfully ({build_result.get('build_kind')}).")
                    else:
                        st.error("Project build failed. Correctness cannot be verified; build diagnostics are included in the assessment.")
                    with st.expander("Build log",expanded=build_result.get("status")!="ok"):
                        for step in build_result.get("build_steps",[]):
                            st.code("$ "+" ".join(step.get("command",[]))+"\n"+step.get("stderr",""))
                except Exception as exc:
                    status.update(label="Invalid project ZIP",state="error"); st.error(str(exc)); st.stop()
            else:
                src=tp/Path(source_file.name).name
                src.write_bytes(source_file.getvalue())
            ref_paths=[]; ref_error=None
            for raw in refs.split(","):
                raw=raw.strip()
                if raw:
                    if not Path(raw).is_file(): ref_error=f"Reference file does not exist: {raw}"; break
                    ref_paths.append(raw)
            if ref_error:
                status.update(label="Assessment configuration issue", state="error"); st.error(ref_error)
            else:
                st.write("Executing configured tests and analyzers")
                try:
                    result=evaluate_submission(str(src),str(testp),str(rulep),str(out),timeout=float(timeout),references=ref_paths,memory_limit_mb=int(memory_mb),prebuilt_executable=prebuilt_executable,project_mode=project_mode,prebuild_result=(build_result if project_mode else None),source_paths=(project_source_paths if project_mode else None),sanitizer_sources=((build_result or {}).get("compile_sources") if project_mode and build_result and build_result.get("status")=="ok" else project_source_paths))
                    st.session_state["grade_result"]=result
                    st.session_state["report_json"]=Path(result["report_paths"]["json"]).read_bytes()
                    st.session_state["report_txt"]=Path(result["report_paths"]["text"]).read_bytes()
                    status.update(label="Assessment complete", state="complete")
                except Exception as exc:
                    status.update(label="Assessment failed", state="error"); st.exception(exc)

# report display
if "grade_result" in st.session_state:
    result=st.session_state.grade_result
    raw=st.session_state.report_json
    try: report=json.loads(raw.decode("utf-8"))
    except Exception: report={}
    st.markdown("## Assessment results")
    score=result.get("overall_score")
    grade_status=result.get("grade_status","unknown")
    if grade_status in ("partial", "execution_blocked"):
        st.warning(report.get("first_pass", {}).get("grading_warning",
            "First-pass execution did not complete. Correctness was not verified; this is a partial diagnostic grade."))
    elif grade_status=="compile_failure": st.error("Compilation failed. Source analyzer outputs are diagnostic only.")
    if report.get("score_summary", {}).get("cap_applied"):
        st.caption(f"Score cap applied: {report['score_summary'].get('score_cap')}/100 — {report['score_summary'].get('cap_reason')}")
    elif report.get("score_calculation",{}).get("correctness_first_award"): st.success("Correctness-first policy applied: all configured correctness tests passed. Quality signals are shown as feedback.")
    correctness_metric = (report.get("metrics", {}).get("correctness", {}) or {})
    correctness_score = correctness_metric.get("score")
    correctness_status = correctness_metric.get("status", "unknown")
    r1,r2,r3,r4,r5=st.columns(5)
    with r1: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Weighted rubric</div><div class='ag-kpi-value'>{score if score is not None else '—'}<span style='font-size:.9rem;color:#93a4bd'> / 100</span></div><div class='ag-kpi-foot'>{grade_status.replace('_',' ').title()}</div></div>",unsafe_allow_html=True)
    with r2: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Functional correctness</div><div class='ag-kpi-value'>{f'{correctness_score:.2f}' if isinstance(correctness_score,(int,float)) else '—'}<span style='font-size:.9rem;color:#93a4bd'> / 100</span></div><div class='ag-kpi-foot'>{correctness_status.title()} · trusted oracle</div></div>",unsafe_allow_html=True)
    quality_score=report.get('quality_score')
    with r3: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Quality / diagnostics</div><div class='ag-kpi-value'>{f'{quality_score:.2f}' if isinstance(quality_score,(int,float)) else '—'}<span style='font-size:.9rem;color:#93a4bd'> / 100</span></div><div class='ag-kpi-foot'>Non-correctness metrics only</div></div>",unsafe_allow_html=True)
    with r4: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>First-pass smoke</div><div class='ag-kpi-value'>{report.get('first_pass',{}).get('smoke_status','—').upper()}</div><div class='ag-kpi-foot'>Compile + initial execution</div></div>",unsafe_allow_html=True)
    with r5: st.markdown(f"<div class='ag-card'><div class='ag-kpi-label'>Review flags</div><div class='ag-kpi-value'>{len(report.get('flags',[]))}</div><div class='ag-kpi-foot'>Signals needing human review</div></div>",unsafe_allow_html=True)

    st.caption(f"Configured correctness test cases: {report.get('test_cases_total', '—')}. Correctness uses trusted expected-output comparisons. The separate quality score excludes correctness; sanitizer/fuzz findings remain diagnostic evidence.")

    t_metrics,t_evidence,t_details,t_export=st.tabs(["Metric overview","Test evidence","Flags & limitations","Export reports"])
    metrics=report.get("metrics",{})
    with t_metrics:
        if metrics:
            rows=[]
            for name,m in metrics.items():
                rows.append({"Metric":name.replace("_"," ").title(),"Status":m.get("status"),"Score":m.get("score"),"Weight":m.get("weight"),"Threshold":m.get("threshold"),"Feedback":m.get("feedback")})
            st.dataframe(rows,use_container_width=True,hide_index=True)
        st.caption("Source metrics are heuristic indicators. Review their evidence and limitations rather than treating them as proofs.")
    with t_evidence:
        found=False
        for mname in ("correctness","logical"):
            cases=((metrics.get(mname,{}) or {}).get("evidence") or {}).get("cases",[])
            if cases:
                found=True
                st.markdown(f"### {mname.title()} cases")
                for idx,case in enumerate(cases):
                    passed=case.get("passed") is True or case.get("status")=="pass"
                    label=case.get("name",f"Case {idx+1}")
                    with st.expander(f"{'✓' if passed else '✕'} {label} · {case.get('status','unknown')}",expanded=not passed):
                        x,y=st.columns(2)
                        x.text_area("Input",case.get("input",""),key=f"evidence_in_{mname}_{idx}",disabled=True)
                        y.text_area("Expected",case.get("expected_output",""),key=f"evidence_ex_{mname}_{idx}",disabled=True)
                        st.text_area("Actual output",case.get("actual_output",""),key=f"evidence_actual_{mname}_{idx}",disabled=True)
                        if case.get("feedback"): st.caption(case["feedback"])
        if not found: st.info("No case-level evidence was returned by the configured analyzers.")
    with t_details:
        flags=report.get("flags",[])
        if flags:
            for flag in flags: st.warning(f"{flag.get('type','Review flag')}: {flag.get('note',flag.get('evidence','Review manually.'))}")
        else: st.success("No report flags were emitted.")
        with st.expander("Usefulness and limitations from project report"):
            for u in report.get("usefulness_limitations",{}).get("usefulness",[]): st.markdown(f"**{u.get('use_case')}** — {u.get('example')}  \n{u.get('benefit')}")
            st.markdown("---")
            for lim in report.get("usefulness_limitations",{}).get("limitations",[]): st.markdown(f"**{lim.get('limitation')}** — {lim.get('example')}")
    with t_export:
        j,t=st.columns(2)
        j.download_button("Download JSON report",data=st.session_state.report_json,file_name="grade-report.json",mime="application/json",use_container_width=True)
        t.download_button("Download readable report",data=st.session_state.report_txt,file_name="grade-report.txt",mime="text/plain",use_container_width=True)
        st.caption("Reports include source/rubric hashes, score details, tool metadata, test evidence, and review flags.")

st.markdown("<div class='small-note' style='text-align:center;padding:1.2rem 0'>AUTOGRADER · Reproducible assessment workspace · DAA Lab</div>",unsafe_allow_html=True)



# Batch assessment: apply the same trusted suite and rubric to multiple submissions.
st.markdown("## Batch grading")
st.caption("Upload multiple C files to grade them independently. Optional pairwise similarity checks compare each submission against the others and produce review flags, not plagiarism verdicts.")
batch_files = st.file_uploader("Upload student C files", type=["c"], accept_multiple_files=True, key="batch_sources")
batch_originality = st.checkbox("Compare submissions against one another for similarity review", value=True)
batch_ready = bool(batch_files) and test_cases_valid and rules_valid
if st.button("Grade all submissions", type="primary", disabled=not batch_ready, use_container_width=True, key="run_batch"):
    batch_rows, batch_reports = [], {}
    with st.status(f"Grading {len(batch_files)} submissions…", expanded=True) as batch_status:
        with tempfile.TemporaryDirectory(prefix="autograder_batch_") as td:
            base = Path(td)
            source_paths = {}
            for i, uploaded in enumerate(batch_files):
                dest = base / f"{i:04d}_{Path(uploaded.name).name}"
                dest.write_bytes(uploaded.getvalue())
                source_paths[uploaded.name] = dest
            testp, rulep = base / "test_cases.json", base / "rules.json"
            testp.write_text(json.dumps(test_cases, indent=2), encoding="utf-8")
            rulep.write_text(json.dumps(rules_obj, indent=2), encoding="utf-8")
            for idx, uploaded in enumerate(batch_files, start=1):
                refs_for_this = ([str(p) for name, p in source_paths.items() if name != uploaded.name]
                                 if batch_originality else [])
                out_dir = base / "reports" / f"{idx:04d}_{Path(uploaded.name).stem}"
                try:
                    rep = evaluate_submission(str(source_paths[uploaded.name]), str(testp), str(rulep),
                                              str(out_dir), timeout=float(timeout),
                                              references=refs_for_this, memory_limit_mb=int(memory_mb))
                    rep_bytes = {kind: Path(path).read_bytes() for kind, path in rep.get("report_paths", {}).items()
                                 if path and Path(path).is_file()}
                    batch_reports[uploaded.name] = rep_bytes
                    batch_rows.append({
                        "submission": uploaded.name, "overall_score": rep.get("overall_score"),
                        "correctness_score": (rep.get("metrics", {}).get("correctness", {}) or {}).get("score"),
                        "quality_score": rep.get("quality_score"), "grade_status": rep.get("grade_status"),
                        "review_flags": len(rep.get("flags", []))
                    })
                except Exception as exc:
                    batch_rows.append({"submission": uploaded.name, "overall_score": None,
                                       "correctness_score": None, "quality_score": None,
                                       "grade_status": "error", "review_flags": 0, "error": str(exc)})
                st.write(f"{idx}/{len(batch_files)} · {uploaded.name}")
        st.session_state["batch_rows"] = batch_rows
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, files in batch_reports.items():
                for kind, payload in files.items():
                    archive.writestr(f"{Path(name).stem}/{kind}_report", payload)
        st.session_state["batch_zip"] = buf.getvalue()
        csv_buf = io.StringIO()
        fields = ["submission", "overall_score", "correctness_score", "quality_score", "grade_status", "review_flags"]
        writer = csv.DictWriter(csv_buf, fieldnames=fields)
        writer.writeheader()
        for row in batch_rows:
            writer.writerow({key: row.get(key) for key in fields})
        st.session_state["batch_csv_bytes"] = csv_buf.getvalue().encode("utf-8")
        batch_status.update(label="Batch assessment complete", state="complete")

if "batch_rows" in st.session_state:
    st.dataframe(st.session_state["batch_rows"], use_container_width=True, hide_index=True)
    ba, bb = st.columns(2)
    ba.download_button("Download batch summary (CSV)", st.session_state["batch_csv_bytes"],
                       "batch-summary.csv", "text/csv", use_container_width=True)
    bb.download_button("Download individual reports (ZIP)", st.session_state["batch_zip"],
                       "batch-reports.zip", "application/zip", use_container_width=True)
