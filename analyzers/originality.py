from analyzers.interface import AnalyzerResult
from analyzers.similarity import analyze_similarity


def analyze_originality(source,references=None,params=None):
    params=params or {}; threshold=float(params.get("flag_threshold",0.85))*100
    result=analyze_similarity(source,references or [])
    if result.status!="ok":
        result.name="originality"
        return result
    evidence=result.evidence or {}; best=float(evidence.get("best_similarity_percent",0))
    evidence["flag_threshold_percent"]=threshold; evidence["suspected_copying_flag"]=best>=threshold
    evidence["interpretation"]="Similarity flag is a review lead; it does not establish plagiarism or LLM use."
    # Higher similarity means higher suspicion and therefore lower originality score.
    return AnalyzerResult("originality","ok",round(100-best,2),evidence=evidence,
      feedback=(f"Flagged for human review: similarity {best:.2f}% meets threshold {threshold:.2f}%." if best>=threshold else f"No similarity flag: best match {best:.2f}% below threshold."))
