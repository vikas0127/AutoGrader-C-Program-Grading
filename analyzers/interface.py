from dataclasses import dataclass, asdict
from typing import Any, Optional
import math

@dataclass
class AnalyzerResult:
    name: str
    status: str
    score: Optional[float]
    max_score: float = 100.0
    evidence: Any = None
    feedback: str = ""
    error: Optional[str] = None
    def to_dict(self):
        return asdict(self)

def validate_result(r):
    if r.status not in {"ok", "error", "skipped"}: raise ValueError(f"Invalid status: {r.status}")
    if r.max_score <= 0: raise ValueError("max_score must be positive")
    if r.status == "ok":
        if r.score is None or not math.isfinite(r.score) or not 0 <= r.score <= r.max_score:
            raise ValueError("Successful results need a valid score")
    elif r.score is not None: raise ValueError("Error/skipped results must have no score")
