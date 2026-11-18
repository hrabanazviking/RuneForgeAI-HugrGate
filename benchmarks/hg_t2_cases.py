"""Fixed HG-T2 benchmark case set (frozen for the readiness gate).

24 categorical triage cases over [routine, attention, escalate]:
12 CLEAR cases whose text names the verdict (rules settle these) and
12 HARD cases with no verdict word at all (rules cannot settle these;
this is the set the model path must earn its cost on, or stay off).
Hard-case texts deliberately contain none of the option tokens (or a
token starting with one), so the keyword backend scores them all zero.
"""

from __future__ import annotations

SPEC = {"type": "categorical",
        "options": ["routine", "attention", "escalate"],
        "metadata": {"option_definitions": {
            "routine": "normal or expected, no action needed",
            "attention": "a real issue a human should review soon, "
                         "but not urgent and nothing is actively "
                         "failing or dangerous",
            "escalate": "urgent: active failure, danger, or "
                        "security breach needing immediate action"}}}

CASES = [
    # --- clear: verdict word present ---------------------------------
    {"id": "clear-01", "kind": "clear", "expected": "escalate",
     "text": "escalate this incident now, the site is down"},
    {"id": "clear-02", "kind": "clear", "expected": "escalate",
     "text": "please escalate the outage to the on-call team"},
    {"id": "clear-03", "kind": "clear", "expected": "escalate",
     "text": "escalate: payment errors on every checkout"},
    {"id": "clear-04", "kind": "clear", "expected": "escalate",
     "text": "we must escalate the security breach immediately"},
    {"id": "clear-05", "kind": "clear", "expected": "attention",
     "text": "attention: the queue is growing slowly today"},
    {"id": "clear-06", "kind": "clear", "expected": "attention",
     "text": "this needs attention before the end of the week"},
    {"id": "clear-07", "kind": "clear", "expected": "attention",
     "text": "attention, disk usage is higher than usual"},
    {"id": "clear-08", "kind": "clear", "expected": "attention",
     "text": "flag for attention: one region is responding slowly"},
    {"id": "clear-09", "kind": "clear", "expected": "routine",
     "text": "routine daily summary, nothing unusual to report"},
    {"id": "clear-10", "kind": "clear", "expected": "routine",
     "text": "a routine heartbeat from the backup job"},
    {"id": "clear-11", "kind": "clear", "expected": "routine",
     "text": "routine check complete, all values normal"},
    {"id": "clear-12", "kind": "clear", "expected": "routine",
     "text": "routine log rotation finished as scheduled"},
    # --- hard: no verdict word; semantics only -----------------------
    {"id": "hard-01", "kind": "hard", "expected": "escalate",
     "text": "the database is corrupting records and customers "
             "cannot check out, page someone now"},
    {"id": "hard-02", "kind": "hard", "expected": "escalate",
     "text": "smoke is coming from the server rack, clear the row"},
    {"id": "hard-03", "kind": "hard", "expected": "escalate",
     "text": "payments have been failing for every order since noon"},
    {"id": "hard-04", "kind": "hard", "expected": "escalate",
     "text": "an unknown person tailgated into the server room"},
    {"id": "hard-05", "kind": "hard", "expected": "attention",
     "text": "disk usage is creeping up and will fill within days"},
    {"id": "hard-06", "kind": "hard", "expected": "attention",
     "text": "a few users say pages load slowly this morning"},
    {"id": "hard-07", "kind": "hard", "expected": "attention",
     "text": "the certificate expires next month, plan its renewal"},
    {"id": "hard-08", "kind": "hard", "expected": "attention",
     "text": "one cache node keeps restarting but service is fine"},
    {"id": "hard-09", "kind": "hard", "expected": "routine",
     "text": "the nightly backup finished without any issues"},
    {"id": "hard-10", "kind": "hard", "expected": "routine",
     "text": "the weekly summary is ready whenever you want it"},
    {"id": "hard-11", "kind": "hard", "expected": "routine",
     "text": "the new hire starts monday and the laptop is imaged"},
    {"id": "hard-12", "kind": "hard", "expected": "routine",
     "text": "the sunday maintenance window is confirmed as planned"},
]
