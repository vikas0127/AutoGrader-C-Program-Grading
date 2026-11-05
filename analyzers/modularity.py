import re
from pathlib import Path
from analyzers.interface import AnalyzerResult

# Approximate C function-definition recognizer; excludes common control keywords.
CONTROL={"if","for","while","switch","sizeof"}
PATTERN=re.compile(r"(?:^|[;{}])\s*(?:[A-Za-z_]\w*\s+|\*\s*)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{",re.M)

def analyze_modularity(source,params=None):
    p=Path(source)
    if not p.is_file(): return AnalyzerResult("modularity","error",None,feedback="Source not found.",error="source_missing")
    params=params or {}; text=p.read_text(encoding="utf-8",errors="replace")
    text=re.sub(r"/\*.*?\*/|//[^\n]*", " ",text,flags=re.S)
    funcs=[n for n in PATTERN.findall(text) if n not in CONTROL]
    min_functions=int(params.get("min_functions",2)); expect=bool(params.get("expect_helpers",True))
    count=len(set(funcs)); score=min(100,round(100*count/max(1,min_functions)))
    if expect and count<min_functions: score=min(score,50)
    return AnalyzerResult("modularity","ok",score,evidence={"functions_detected":sorted(set(funcs)),"function_count":count,"minimum_expected":min_functions},
      feedback=(f"Detected {count} function definition(s)." if count>=min_functions else "Few helper functions detected; consider separating logic into reusable functions."))
