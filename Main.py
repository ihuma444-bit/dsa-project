import sys, csv, os, time, threading
import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QProgressBar, QLabel, QTableWidget, QTableWidgetItem,
    QComboBox, QGroupBox, QDialog,
)
from sorted import ALGORITHMS, NUMERIC_COLUMNS, algorithm_label, sort_rows

FIELDS = ["id", "title", "type", "episodes", "status", "score",
          "popularity", "favourites", "year", "studio", "genre"]
TARGET = 15000
PER_PAGE = 50
CSV_FILE = "anime.csv"
URL = "https://graphql.anilist.co"

FORMATS = ["TV", "MOVIE", "OVA", "ONA", "SPECIAL", "TV_SHORT", "MUSIC"]

QUERY = """
query ($page: Int, $perPage: Int, $format: MediaFormat) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(type: ANIME, format: $format, sort: ID) {
      id
      title { romaji }
      format
      episodes
      status
      averageScore
      popularity
      favourites
      seasonYear
      studios(isMain: true) { nodes { name } }
      genres
    }
  }
}
"""



STYLE = """
QWidget { background: #14151c; color: #e6e6ef; font-family: "Segoe UI"; font-size: 13px; }
QLabel { background: transparent; }
QLabel#title { font-size: 22px; font-weight: bold; color: #ffffff; }
QLabel#subtitle { color: #8c8fa6; }
QLabel#status { color: #a99cff; }
QGroupBox { background: transparent; border: 1px solid #2a2c3a; border-radius: 10px;
            margin-top: 12px; padding: 14px 10px 10px 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #a99cff;
                   font-weight: bold; }
QPushButton { background: #262838; border: 1px solid #34374a; border-radius: 6px;
              padding: 7px 16px; }
QPushButton:hover { background: #303349; }
QPushButton:pressed { background: #3a3d57; }
QPushButton:disabled { background: #1b1c27; color: #5c5f73; border: 1px solid #25273a; }
QPushButton#primary { background: #7c5cff; border: none; color: #ffffff; font-weight: bold; }
QPushButton#primary:hover { background: #8f73ff; }
QPushButton#primary:disabled { background: #2b2748; color: #6d6a8c; }
QPushButton#danger { background: #3a2230; border: 1px solid #5a2f44; color: #ff8fa0; }
QPushButton#danger:hover { background: #4b2a3c; }
QPushButton#danger:disabled { background: #1b1c27; color: #5c5f73; border: 1px solid #25273a; }
QComboBox { background: #1d1f2b; border: 1px solid #34374a; border-radius: 6px; padding: 5px 10px; }
QComboBox:hover { border: 1px solid #7c5cff; }
QComboBox:disabled { color: #5c5f73; }
QComboBox QAbstractItemView { background: #1d1f2b; border: 1px solid #34374a;
                              selection-background-color: #7c5cff; selection-color: white; }
QProgressBar { background: #1d1f2b; border: none; border-radius: 8px; height: 18px;
               text-align: center; color: #ffffff; }
QProgressBar::chunk { background: #7c5cff; border-radius: 8px; }
QTableWidget { background: #171925; alternate-background-color: #1b1d2b; border: 1px solid #2a2c3a;
               border-radius: 8px; gridline-color: transparent;
               selection-background-color: #3b3470; selection-color: #ffffff; }
QTableWidget::item { padding: 4px 8px; }
QHeaderView::section { background: #20223a; color: #c9c5ff; padding: 9px 8px; border: none;
                       border-bottom: 2px solid #7c5cff; font-weight: bold; }
QScrollBar:vertical { background: #14151c; width: 12px; margin: 0; }
QScrollBar:horizontal { background: #14151c; height: 12px; margin: 0; }
QScrollBar::handle { background: #34374a; border-radius: 5px; min-height: 30px; min-width: 30px; }
QScrollBar::handle:hover { background: #4a4e6b; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
"""

COL_WIDTHS = {"id": 70, "title": 300, "type": 90, "episodes": 90, "status": 120, "score": 70,
              "popularity": 110, "favourites": 110, "year": 70, "studio": 180, "genre": 130}


def make_item(field, value):
    item = QTableWidgetItem(str(value))
    if field in NUMERIC_COLUMNS:
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def blank(v):
    return "" if v is None else v


def parse(a):
    studios = a["studios"]["nodes"]
    return {
        "id": a["id"],
        "title": a["title"]["romaji"] or "",
        "type": blank(a["format"]),
        "episodes": blank(a["episodes"]),
        "status": blank(a["status"]),
        "score": blank(a["averageScore"]),
        "popularity": blank(a["popularity"]),
        "favourites": blank(a["favourites"]),
        "year": blank(a["seasonYear"]),
        "studio": studios[0]["name"] if studios else "",
        "genre": a["genres"][0] if a["genres"] else "",
    }


