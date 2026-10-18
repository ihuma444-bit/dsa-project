import math
import time

from sorted import NUMERIC_COLUMNS, Stats, sort_rows

NUMERIC_OPS = ["=", "!=", ">", ">=", "<", "<="]
STRING_OPS = ["contains", "starts with", "ends with", "equals"]

RANGE_OPS_NUMERIC = {"=", ">", ">=", "<", "<="}
RANGE_OPS_STRING = {"equals", "starts with"}

MAX_CHAR = "\U0010ffff"


def operators_for(column):
    return NUMERIC_OPS if column in NUMERIC_COLUMNS else STRING_OPS


def row_id(row):
    return int(row["id"])


def parse_value(column, text):
    """User ki value ko compare karne layak banata hai. Number ghalat ho to ValueError."""
    if column in NUMERIC_COLUMNS:
        return float(text)
    return str(text).strip().lower()


def cell(row, column):
    """Row ki value (number ya lowercase string). Blank ho to None."""
    v = row[column]
    if v == "" or v is None:
        return None
    return float(v) if column in NUMERIC_COLUMNS else str(v).lower()


def matches(cv, op, t):
    if cv is None:                 # blank value kisi condition se match nahi karti
        return False
    if op in ("=", "equals"):
        return cv == t
    if op == "!=":
        return cv != t
    if op == ">":
        return cv > t
    if op == ">=":
        return cv >= t
    if op == "<":
        return cv < t
    if op == "<=":
        return cv <= t
    if op == "contains":
        return t in cv
    if op == "starts with":
        return cv.startswith(t)
    if op == "ends with":
        return cv.endswith(t)
    raise ValueError(f"Unknown operator: {op}")


# ------------------------------------------------------------------
# Boundary searches. Sorted `keys` mein pehla index dhoondte hain jahan
#   key >= t   (inclusive=False)   ya   key > t   (inclusive=True)
# ------------------------------------------------------------------
def _before(k, t, inclusive):
    return k <= t if inclusive else k < t


def binary_boundary(keys, t, inclusive, st):
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        st.comparisons += 1
        if _before(keys[mid], t, inclusive):
            lo = mid + 1
        else:
            hi = mid
    return lo


def jump_boundary(keys, t, inclusive, st):
    n = len(keys)
    step = max(1, int(math.sqrt(n)))
    prev = 0
    while prev < n:                       # block ke aakhri element se jump
        last = min(prev + step, n)
        st.comparisons += 1
        if _before(keys[last - 1], t, inclusive):
            prev = last
        else:
            break
    end = min(prev + step, n)
    i = prev
    while i < end:                        # block ke andar linear
        st.comparisons += 1
        if not _before(keys[i], t, inclusive):
            break
        i += 1
    return i


def interpolation_boundary(keys, t, inclusive, st):
    lo, hi = 0, len(keys)
    while lo < hi:
        a, b = keys[lo], keys[hi - 1]
        if b == a:
            pos = lo
        else:
            pos = lo + int((t - a) * (hi - 1 - lo) / (b - a))
            pos = max(lo, min(hi - 1, pos))
        st.comparisons += 1
        if _before(keys[pos], t, inclusive):
            lo = pos + 1
        else:
            hi = pos
    return lo


# name -> (boundary function or None, complexity, needs sorted data)
ALGORITHMS = {
    "Linear Search":        (None,                  "O(n)",                False),
    "Binary Search":        (binary_boundary,       "O(log n)",            True),
    "Jump Search":          (jump_boundary,         "O(√n)",               True),
    "Interpolation Search": (interpolation_boundary, "O(log log n) avg",   True),
}


def algorithm_label(name):
    _, complexity, needs_sorted = ALGORITHMS[name]
    extra = "sorted data chahiye" if needs_sorted else "kisi bhi data pe"
    if name == "Interpolation Search":
        extra = "sorted number column"
    return f"{name}  |  {complexity}  |  {extra}"


