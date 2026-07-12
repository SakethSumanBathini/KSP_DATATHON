"""
Component 2 — Relational loader + data-access API.
Loads Component 1's CSVs into SQLite (swappable target), enforcing schema + FKs.
CONTRACT CHECK: validates every CSV's columns against the expected contract and
fails LOUDLY if they don't match — no silent assumptions across the boundary.
"""
import sqlite3, threading, csv, os, sys
from schema import TABLES, LOAD_ORDER

class ContractViolation(Exception): pass

class _LockedConnection:
    """
    Thread-safe proxy around a shared sqlite3 connection.

    THE BUG THIS FIXES (reproduced, not theoretical — a 12-thread stress test raised
    "InterfaceError: bad parameter or other API misuse"):
    Flask serves requests CONCURRENTLY. One sqlite3 connection shared across threads with
    check_same_thread=False corrupts under interleaved cursor use, and — far worse than an
    exception — it can SILENTLY RETURN THE WRONG ROWS. In a police system that means one officer
    being shown another case's data. Absence of an exception is NOT proof of safety.

    Design: execute() takes the lock, runs the query, MATERIALISES all rows while still holding
    the lock, then releases it and hands back a list-like result. The cursor never escapes the
    critical section, so no interleaving is possible. The DB is in-memory and read-only after
    build(), so reads are microseconds and contention is negligible. Correctness over speed.

    This wraps the CONNECTION rather than rewriting 12 call sites — fewer places to get wrong.
    (I know: I first tried the bulk rewrite and it silently swapped fetchone/fetchall.)
    """

    class _Result(list):
        """Behaves like a cursor for our access patterns AND like a list."""
        def fetchall(self):
            return list(self)

        def fetchone(self):
            return self[0] if self else None

    def __init__(self, conn, lock):
        self._conn = conn
        self._lock = lock

    def execute(self, sql, args=()):
        with self._lock:
            cur = self._conn.execute(sql, args)
            rows = cur.fetchall()          # materialise INSIDE the lock
        return self._Result(rows)

    def executemany(self, sql, seq):
        with self._lock:
            return self._conn.executemany(sql, seq)

    def commit(self):
        with self._lock:
            return self._conn.commit()

    def cursor(self):
        return self._conn.cursor()         # build-time only, single-threaded

    def close(self):
        with self._lock:
            return self._conn.close()