# =====================================================================
#  Scraper thread
# =====================================================================
class ScraperThread(QThread):
    page_done = pyqtSignal(list)   # new rows of one page
    status = pyqtSignal(str)

    def __init__(self, seen_ids, already):
        super().__init__()
        self.seen = seen_ids           # pehle se mojood ids (duplicate se bachne ke liye)
        self.count = already
        self.error = ""
        self._running = True
        self._resume = threading.Event()
        self._resume.set()

    def pause(self):
        self._resume.clear()

    def resume(self):
        self._resume.set()

    def stop(self):
        self._running = False
        self._resume.set()

    def run(self):
        # AniList ek query mein sirf 5000 entries deta hai,
        # is liye har format (TV, MOVIE, ...) alag alag scrape karte hain
        for fmt in FORMATS:
            if not self._running or self.count >= TARGET:
                break
            if not self.scrape_format(fmt):
                break

    def scrape_format(self, fmt):
        page = 1
        while self._running and self.count < TARGET:
            self._resume.wait()            # pause hone par yahin ruk jata hai
            if not self._running:
                return False
            try:
                r = requests.post(
                    URL,
                    json={"query": QUERY,
                          "variables": {"page": page, "perPage": PER_PAGE,
                                        "format": fmt}},
                    timeout=20,
                )
            except requests.RequestException:
                self.status.emit("Network error, retrying...")
                time.sleep(3)
                continue
            if r.status_code == 429:       # rate limit
                wait = int(r.headers.get("Retry-After", 30))
                self.status.emit(f"Rate limit, waiting {wait}s...")
                time.sleep(wait)
                continue
            if r.status_code == 400 and "depth" in r.text:
                return True                # is format ki limit khatam, agla format
            if r.status_code != 200:
                self.error = f"Error {r.status_code}: {r.text[:150]}"
                return False
            result = r.json()["data"]["Page"]
            rows = []
            for a in result["media"]:
                row = parse(a)
                if row["id"] not in self.seen:
                    self.seen.add(row["id"])
                    rows.append(row)
            if rows:
                self.count += len(rows)
                self.page_done.emit(rows)
            if not result["pageInfo"]["hasNextPage"]:
                return True
            page += 1
            time.sleep(0.8)
        return True


# =====================================================================
#  Sorting threads (taake window freeze na ho)
# =====================================================================
class SortWorker(QThread):
    done = pyqtSignal(list, float, int, int)   # rows, ms, comparisons, swaps

    def __init__(self, rows, columns, algo, descending):
        super().__init__()
        self.rows, self.columns = rows, columns
        self.algo, self.descending = algo, descending

    def run(self):
        out, ms, comps, swaps = sort_rows(self.rows, self.columns,
                                          self.algo, self.descending)
        self.done.emit(out, ms, comps, swaps)


class BenchWorker(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(tuple)   # (name, ms, comps, swaps, complexity, stable)

    def __init__(self, rows, columns, descending):
        super().__init__()
        self.rows, self.columns, self.descending = rows, columns, descending

    def run(self):
        for name, (_, complexity, stable) in ALGORITHMS.items():
            self.progress.emit(f"Benchmark chal raha hai: {name}...")
            _, ms, comps, swaps = sort_rows(self.rows, self.columns,
                                            name, self.descending)
            self.result.emit((name, ms, comps, swaps, complexity, stable))


class BenchmarkDialog(QDialog):
    HEADERS = ["Algorithm", "Time (ms)", "Comparisons", "Swaps",
               "Complexity", "Stable"]

    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 360)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.note = QLabel("Chal raha hai...")
        lay = QVBoxLayout(self)
        lay.addWidget(self.note)
        lay.addWidget(self.table)
        self.results = []

    def add_result(self, res):
        self.results.append(res)
        name, ms, comps, swaps, complexity, stable = res
        i = self.table.rowCount()
        self.table.insertRow(i)
        vals = [name, f"{ms:.2f}", f"{comps:,}", f"{swaps:,}",
                complexity, "Yes" if stable else "No"]
        for c, v in enumerate(vals):
            self.table.setItem(i, c, QTableWidgetItem(v))

    def finished(self):
        # sabse tez algorithm ko highlight karo
        best = min(range(len(self.results)), key=lambda k: self.results[k][1])
        bold = QFont()
        bold.setBold(True)
        for c in range(len(self.HEADERS)):
            item = self.table.item(best, c)
            item.setFont(bold)
            item.setBackground(QBrush(QColor("#1e6b45")))
        self.note.setText(f"Done. Sabse tez: {self.results[best][0]} "
                          f"({self.results[best][1]:.2f} ms)")


