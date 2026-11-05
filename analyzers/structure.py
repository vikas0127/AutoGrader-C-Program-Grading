import re
from pathlib import Path
from analyzers.interface import AnalyzerResult


def analyze_structure(source,params=None):
    p=Path(source)
    if not p.is_file(): return AnalyzerResult("structure","error",None,feedback="Source not found.",error="source_missing")
    params=params or {}; text=p.read_text(encoding="utf-8",errors="replace")
    clean=re.sub(r"/\*.*?\*/|//[^\n]*", " ",text,flags=re.S)
    # Simple lexical metrics; document their limitations in evidence.
    decisions=len(re.findall(r"\b(if|for|while|case)\b|&&|\|\|",clean)); max_cycl=int(params.get("max_cyclomatic",8))
    function_chunks=re.split(r"\b[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{",clean)
    longest=max((len(chunk.splitlines()) for chunk in function_chunks),default=0); max_len=int(params.get("max_function_length",40))
    has_header=bool(re.search(r"^\s*#\s*include",text,re.M))
    penalty=max(0,decisions-max_cycl)*5+max(0,longest-max_len)
    score=max(0,100-min(100,penalty))
    return AnalyzerResult("structure","ok",score,evidence={"decision_tokens":decisions,"max_cyclomatic_threshold":max_cycl,
      "longest_lexical_chunk_lines":longest,"max_function_length_threshold":max_len,"has_include_directive":has_header},
      feedback="Source structure metrics are lexical approximations; they do not replace a full C parser.")
