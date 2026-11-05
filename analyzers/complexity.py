import re
from pathlib import Path
from analyzers.interface import AnalyzerResult


def analyze_complexity(source,params=None):
    p=Path(source)
    if not p.is_file(): return AnalyzerResult("complexity","error",None,feedback="Source not found.",error="source_missing")
    params=params or {}; text=p.read_text(encoding="utf-8",errors="replace")
    text=re.sub(r'/\*.*?\*/|//[^\n]*',' ',text,flags=re.S)
    loops=len(re.findall(r'\b(for|while|do)\b',text)); decisions=len(re.findall(r'\b(if|switch|case)\b|&&|\|\|',text))
    required=params.get("required","O(1)")
    # Transparent structural heuristic: loop-free code is consistent with O(1),
    # one simple loop with O(n), nested loops with O(n^2) or worse.
    if loops==0: estimate="O(1)"
    elif loops==1: estimate="O(n)"
    else: estimate="O(n^2) or higher"
    score=100 if estimate==required else max(0,100-min(80,decisions*4+loops*12))
    return AnalyzerResult("complexity","ok",score,evidence={"loop_tokens":loops,"decision_tokens":decisions,
      "estimated_bound":estimate,"required_bound":required,"sizes":params.get("sizes",[1,10,100])},
      feedback="Static structural estimate only; not a formal complexity proof or reliable timing curve.")
