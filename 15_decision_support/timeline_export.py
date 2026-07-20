"""
Component 15 — Investigator Decision Support: Timelines + PDF Export
  [req 6: "Automated case summaries and investigation timelines"]
  [req 1: "Save the Conversation History in PDF format locally"]

Timeline reconstructs the chronology of a case from the FIR record itself (incident -> report ->
registration -> arrests -> chargesheet), plus any LINKED offences surfaced by identity resolution
— which is the part an officer cannot get from the case file alone.

PDF export: pure-stdlib PDF writer (no third-party dependency, so nothing extra to vendor into
Catalyst's 256MB disk budget). Produces a valid PDF 1.4 with selectable text.
"""
import sys, os, datetime, zlib
import textwrap
for p in ["02_relational_layer","03_graph_construction","05_entity_resolution"]:
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), p))


# ─────────────────────────── INVESTIGATION TIMELINE ───────────────────────────
class CaseTimeline:
    def __init__(self, store, resolved_groups=None):
        self.store = store
        self.groups = resolved_groups or []
        self.identity_of = {}
        for gi, g in enumerate(self.groups):
            for amid in g:
                self.identity_of[amid] = gi

    @staticmethod
    def _dt(v):
        try:
            return datetime.datetime.fromisoformat(str(v))
        except Exception:
            return None

    def build(self, case_id):
        c = self.store.get_case(case_id)
        if not c:
            return None
        ev = []

        inc = self._dt(c["IncidentFromDate"])
        if inc:
            ev.append({"when": inc, "type": "INCIDENT",
                       "what": f"Offence occurred ({inc.strftime('%H:%M')})",
                       "source": f"CaseMaster.IncidentFromDate (FIR {case_id})"})
        rec = self._dt(c["InfoReceivedPSDate"])
        if rec:
            ev.append({"when": rec, "type": "REPORTED",
                       "what": "Information received at police station",
                       "source": f"CaseMaster.InfoReceivedPSDate (FIR {case_id})"})
        reg = self._dt(c["CrimeRegisteredDate"])
        if reg:
            ev.append({"when": reg, "type": "FIR REGISTERED",
                       "what": f"FIR {c['CrimeNo']} registered",
                       "source": f"CaseMaster.CrimeRegisteredDate (FIR {case_id})"})

        for a in self.store.get_accused_for_case(case_id):
            for ar in self.store.get_arrests_for_accused(a["AccusedMasterID"]):
                d = self._dt(ar.get("ArrestSurrenderDate"))
                if d:
                    ev.append({"when": d, "type": "ARREST",
                               "what": f"{a['AccusedName']} arrested/surrendered",
                               "source": f"ArrestSurrender (accused {a['AccusedMasterID']})"})

        # LINKED PRIOR OFFENCES via resolved identity — invisible in the case file itself
        linked = []
        for a in self.store.get_accused_for_case(case_id):
            gi = self.identity_of.get(a["AccusedMasterID"])
            if gi is None:
                continue
            for amid in self.groups[gi]:
                other = next((x for x in self.store.all_accused()
                              if x["AccusedMasterID"] == amid), None)
                if not other or other["CaseMasterID"] == case_id:
                    continue
                oc = self.store.get_case(other["CaseMasterID"])
                if not oc:
                    continue
                d = self._dt(oc["CrimeRegisteredDate"])
                if d:
                    linked.append({"when": d, "type": "LINKED PRIOR OFFENCE",
                                   "what": (f"Same person ({other['AccusedName']}) in FIR "
                                            f"{other['CaseMasterID']} "
                                            f"[{self.store.get_crime_subhead_name(oc['CrimeMinorHeadID'])}]"),
                                   "source": (f"Identity:{gi} — cross-case resolution, "
                                              f"FIR {other['CaseMasterID']}")})
        ev.extend(linked)
        # ORDERING FIX. Per the real schema, CrimeRegisteredDate is a DATE (no time) while
        # IncidentFromDate is a DATETIME — so a naive sort put "FIR REGISTERED 00:00" BEFORE the
        # incident at 14:00 on the same day, i.e. the FIR was filed before the crime happened.
        # The data is schema-correct; the SORT was wrong. Within the same calendar day we order by
        # the real-world causal sequence instead of by a clock time the schema does not carry.
        SEQ = {"INCIDENT": 0, "REPORTED": 1, "FIR REGISTERED": 2, "ARREST": 3,
               "CHARGESHEET": 4, "LINKED PRIOR OFFENCE": 5}
        ev.sort(key=lambda e: (e["when"].date(), SEQ.get(e["type"], 9), e["when"]))
        return {
            "case_id": case_id,
            "crime_no": c["CrimeNo"],
            "status": self.store.get_case_status_name(c["CaseStatusID"]),
            "events": ev,
            "linked_prior_count": len(linked),
            "citations": sorted({case_id} | {int(e["source"].split("FIR ")[-1].rstrip(")"))
                                             for e in linked if "FIR " in e["source"]}),
        }

    def render(self, tl):
        L = [f"INVESTIGATION TIMELINE — FIR {tl['crime_no']} (case {tl['case_id']})",
             f"Status: {tl['status']}", ""]
        DATE_ONLY = {"FIR REGISTERED", "LINKED PRIOR OFFENCE", "CHARGESHEET"}
        for e in tl["events"]:
            marker = ">>" if e["type"] == "LINKED PRIOR OFFENCE" else "  "
            # don't print a fake 00:00 clock time for fields the schema stores as DATE only
            stamp = (e["when"].strftime('%Y-%m-%d') + "      ") if e["type"] in DATE_ONLY \
                    else e["when"].strftime('%Y-%m-%d %H:%M')
            L.append(f" {marker} {stamp}  [{e['type']:<21}] {e['what']}")
            L.append(f"                          source: {e['source']}")
        if tl["linked_prior_count"]:
            L.append("")
            L.append(f" >> {tl['linked_prior_count']} LINKED PRIOR OFFENCE(S) surfaced by identity")
            L.append("    resolution — these do NOT appear anywhere in this case file.")
        return "\n".join(L)