def can_use_range(column, op, algo):
    if ALGORITHMS[algo][0] is None:
        return False
    if algo == "Interpolation Search" and column not in NUMERIC_COLUMNS:
        return False
    ops = RANGE_OPS_NUMERIC if column in NUMERIC_COLUMNS else RANGE_OPS_STRING
    return op in ops


# ------------------------------------------------------------------
# Ek condition chalana
# ------------------------------------------------------------------
def _linear(rows, column, op, t, st):
    hits = set()
    for r in rows:
        st.comparisons += 1
        if matches(cell(r, column), op, t):
            hits.add(row_id(r))
    return hits


def _range_search(rows, column, op, t, algo, st):
    boundary = ALGORITHMS[algo][0]
    # 1) column ko sort karo (blank values end mein jati hain)
    sorted_rows, prep_ms, _, _ = sort_rows(rows, [column], "Merge Sort")
    keys, kept = [], []
    for r in sorted_rows:
        cv = cell(r, column)
        if cv is None:
            break
        keys.append(cv)
        kept.append(r)
    m = len(keys)

    # 2) search sirf is hisse ko ginta hai
    t0 = time.perf_counter()
    if op in ("=", "equals"):
        lo, hi = boundary(keys, t, False, st), boundary(keys, t, True, st)
    elif op == ">":
        lo, hi = boundary(keys, t, True, st), m
    elif op == ">=":
        lo, hi = boundary(keys, t, False, st), m
    elif op == "<":
        lo, hi = 0, boundary(keys, t, False, st)
    elif op == "<=":
        lo, hi = 0, boundary(keys, t, True, st)
    else:                                     # starts with
        lo = boundary(keys, t, False, st)
        hi = boundary(keys, t + MAX_CHAR, False, st)
    ms = (time.perf_counter() - t0) * 1000
    return {row_id(r) for r in kept[lo:hi]}, ms, prep_ms


def run_condition(rows, column, op, value, algo):
    """
    Returns (set of matching ids, info dict).
    info: text, algo_used, note, count, comparisons, ms, prep_ms
    """
    t = parse_value(column, value)
    st = Stats()
    note = ""
    prep_ms = 0.0
    if can_use_range(column, op, algo):
        ids, ms, prep_ms = _range_search(rows, column, op, t, algo, st)
        used = algo
    else:
        if algo != "Linear Search":
            if algo == "Interpolation Search" and column not in NUMERIC_COLUMNS:
                note = f"{algo} sirf number column pe chalta hai, Linear use hua"
            else:
                note = f"{algo} '{op}' pe nahi chalta, Linear use hua"
        t0 = time.perf_counter()
        ids = _linear(rows, column, op, t, st)
        ms = (time.perf_counter() - t0) * 1000
        used = "Linear Search"
    info = {
        "text": f'{column} {op} "{value}"',
        "algo_used": used,
        "note": note,
        "count": len(ids),
        "comparisons": st.comparisons,
        "ms": ms,
        "prep_ms": prep_ms,
    }
    return ids, info


def condition_text(c, first):
    conn = "" if first else c["connector"] + " "
    neg = "NOT " if c["negate"] else ""
    return f'{conn}{neg}{c["column"]} {c["op"]} "{c["value"]}"   [{c["algo"]}]'


def evaluate(rows, conditions):
    """
    conditions: list of dict(column, op, value, algo, connector, negate).
    Left-to-right evaluation. Returns (matched_rows, details list).
    matched_rows `rows` ki current tarteeb mein hoti hain.
    """
    all_ids = {row_id(r) for r in rows}
    result = None
    details = []
    for c in conditions:
        ids, info = run_condition(rows, c["column"], c["op"], c["value"], c["algo"])
        if c["negate"]:
            ids = all_ids - ids
            info["text"] = "NOT " + info["text"]
        if result is None:
            result = ids
        elif c["connector"] == "OR":
            result = result | ids
        else:
            result = result & ids
        details.append(info)
    result = result or set()
    matched = [r for r in rows if row_id(r) in result]
    return matched, details