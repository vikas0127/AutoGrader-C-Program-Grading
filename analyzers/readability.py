"""Deterministic readability proxy; optional LLM review can be added as a provider."""
import re
from pathlib import Path
from analyzers.interface import AnalyzerResult


def analyze_readability(source,params=None):
    p=Path(source)
    if not p.is_file(): return AnalyzerResult("readability","error",None,feedback="Source not found.",error="source_missing")
    text=p.read_text(encoding="utf-8",errors="replace"); params=params or {}
    lines=text.splitlines(); nonblank=[x for x in lines if x.strip()]
    comments=len(re.findall(r"/\*.*?\*/|//[^\n]*",text,flags=re.S)); funcs=len(re.findall(r"\b[A-Za-z_]\w*\s*\([^;]*\)\s*\{",text))
    long_lines=sum(len(x)>params.get("max_line_length",100) for x in lines)
    whitespace_penalty=sum(1 for x in nonblank if x.strip() and not x.startswith(("#","//","/*","*")) and "=" in x and not re.search(r"\s=\s",x))
    score=max(0,min(100,100-min(40,long_lines*2)-min(25,whitespace_penalty*2)- (15 if comments==0 else 0) - (10 if len(nonblank)>80 and funcs<2 else 0)))
    return AnalyzerResult("readability","ok",score,evidence={"line_count":len(lines),"comment_blocks":comments,"function_like_definitions":funcs,"long_lines":long_lines,"compact_assignment_lines":whitespace_penalty,"method":"deterministic source heuristics"},
      feedback="Readability score is a deterministic heuristic, not an LLM judgment or proof of code quality.")
