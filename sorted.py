import time

NUMERIC_COLUMNS = {"id", "episodes", "score", "popularity", "favourites", "year"}


class Stats:
    def __init__(self):
        self.comparisons = 0
        self.swaps = 0


def less(x, y, st):
    st.comparisons += 1
    return x < y


# ---------------------------------------------------------------- bubble
def bubble_sort(a, st):
    n = len(a)
    for i in range(n - 1):
        swapped = False
        for j in range(n - 1 - i):
            if less(a[j + 1][0], a[j][0], st):
                a[j], a[j + 1] = a[j + 1], a[j]
                st.swaps += 1
                swapped = True
        if not swapped:
            break


# ---------------------------------------------------------------- selection
def selection_sort(a, st):
    n = len(a)
    for i in range(n - 1):
        m = i
        for j in range(i + 1, n):
            if less(a[j][0], a[m][0], st):
                m = j
        if m != i:
            a[i], a[m] = a[m], a[i]
            st.swaps += 1


# ---------------------------------------------------------------- insertion
def insertion_range(a, lo, hi, st):
    """a[lo:hi] ko insertion sort se sort karta hai (hybrid sort bhi isse use karta hai)."""
    for i in range(lo + 1, hi):
        cur = a[i]
        j = i - 1
        while j >= lo and less(cur[0], a[j][0], st):
            a[j + 1] = a[j]
            st.swaps += 1
            j -= 1
        a[j + 1] = cur


def insertion_sort(a, st):
    insertion_range(a, 0, len(a), st)


# ---------------------------------------------------------------- merge
def _merge(src, dst, lo, mid, hi, st):
    i, j, k = lo, mid, lo
    while i < mid and j < hi:
        st.comparisons += 1
        if src[j][0] < src[i][0]:      # strict: barabar items mein left pehle (stable)
            dst[k] = src[j]
            j += 1
        else:
            dst[k] = src[i]
            i += 1
        st.swaps += 1
        k += 1
    while i < mid:
        dst[k] = src[i]
        i += 1
        k += 1
        st.swaps += 1
    while j < hi:
        dst[k] = src[j]
        j += 1
        k += 1
        st.swaps += 1


def _bottom_up_merge(a, st, width):
    n = len(a)
    src, dst = a, [None] * n
    while width < n:
        for lo in range(0, n, 2 * width):
            mid = min(lo + width, n)
            hi = min(lo + 2 * width, n)
            _merge(src, dst, lo, mid, hi, st)
        src, dst = dst, src
        width *= 2
    if src is not a:
        a[:] = src


def merge_sort(a, st):
    _bottom_up_merge(a, st, 1)


# ---------------------------------------------------------------- hybrid
HYBRID_RUN = 32


def hybrid_sort(a, st):
    """Merge sort + insertion sort: chhote blocks (32) insertion se, phir merge."""
    n = len(a)
    for lo in range(0, n, HYBRID_RUN):
        insertion_range(a, lo, min(lo + HYBRID_RUN, n), st)
    _bottom_up_merge(a, st, HYBRID_RUN)


# ---------------------------------------------------------------- quick
def quick_sort(a, st):
    """Hoare partition, middle pivot, iterative (zyada duplicates mein bhi theek)."""
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        if lo >= hi:
            continue
        pivot = a[(lo + hi) // 2][0]
        i, j = lo - 1, hi + 1
        while True:
            i += 1
            while less(a[i][0], pivot, st):
                i += 1
            j -= 1
            while less(pivot, a[j][0], st):
                j -= 1
            if i >= j:
                break
            a[i], a[j] = a[j], a[i]
            st.swaps += 1
        stack.append((lo, j))
        stack.append((j + 1, hi))


# ---------------------------------------------------------------- heap (extra)
def _sift_down(a, start, end, st):
    root = start
    while True:
        child = 2 * root + 1
        if child > end:
            return
        if child + 1 <= end and less(a[child][0], a[child + 1][0], st):
            child += 1
        if less(a[root][0], a[child][0], st):
            a[root], a[child] = a[child], a[root]
            st.swaps += 1
            root = child
        else:
            return


def heap_sort(a, st):
    n = len(a)
    for start in range(n // 2 - 1, -1, -1):
        _sift_down(a, start, n - 1, st)
    for end in range(n - 1, 0, -1):
        a[0], a[end] = a[end], a[0]
        st.swaps += 1
        _sift_down(a, 0, end - 1, st)


# ---------------------------------------------------------------- shell (extra)
def shell_sort(a, st):
    n = len(a)
    gap = 1
    while gap < n // 3:
        gap = 3 * gap + 1              # Knuth gaps: 1, 4, 13, 40, ...
    while gap >= 1:
        for i in range(gap, n):
            cur = a[i]
            j = i
            while j >= gap and less(cur[0], a[j - gap][0], st):
                a[j] = a[j - gap]
                st.swaps += 1
                j -= gap
            a[j] = cur
        gap //= 3


# name -> (function, time complexity, stable?)
ALGORITHMS = {
    "Bubble Sort":    (bubble_sort,    "O(n²)",       True),
    "Selection Sort": (selection_sort, "O(n²)",       False),
    "Insertion Sort": (insertion_sort, "O(n²)",       True),
    "Merge Sort":     (merge_sort,     "O(n log n)",  True),
    "Quick Sort":     (quick_sort,     "O(n log n)*", False),   # *worst case O(n²)
    "Hybrid Sort":    (hybrid_sort,    "O(n log n)",  True),
    "Heap Sort":      (heap_sort,      "O(n log n)",  False),
    "Shell Sort":     (shell_sort,     "O(n^1.5)",    False),
}


def algorithm_label(name):
    _, complexity, stable = ALGORITHMS[name]
    return f"{name}  |  {complexity}  |  {'Stable' if stable else 'Not stable'}"


# ---------------------------------------------------------------- keys + runner
def key_for(row, column):
    """Blank values hamesha end mein jati hain."""
    v = row[column]
    if v == "" or v is None:
        return (1, 0) if column in NUMERIC_COLUMNS else (1, "")
    if column in NUMERIC_COLUMNS:
        return (0, float(v))
    return (0, str(v).lower())


def sort_rows(rows, columns, algo_name, descending=False):
    """
    rows: list of dict, columns: list of column names (pehla = main, baqi = tie-break).
    Returns (sorted_rows, time_ms, comparisons, swaps). Original `rows` change nahi hoti.
    """
    func = ALGORITHMS[algo_name][0]
    items = [(tuple(key_for(r, c) for c in columns), r) for r in rows]
    st = Stats()
    t0 = time.perf_counter()
    func(items, st)
    ms = (time.perf_counter() - t0) * 1000
    result = [r for _, r in items]
    if descending:
        # blank values descending mein bhi end mein rahein
        filled = [r for k, r in items if k[0][0] == 0]
        empty = [r for k, r in items if k[0][0] == 1]
        filled.reverse()
        result = filled + empty
    return result, ms, st.comparisons, st.swaps


def benchmark(rows, columns, descending=False):
    """Saare algorithms chalata hai. Returns list of (name, ms, comparisons, swaps, complexity, stable)."""
    out = []
    for name, (_, complexity, stable) in ALGORITHMS.items():
        _, ms, comps, swaps = sort_rows(rows, columns, name, descending)
        out.append((name, ms, comps, swaps, complexity, stable))
    return out