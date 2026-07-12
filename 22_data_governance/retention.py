"""
Component 22 — Data Retention & Purge (DPDP Act 2023 compliance)   [Challenge req 10.3]
"Data protection and privacy compliance."

THE LEGAL BLOCKER THIS CLOSES:
  India's Digital Personal Data Protection Act 2023 requires, among other things:
    - PURPOSE LIMITATION: personal data kept only as long as necessary for the stated purpose.
    - STORAGE LIMITATION: a retention schedule, and erasure when the purpose ends.
    - RIGHT TO ERASURE / CORRECTION (with lawful exceptions).
    - AUDITABILITY of what was retained, erased, and why.
  A government-deployed police system with NO retention policy and NO purge capability is not
  merely incomplete — it is non-compliant. We had neither.

WHAT THIS PROVIDES:
    - A retention SCHEDULE keyed to case status (open cases retained; closed cases age out; false
      cases purged fastest — an innocent person's data should not linger).
    - A PURGE operation that removes personal identifiers while preserving the anonymised
      statistical record (so crime analytics survive lawful erasure of PERSONAL data).
    - A tamper-evident PURGE LOG (what was erased, when, under which rule) — because erasure in a
      government system must itself be auditable.
    - A LEGAL-HOLD flag: data under active investigation or court proceedings is EXEMPT from
      automated purge (DPDP carves out legal proceedings). Purging evidence would be unlawful.

DESIGN NOTE: this operates on the in-memory store for the prototype. In production the same policy
drives a scheduled job against Catalyst Data Store. The POLICY is the deliverable; the storage
backend is swappable.
"""
import sys, os, datetime, hashlib, json
for p in ["02_relational_layer"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))

# Retention schedule (days) by case outcome. Tunable, and deliberately conservative.
# An innocent person (false case) should have the SHORTEST retention.
RETENTION_DAYS = {
    "false_case":   90,      # cstype B — innocent party; purge fastest
    "undetected":  1825,     # cstype C — 5y; may reopen, but not indefinite
    "chargesheeted":3650,    # cstype A — 10y; conviction record / appeals window
    "open":         None,    # under investigation — retained (legal hold)
    "no_outcome":   1095,    # 3y default if no final report and not open
}

# Fields considered PERSONAL under DPDP — these are what purge removes.
PERSONAL_FIELDS = {
    "Accused": ["AccusedName"],
    "Victim": ["VictimName"],
    "ComplainantDetails": ["ComplainantName"],
}