# =====================================================================
#  Main window
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Explorer - CS200 Project 1")
        self.resize(1200, 720)
        self.data = []        # saara data
        self.view = []        # jo table mein abhi dikh raha hai (baad mein filter yahan lagega)
        self.thread = None    # scraper thread
        self.sort_worker = None
        self.bench_worker = None
        self.bench_dialog = None
        self.scraping = False
        self.busy = False     # sorting / benchmark chal raha hai

        # ---------- scraping controls ----------
        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("primary")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("danger")
        self.progress = QProgressBar()
        self.progress.setMaximum(TARGET)
        self.label = QLabel("Ready")
        self.label.setObjectName("status")

        top = QHBoxLayout()
        top.setSpacing(8)
        for w in (self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop):
            top.addWidget(w)
        top.addWidget(self.progress, 1)

        # ---------- sorting panel ----------
        cols = [f.capitalize() for f in FIELDS]
        self.cb_col = QComboBox()
        for f in FIELDS:
            self.cb_col.addItem(f.capitalize(), f)
        self.cb_col2 = QComboBox()
        self.cb_col2.addItem("(none)", None)
        for f in FIELDS:
            self.cb_col2.addItem(f.capitalize(), f)
        self.cb_order = QComboBox()
        self.cb_order.addItems(["Ascending", "Descending"])
        self.cb_algo = QComboBox()
        for name in ALGORITHMS:
            self.cb_algo.addItem(algorithm_label(name), name)
        self.cb_scope = QComboBox()
        self.cb_scope.addItem("Full dataset", "full")
        self.cb_scope.addItem("Filtered results only", "filtered")
        self.btn_sort = QPushButton("Sort")
        self.btn_sort.setObjectName("primary")
        self.btn_bench = QPushButton("Benchmark")
        self.sort_result = QLabel("")
        self.sort_result.setObjectName("status")

        g = QGridLayout()
        g.addWidget(QLabel("Sort by:"), 0, 0)
        g.addWidget(self.cb_col, 0, 1)
        g.addWidget(QLabel("Then by:"), 0, 2)
        g.addWidget(self.cb_col2, 0, 3)
        g.addWidget(QLabel("Order:"), 0, 4)
        g.addWidget(self.cb_order, 0, 5)
        g.addWidget(QLabel("Algorithm:"), 1, 0)
        g.addWidget(self.cb_algo, 1, 1, 1, 3)
        g.addWidget(QLabel("Scope:"), 1, 4)
        g.addWidget(self.cb_scope, 1, 5)
        g.addWidget(self.btn_sort, 2, 0)
        g.addWidget(self.btn_bench, 2, 1)
        g.addWidget(self.sort_result, 2, 2, 1, 4)
        box = QGroupBox("Sorting")
        box.setLayout(g)

        # ---------- table ----------
        self.table = QTableWidget(0, len(FIELDS))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setStretchLastSection(True)
        for c, f in enumerate(FIELDS):
            self.table.setColumnWidth(c, COL_WIDTHS[f])

        title = QLabel("Anime Explorer")
        title.setObjectName("title")
        self.count_label = QLabel("")
        self.count_label.setObjectName("subtitle")
        head = QHBoxLayout()
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count_label)

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        layout.addLayout(head)
        layout.addLayout(top)
        layout.addWidget(self.label)
        layout.addWidget(box)
        layout.addWidget(self.table, 1)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.btn_start.clicked.connect(self.start_scrape)
        self.btn_pause.clicked.connect(self.pause_scrape)
        self.btn_resume.clicked.connect(self.resume_scrape)
        self.btn_stop.clicked.connect(self.stop_scrape)
        self.btn_sort.clicked.connect(self.do_sort)
        self.btn_bench.clicked.connect(self.do_benchmark)

        self.load_csv()
        self.set_buttons(running=False)

    # ---------- button states ----------
    def set_buttons(self, running, paused=False):
        self.scraping = running
        self.btn_start.setEnabled(not running)
        self.btn_pause.setEnabled(running and not paused)
        self.btn_resume.setEnabled(running and paused)
        self.btn_stop.setEnabled(running)
        self.update_sort_controls()

    def update_sort_controls(self):
        # scraping ya sorting ke dauran sorting controls band
        on = not self.scraping and not self.busy
        for w in (self.btn_sort, self.btn_bench, self.cb_col, self.cb_col2,
                  self.cb_order, self.cb_algo, self.cb_scope):
            w.setEnabled(on)
        self.btn_start.setEnabled(not self.scraping and not self.busy)

    # ---------- scraping controls ----------
    def start_scrape(self):
        seen = {int(r["id"]) for r in self.data}   # purane data ko dobara add nahi karna
        self.thread = ScraperThread(seen, len(self.data))
        self.thread.page_done.connect(self.add_rows)
        self.thread.status.connect(self.label.setText)
        self.thread.finished.connect(self.scrape_finished)
        self.thread.start()
        self.label.setText("Scraping...")
        self.set_buttons(running=True)

    def pause_scrape(self):
        self.thread.pause()
        self.label.setText("Paused")
        self.set_buttons(running=True, paused=True)

    def resume_scrape(self):
        self.thread.resume()
        self.label.setText("Scraping...")
        self.set_buttons(running=True)

    def stop_scrape(self):
        self.thread.stop()
        self.label.setText("Stopping...")

    def scrape_finished(self):
        self.save_csv()
        if self.thread.error:
            self.label.setText(self.thread.error)
        else:
            self.label.setText(f"Done. {len(self.data)} anime saved to {CSV_FILE}")
        self.set_buttons(running=False)

    # ---------- data ----------
    def add_rows(self, rows):
        for row in rows:
            self.data.append(row)
            self.view.append(row)
            self.append_table_row(row)
        self.progress.setValue(min(len(self.data), TARGET))
        self.label.setText(f"Scraped {len(self.data)} / {TARGET}")
        self.update_count()

    def append_table_row(self, row):
        i = self.table.rowCount()
        self.table.insertRow(i)
        for c, f in enumerate(FIELDS):
            self.table.setItem(i, c, make_item(f, row[f]))

    def update_count(self):
        self.count_label.setText(
            f"Showing {len(self.view):,} of {len(self.data):,} anime")

    def populate_table(self, rows):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for c, f in enumerate(FIELDS):
                self.table.setItem(i, c, make_item(f, row[f]))
        self.table.setUpdatesEnabled(True)
        self.update_count()

    def save_csv(self):
        if not self.data:
            return
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(self.data)

    def load_csv(self):
        if not os.path.exists(CSV_FILE):
            return
        with open(CSV_FILE, newline="", encoding="utf-8") as f:
            self.data = list(csv.DictReader(f))
        self.view = list(self.data)
        self.populate_table(self.view)
        self.progress.setValue(min(len(self.data), TARGET))
        self.label.setText(f"Loaded {len(self.data)} anime from {CSV_FILE}")

    # ---------- sorting ----------
    def chosen_columns(self):
        cols = [self.cb_col.currentData()]
        second = self.cb_col2.currentData()
        if second and second not in cols:
            cols.append(second)
        return cols

    def rows_for_scope(self):
        return self.data if self.cb_scope.currentData() == "full" else self.view

    def set_busy(self, busy):
        self.busy = busy
        self.update_sort_controls()

    def do_sort(self):
        rows = self.rows_for_scope()
        if not rows:
            self.sort_result.setText("Koi data nahi hai.")
            return
        algo = self.cb_algo.currentData()
        self.sort_result.setText(f"{algo} chal raha hai... ({len(rows)} rows)")
        self.set_busy(True)
        self.sort_worker = SortWorker(rows, self.chosen_columns(), algo,
                                      self.cb_order.currentIndex() == 1)
        self.sort_worker.done.connect(self.sort_done)
        self.sort_worker.start()

    def sort_done(self, rows, ms, comps, swaps):
        if self.cb_scope.currentData() == "full":
            self.data = rows
        self.view = rows
        self.populate_table(rows)
        algo = self.cb_algo.currentData()
        self.sort_result.setText(
            f"{algo}  |  Time: {ms:.2f} ms  |  Comparisons: {comps:,}  |  Swaps: {swaps:,}")
        self.set_busy(False)

    def do_benchmark(self):
        rows = self.rows_for_scope()
        if not rows:
            self.sort_result.setText("Koi data nahi hai.")
            return
        cols = self.chosen_columns()
        self.set_busy(True)
        self.bench_dialog = BenchmarkDialog(
            self, f"Benchmark: {', '.join(cols)} ({len(rows)} rows)")
        self.bench_dialog.show()
        self.bench_worker = BenchWorker(rows, cols, self.cb_order.currentIndex() == 1)
        self.bench_worker.progress.connect(self.sort_result.setText)
        self.bench_worker.result.connect(self.bench_dialog.add_result)
        self.bench_worker.finished.connect(self.bench_done)
        self.bench_worker.start()

    def bench_done(self):
        self.bench_dialog.finished()
        self.sort_result.setText("Benchmark complete.")
        self.set_busy(False)

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()
        for w in (self.sort_worker, self.bench_worker):
            if w and w.isRunning():
                w.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())