class RelationalStore:
    def __init__(self, db_path=":memory:", csv_dir=None):
        self.db_path = db_path
        self.csv_dir = csv_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "01_data_generator")
        # check_same_thread=False: allow the built-once in-memory DB to serve web-server
        # worker threads (read-only after build, so this is safe).
        _raw = sqlite3.connect(self.db_path, check_same_thread=False)
        _raw.row_factory = sqlite3.Row
        self._db_lock = threading.RLock()
        self._raw = _raw
        # every read from here on is serialised — see _LockedConnection above
        self.conn = _LockedConnection(_raw, self._db_lock)
        # (row_factory set on the raw connection above)
        self.conn.execute("PRAGMA foreign_keys = ON")

    # ---- CONTRACT CHECK (the boundary guard) ----
    def _check_contract(self, table):
        create_sql, csv_name, expected_cols = TABLES[table]
        path = os.path.join(self.csv_dir, csv_name)
        if not os.path.exists(path):
            raise ContractViolation(f"[{table}] expected input CSV missing: {csv_name}")
        with open(path, encoding="utf-8") as f:
            header = next(csv.reader(f))
        if header != expected_cols:
            raise ContractViolation(
                f"[{table}] CSV column contract mismatch.\n"
                f"  expected: {expected_cols}\n  found:    {header}\n"
                f"  Component 1 output does not match Component 2's expected interface. Halting.")
        return path, create_sql

    def build(self, verbose=True):
        report = {"tables_loaded": {}, "contract_checks": "all passed", "fk_integrity": None}
        cur = self.conn.cursor()
        for table in LOAD_ORDER:
            path, create_sql = self._check_contract(table)   # fail loudly here if mismatch
            cur.execute(create_sql)
            with open(path, encoding="utf-8") as f:
                rd = csv.DictReader(f)
                cols = TABLES[table][2]
                placeholders = ",".join("?" for _ in cols)
                insert = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
                n = 0
                for row in rd:
                    vals = [row[c] if row[c] != "" else None for c in cols]
                    cur.execute(insert, vals)     # parameterized — no string concatenation
                    n += 1
            report["tables_loaded"][table] = n
            if verbose: print(f"  loaded {table}: {n}")
        self.conn.commit()
        # FK integrity check across the whole DB
        violations = cur.execute("PRAGMA foreign_key_check").fetchall()
        report["fk_integrity"] = "PASS (no violations)" if not violations else f"FAIL: {len(violations)} violations"
        report["fk_violations"] = [dict(v) if hasattr(v,'keys') else tuple(v) for v in violations]
        return report

    # ================= DATA-ACCESS API (parameterized only) =================
    # Components 3 and 4 consume ONLY through these methods, never raw CSV.
    def get_all_cases(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM CaseMaster").fetchall()]

    def get_case(self, case_id):
        r = self.conn.execute("SELECT * FROM CaseMaster WHERE CaseMasterID = ?", (case_id,)).fetchone()
        return dict(r) if r else None

    def get_accused_for_case(self, case_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM Accused WHERE CaseMasterID = ?", (case_id,)).fetchall()]

    def get_victims_for_case(self, case_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM Victim WHERE CaseMasterID = ?", (case_id,)).fetchall()]

    def get_complainants_for_case(self, case_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM ComplainantDetails WHERE CaseMasterID = ?", (case_id,)).fetchall()]

    def get_sections_for_case(self, case_id):
        return [dict(r) for r in self.conn.execute("""
            SELECT asa.CaseMasterID, asa.ActID, asa.SectionID,
                   a.ShortName AS ActShortName, a.Active AS ActActive,
                   s.SectionDescription, s.Active AS SectionActive
            FROM ActSectionAssociation asa
            JOIN Act a ON a.ActCode = asa.ActID
            LEFT JOIN Section s ON s.ActCode = asa.ActID AND s.SectionCode = asa.SectionID
            WHERE asa.CaseMasterID = ?""", (case_id,)).fetchall()]

    def get_arrests_for_accused(self, accused_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM ArrestSurrender WHERE AccusedMasterID = ?", (accused_id,)).fetchall()]

    def get_station(self, unit_id):
        r = self.conn.execute("""SELECT u.*, d.DistrictName FROM Unit u
            JOIN District d ON d.DistrictID = u.DistrictID WHERE u.UnitID = ?""", (unit_id,)).fetchone()
        return dict(r) if r else None

    def get_district_for_case(self, case_id):
        r = self.conn.execute("""SELECT d.DistrictID, d.DistrictName FROM CaseMaster cm
            JOIN Unit u ON u.UnitID = cm.PoliceStationID
            JOIN District d ON d.DistrictID = u.DistrictID WHERE cm.CaseMasterID = ?""",
            (case_id,)).fetchone()
        return dict(r) if r else None

    # ---- reference-table lookups (used by sociological + trend analysis) ----
    # Table/column names CANNOT be parameterised in SQL, so they are interpolated. Today every
    # caller passes a hardcoded literal, but an interpolated identifier is a latent injection hole:
    # the day someone routes a user-supplied string here, it becomes exploitable. We close it now
    # with a strict allowlist rather than relying on every future caller being careful.
    _ALLOWED_LOOKUPS = {
        ("OccupationMaster",  "OccupationID",   "OccupationName"),
        ("ReligionMaster",    "ReligionID",     "ReligionName"),
        ("CasteMaster",       "caste_master_id","caste_master_name"),
        ("CrimeSubHead",      "CrimeSubHeadID", "CrimeHeadName"),
        ("CaseStatusMaster",  "CaseStatusID",   "CaseStatusName"),
        ("GravityOffence",    "GravityOffenceID","LookupValue"),
    }

    def _lookup(self, table, id_col, name_col, key):
        if key is None:
            return None
        if (table, id_col, name_col) not in self._ALLOWED_LOOKUPS:
            raise ValueError(f"Disallowed lookup: {table}.{id_col}/{name_col}")
        r = self.conn.execute(
            f"SELECT {name_col} AS n FROM {table} WHERE {id_col}=?", (key,)).fetchone()
        return r["n"] if r else None

    def get_occupation_name(self, occupation_id):
        return self._lookup("OccupationMaster", "OccupationID", "OccupationName", occupation_id)

    def get_religion_name(self, religion_id):
        return self._lookup("ReligionMaster", "ReligionID", "ReligionName", religion_id)

    def get_caste_name(self, caste_id):
        return self._lookup("CasteMaster", "caste_master_id", "caste_master_name", caste_id)

    def get_crime_subhead_name(self, subhead_id):
        return self._lookup("CrimeSubHead", "CrimeSubHeadID", "CrimeHeadName", subhead_id)

    def get_case_status_name(self, status_id):
        return self._lookup("CaseStatusMaster", "CaseStatusID", "CaseStatusName", status_id)

    def get_gravity_name(self, gravity_id):
        return self._lookup("GravityOffence", "GravityOffenceID", "LookupValue", gravity_id)

    # ---- investigation outcomes (ChargesheetDetails) ----
    def get_outcome_for_case(self, case_id):
        """Final report for a case: A=Chargesheet, B=False case, C=Undetected. None if still open."""
        r = self.conn.execute(
            "SELECT * FROM ChargesheetDetails WHERE CaseMasterID = ?", (case_id,)).fetchone()
        return dict(r) if r else None

    def all_outcomes(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM ChargesheetDetails").fetchall()]

    def all_accused(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM Accused").fetchall()]

    def close(self): self.conn.close()


if __name__ == "__main__":
    store = RelationalStore(db_path=":memory:")
    print("=== COMPONENT 2: LOAD + CONTRACT CHECK ===")
    try:
        rep = store.build(verbose=True)
    except ContractViolation as e:
        print("CONTRACT VIOLATION:\n", e); sys.exit(1)
    print("\nContract checks:", rep["contract_checks"])
    print("FK integrity:", rep["fk_integrity"])
    print("Total rows:", sum(rep["tables_loaded"].values()))