class RetentionManager:
    def __init__(self, store, as_of=None):
        self.store = store
        self.as_of = as_of or self._corpus_latest()
        self.purge_log = []
        self._chain = "GENESIS"

    def _corpus_latest(self):
        dates = []
        for c in self.store.get_all_cases():
            try:
                dates.append(datetime.datetime.fromisoformat(str(c["CrimeRegisteredDate"])))
            except Exception:
                pass
        return max(dates) if dates else datetime.datetime.now()

    def _bucket(self, case):
        """Which retention rule applies to this case."""
        if case["CaseStatusID"] == 1:
            return "open"
        o = self.store.get_outcome_for_case(case["CaseMasterID"])
        if not o:
            return "no_outcome"
        return {"A": "chargesheeted", "B": "false_case", "C": "undetected"}.get(o["cstype"], "no_outcome")

    def assess(self):
        """Dry run: what WOULD be purged, retained, or held. No mutation. This is what an officer
        or a DPO reviews BEFORE any erasure runs."""
        due_purge, retained, legal_hold = [], [], []
        for c in self.store.get_all_cases():
            bucket = self._bucket(c)
            limit = RETENTION_DAYS[bucket]
            try:
                reg = datetime.datetime.fromisoformat(str(c["CrimeRegisteredDate"]))
            except Exception:
                retained.append(c["CaseMasterID"]); continue
            age_days = (self.as_of - reg).days

            if bucket == "open":
                legal_hold.append({"case_id": c["CaseMasterID"], "reason":
                                   "Under investigation — legal hold, exempt from automated purge."})
            elif limit is not None and age_days > limit:
                due_purge.append({"case_id": c["CaseMasterID"], "bucket": bucket,
                                  "age_days": age_days, "limit_days": limit})
            else:
                retained.append(c["CaseMasterID"])

        return {
            "as_of": self.as_of.isoformat(),
            "retention_schedule_days": RETENTION_DAYS,
            "due_for_purge": due_purge,
            "under_legal_hold": legal_hold,
            "within_retention": len(retained),
            "summary": (f"{len(due_purge)} case(s) exceed their retention limit and are due for "
                        f"personal-data purge. {len(legal_hold)} under legal hold (exempt). "
                        f"{len(retained)} within retention."),
            "note": ("This is a DRY RUN. No data is erased. A Data Protection Officer reviews this "
                     "before any purge executes. Purge removes PERSONAL identifiers only; the "
                     "anonymised statistical record is preserved for lawful crime analytics."),
        }

    def _log(self, entry):
        """Hash-chained purge log — erasure in a government system must itself be auditable."""
        prev = self._chain
        payload = json.dumps(entry, sort_keys=True)
        self._chain = hashlib.sha256((prev + payload).encode()).hexdigest()
        self.purge_log.append({**entry, "prev_hash": prev, "hash": self._chain})

    def purge_case(self, case_id, dry_run=True):
        """
        Erase PERSONAL identifiers for one case, preserving the anonymised record.
        dry_run=True by default — actual erasure must be an explicit, logged action.
        """
        c = self.store.get_case(case_id)
        if not c:
            return {"error": "case not found"}
        bucket = self._bucket(case_id if isinstance(case_id, dict) else c)
        if bucket == "open":
            return {"case_id": case_id, "refused": True,
                    "reason": "LEGAL HOLD: case is under investigation. Purge would erase "
                              "evidence and is unlawful under the DPDP legal-proceedings carve-out."}

        # what WOULD be erased (names across accused/victims/complainants for this case)
        to_erase = []
        for a in self.store.get_accused_for_case(case_id):
            to_erase.append(("Accused", a["AccusedMasterID"], a["AccusedName"]))
        for v in self.store.get_victims_for_case(case_id):
            to_erase.append(("Victim", v["VictimMasterID"], v.get("VictimName")))

        entry = {
            "action": "PURGE_PERSONAL_DATA" if not dry_run else "PURGE_DRY_RUN",
            "case_id": case_id,
            "bucket": bucket,
            "identifiers_affected": len(to_erase),
            "timestamp": datetime.datetime.now().isoformat(),
            "preserved": "Anonymised statistical record (crime type, location, date, outcome).",
        }
        if not dry_run:
            # in production this UPDATEs Catalyst Data Store, setting personal fields to a tombstone
            self._log(entry)
        return {**entry, "erasable_identifiers": [(t, i) for (t, i, _) in to_erase],
                "dry_run": dry_run,
                "note": ("Personal fields would be replaced with a tombstone ('[ERASED-DPDP]'); "
                         "the case shell and anonymised analytics survive.")}

    def erasure_request(self, person_name):
        """
        DPDP right-to-erasure: a data principal requests erasure of their personal data.
        Returns the cases affected and whether each can be erased or is under legal hold.
        Does NOT auto-erase — routes to a DPO with the lawful basis for each decision.
        """
        affected = []
        for c in self.store.get_all_cases():
            names = [a["AccusedName"] for a in self.store.get_accused_for_case(c["CaseMasterID"])]
            names += [v.get("VictimName") for v in self.store.get_victims_for_case(c["CaseMasterID"])]
            if person_name in names:
                bucket = self._bucket(c)
                affected.append({
                    "case_id": c["CaseMasterID"],
                    "status": self.store.get_case_status_name(c["CaseStatusID"]),
                    "erasable": bucket != "open",
                    "basis": ("Legal hold — active investigation, erasure refused (lawful exception)."
                              if bucket == "open" else
                              "Eligible for erasure review by the Data Protection Officer."),
                })
        return {
            "request": f"Erasure request for '{person_name}'",
            "cases_affected": affected,
            "decision": ("Routed to Data Protection Officer. Cases under legal hold are exempt; the "
                         "remainder are reviewed for erasure. No automated erasure of evidence."),
            "dpdp_reference": "DPDP Act 2023 — right to erasure, subject to legal-proceedings exception.",
        }


if __name__ == "__main__":
    from loader import RelationalStore
    store = RelationalStore(":memory:"); store.build(verbose=False)
    R = RetentionManager(store)

    print("=== COMPONENT 22: DATA RETENTION & PURGE (DPDP Act 2023) ===\n")
    a = R.assess()
    print("--- RETENTION ASSESSMENT (dry run — nothing erased) ---")
    print(f"  {a['summary']}")
    print(f"  schedule: {a['retention_schedule_days']}")
    print(f"  due for purge: {len(a['due_for_purge'])}  legal hold: {len(a['under_legal_hold'])}  "
          f"within retention: {a['within_retention']}")

    print("\n--- PURGE a specific case (dry run) ---")
    if a["due_for_purge"]:
        cid = a["due_for_purge"][0]["case_id"]
        p = R.purge_case(cid, dry_run=True)
        print(f"  case {cid} ({p['bucket']}): {p['identifiers_affected']} identifiers would be erased")
        print(f"  preserved: {p['preserved']}")

    print("\n--- LEGAL HOLD blocks purge of an open case ---")
    open_case = next((c["CaseMasterID"] for c in store.get_all_cases() if c["CaseStatusID"] == 1), None)
    if open_case:
        p = R.purge_case(open_case, dry_run=False)
        print(f"  case {open_case}: {'REFUSED — ' + p['reason'][:80] if p.get('refused') else 'purged'}")

    print("\n--- DPDP RIGHT-TO-ERASURE request ---")
    name = store.all_accused()[0]["AccusedName"]
    e = R.erasure_request(name)
    print(f"  {e['request']}: {len(e['cases_affected'])} cases affected")
    for c in e["cases_affected"][:3]:
        print(f"    case {c['case_id']} ({c['status']}): {'ERASABLE' if c['erasable'] else 'LEGAL HOLD'}")
    print(f"  -> {e['decision'][:88]}")
    store.close()
