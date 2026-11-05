
import re
from pathlib import Path
from collections import Counter
from difflib import SequenceMatcher

from analyzers.interface import AnalyzerResult


C_KEYWORDS = set("""
auto break case char const continue default do double else enum extern float for goto if
inline int long register restrict return short signed sizeof static struct switch typedef
union unsigned void volatile while _Alignas _Alignof _Atomic _Bool _Complex _Generic
_Imaginary _Noreturn _Static_assert _Thread_local
""".split())
STABLE_IDENTIFIERS = set("""
main printf fprintf sprintf snprintf scanf fscanf sscanf getchar putchar puts
fopen fclose fread fwrite malloc calloc realloc free exit abort strlen strcmp strcpy
memcpy memset sqrt pow sin cos tan abs labs rand srand time
""".split())


def tokens(source_code):
    """Strip comments and normalize user identifiers/literals for similarity."""
    source_code = re.sub(r'/\*.*?\*/|//[^\n]*', ' ', source_code, flags=re.S)
    raw = re.findall(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)|[^\s]', source_code)
    identifiers = {}
    normalized = []
    for token in raw:
        if token.startswith('"'):
            normalized.append("<STRING>")
        elif token.startswith("'"):
            normalized.append("<CHAR>")
        elif re.fullmatch(r'(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)', token):
            normalized.append("<NUMBER>")
        elif re.fullmatch(r'[A-Za-z_]\w*', token) and token not in C_KEYWORDS | STABLE_IDENTIFIERS:
            if token not in identifiers:
                identifiers[token] = f"<ID{len(identifiers)}>"
            normalized.append(identifiers[token])
        else:
            normalized.append(token)
    return normalized


def analyze_similarity(source, references=None):
    source_path = Path(source)

    if not source_path.is_file():
        return AnalyzerResult(
            'similarity',
            'error',
            None,
            feedback='Source not found.'
        )

    if not references:
        return AnalyzerResult(
            'similarity',
            'skipped',
            None,
            evidence=[],
            feedback='No reference submissions supplied.'
        )

    source_tokens = tokens(source_path.read_text(errors='replace'))
    source_counts = Counter(zip(source_tokens, source_tokens[1:]))
    comparisons = []

    for reference in references:
        reference_path = Path(reference)

        if not reference_path.is_file():
            comparisons.append({
                'reference': reference_path.name,
                'status': 'missing'
            })
            continue

        reference_tokens = tokens(
            reference_path.read_text(errors='replace')
        )
        reference_counts = Counter(
            zip(reference_tokens, reference_tokens[1:])
        )

        source_total = sum(source_counts.values())
        reference_total = sum(reference_counts.values())

        if source_total == 0 or reference_total == 0:
            token_pair_similarity = 0.0
        else:
            shared = sum((source_counts & reference_counts).values())
            token_pair_similarity = 200.0 * shared / (source_total + reference_total)

        # Sequence similarity adds an order-sensitive signal. Both scores are
        # normalized tokens; neither is a plagiarism verdict.
        sequence_similarity = 100.0 * SequenceMatcher(
            None, source_tokens, reference_tokens, autojunk=False
        ).ratio()
        similarity = round(0.6 * token_pair_similarity + 0.4 * sequence_similarity, 2)

        comparisons.append({
            'reference': reference_path.name,
            'status': 'compared',
            'similarity_percent': similarity,
            'token_pair_similarity_percent': round(token_pair_similarity, 2),
            'sequence_similarity_percent': round(sequence_similarity, 2),
            'matched_token_pairs': int(sum((source_counts & reference_counts).values())),
            'source_token_pairs': int(source_total),
            'reference_token_pairs': int(reference_total)
        })

    valid_scores = [
        item['similarity_percent']
        for item in comparisons
        if item.get('status') == 'compared'
    ]

    if not valid_scores:
        return AnalyzerResult(
            'similarity',
            'skipped',
            None,
            evidence={'comparisons': comparisons},
            feedback='No valid reference submissions could be compared.'
        )

    best_similarity = max(valid_scores)

    # Higher similarity means greater concern, so lower the metric score.
    score = round(100.0 - best_similarity, 2)

    return AnalyzerResult(
        'similarity',
        'ok',
        score,
        evidence={
            'comparisons': comparisons,
            'best_similarity_percent': best_similarity,
            'method': '0.6 * normalized token-pair Dice + 0.4 * normalized token sequence similarity',
            'human_review_required': True
        },
        feedback=(
            'Token-pair similarity heuristic only. '
            'High similarity requires human review and does not prove copying.'
        )
    )