# ─────────────────────────── PDF EXPORT (stdlib only) ───────────────────────────
def _esc(s):
    return (str(s).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)"))


def conversation_to_pdf(path, title, lines, meta=None):
    """
    Minimal, dependency-free PDF 1.4 writer. Text is selectable (not an image).
    Non-Latin glyphs (Kannada) are transliterated to a Latin note, because embedding a Kannada
    TrueType font would require shipping the font binary — we state that limitation openly rather
    than silently dropping the characters.
    """
    W, H, M, LH, FS = 595, 842, 50, 14, 10          # A4 points

    # PDF DOES NOT WRAP. A LONG LINE IS SILENTLY CUT AT THE PAGE EDGE.
    # Found by reading an exported transcript: a briefing ended "...Ask " and the next question
    # began on the same visual line. The answer was complete in the data - the page just stopped
    # drawing it. An officer's saved record was losing its own content, which is worse than not
    # offering the export at all, because it looks complete.
    # 495pt of usable width at 10pt Helvetica is ~99 characters; 92 leaves room for wide glyphs.
    # Measure the ESCAPED length: _esc() turns "(" into "\\(", so a line of exactly 92 characters
    # can render at 94 and clip anyway. Wrap against what actually gets drawn, not the source.
    WRAP = 92
    def _fits(t):
        return len(_esc(t)) <= WRAP

    wrapped = []
    for _ln in lines:
        if _fits(_ln):
            wrapped.append(_ln)
            continue
        _indent = len(_ln) - len(_ln.lstrip())
        _pad = " " * _indent
        _w = max(20, WRAP - _indent)
        while _w > 20:
            _segs = textwrap.wrap(_ln.strip(), _w) or [""]
            if all(_fits(_pad + sg) for sg in _segs):
                break
            _w -= 4
        wrapped.extend(_pad + sg for sg in _segs)
    lines = wrapped

    page_lines, pages = [], []
    y = H - M - 30
    for ln in lines:
        if y < M + LH:
            pages.append(page_lines); page_lines = []; y = H - M
        page_lines.append((M, y, ln))
        y -= LH
    if page_lines:
        pages.append(page_lines)

    objs, content_ids = [], []
    for pi, plines in enumerate(pages):
        parts = ["BT", "/F1 14 Tf", f"1 0 0 1 {M} {H - M} Tm",
                 f"({_esc(title)}) Tj", "ET"]
        if pi == 0 and meta:
            parts += ["BT", "/F1 8 Tf", f"1 0 0 1 {M} {H - M - 14} Tm",
                      f"({_esc(meta)}) Tj", "ET"]
        parts += ["BT", f"/F1 {FS} Tf"]
        for (x, yy, ln) in plines:
            safe = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(ln))
            parts += [f"1 0 0 1 {x} {yy} Tm", f"({_esc(safe)}) Tj"]
        parts += ["ET"]
        stream = "\n".join(parts).encode("latin-1", "replace")
        content_ids.append(stream)

    n_pages = len(pages)
    out = [b"%PDF-1.4\n"]
    offsets = [0]

    def add(obj_bytes):
        offsets.append(sum(len(x) for x in out))
        out.append(obj_bytes)

    kids = " ".join(f"{4 + 2*i} 0 R" for i in range(n_pages))
    add(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    add(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>\nendobj\n".encode())
    add(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    for i, stream in enumerate(content_ids):
        pid, cid = 4 + 2*i, 5 + 2*i
        add(f"{pid} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>\nendobj\n".encode())
        add(f"{cid} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode() + stream +
            b"\nendstream\nendobj\n")

    xref_pos = sum(len(x) for x in out)
    n_objs = 3 + 2*n_pages + 1
    xref = [f"xref\n0 {n_objs}\n", "0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n")
    out.append("".join(xref).encode())
    out.append(f"trailer\n<< /Size {n_objs} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())

    with open(path, "wb") as f:
        for chunk in out:
            f.write(chunk)
    return path


def export_conversation(path, session_turns, user, role):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["", f"Officer: {user}    Role: {role}", f"Exported: {ts}", "-" * 78, ""]
    for i, t in enumerate(session_turns, 1):
        lines.append(f"[Q{i}] {t['query']}")
        ctx = t.get("context", {})
        lines.append(f"      intent={ctx.get('intent')}  case={ctx.get('case_id')}  "
                     f"lang={ctx.get('language')}")
        for ln in str(t.get("answer", "")).split("\n")[:6]:
            lines.append(f"      {ln}")
        lines.append("")
    lines += ["-" * 78,
              "Every answer above is generated from cited FIR records.",
              "KAVERI is a decision-support tool. A human officer verifies before any action.",
              "NOTE: Kannada glyphs are shown as '?' in this PDF — embedding a Kannada TrueType",
              "font is required for full script rendering and is a known limitation."]
    return conversation_to_pdf(path, "KAVERI — Conversation History",
                               lines, meta="Karnataka State Police — Investigation Copilot")


if __name__ == "__main__":
    from loader import RelationalStore
    from graph_store import NetworkXGraphStore
    from build_graph import build
    from resolve import resolve
    sys.path.insert(0, os.path.join(os.path.dirname(os.getcwd()), "04_extraction"))
    from extract import enrich

    store = RelationalStore(":memory:"); store.build(verbose=False)
    graph = NetworkXGraphStore(); build(store, graph); enrich(store, graph)
    _, _, _, groups, _ = resolve(store, graph)

    print("=== COMPONENT 15: INVESTIGATION TIMELINE + PDF EXPORT ===\n")
    T = CaseTimeline(store, groups)
    tl = T.build(17)                      # the Kannada-variant repeat offender
    print(T.render(tl))

    print("\n\n--- PDF EXPORT (stdlib only, nothing to vendor) ---")
    turns = [
        {"query": "Show the network for FIR 1",
         "context": {"intent": "network", "case_id": 1, "language": "en"},
         "answer": "7 cases linked via 2 shared phones. Accused Ramesh Gowda [Identity:0]."},
        {"query": "What is his prior history?",
         "context": {"intent": "identity_history", "case_id": 1, "language": "en"},
         "answer": "5 linked cases after cross-case identity resolution. Risk 60.4/100 MEDIUM."},
    ]
    out = export_conversation("/tmp/kaveri_conversation.pdf", turns, "IO Ramesh", "station_officer")
    size = os.path.getsize(out)
    with open(out, "rb") as f:
        head = f.read(9)
    print(f"  wrote {out}  ({size} bytes)  header={head!r}")
    print(f"  valid PDF: {head.startswith(b'%PDF-1.4')}")
    store.close()
