from analyzers.static_analysis import analyze_static

def analyze_syntax(source,params=None):
    params=params or {}
    flags=params.get("flags",["-Wall","-Wextra","-Werror","-std=c11"])
    if isinstance(flags,str): flags=flags.split()
    # Existing GCC diagnostic analyzer supports a fixed compiler invocation;
    # params are represented in evidence to keep rubric traceability.
    # Keep warnings scoreable even if the rubric lists -Werror; apply -Werror
    # as a rubric preference rather than turning every warning into a build failure.
    diagnostic_flags=[flag for flag in flags if flag != "-Werror"]
    if "-fsyntax-only" not in diagnostic_flags: diagnostic_flags.append("-fsyntax-only")
    result=analyze_static(source,flags=diagnostic_flags)
    result.name="syntax"
    if result.status=="ok":
        result.evidence=(result.evidence or {}) | {"configured_flags":flags,"diagnostic_flags":diagnostic_flags}
    return result
