"""Evidence-semantics checks for holdout artifacts (``gov evidence``).

Two attestation failures found by a 2026-09 production evidence grill
(dual-snapshot generator):

1. **A claimed cutoff later than the run that produced it.** A snapshot
   generator stamped its output "as of 14:59" but read data until 15:02
   (``now - lag`` pretending to be a historical section).  If a gate's
   evidence declares a ``data_cutoff`` (the data time the evidence reflects)
   that is *later than* its own ``run_at``, the cutoff cannot be genuine —
   evidence cannot contain data newer than the moment it was produced.

2. **Same-source evidence counted as independent.** Two files produced from
   the same underlying source at the same declared cutoff are one time
   slice, not two independent confirmations — regardless of byte content
   (volatile stamps differ; the information does not).  Same source, same
   ``data_cutoff``, two ``pass`` gates -> not independent.

Gate entries may attest ``evidence_source`` (which data lineage the evidence
rests on) and ``data_cutoff`` (the data time it reflects).  Attestation is
optional and backward compatible; when present, ``gov check`` / ``gov report``
enforce these rules fail-closed automatically.  ``gov evidence`` runs the
same check standalone (read-only).  Rules:

- R1 ``duplicate_evidence_content``: two gate entries carrying the same
  non-empty ``report_ref`` are the same bytes counted twice.
- R2 ``data_cutoff_after_run_at``: declared data time later than the run
  that produced the evidence (the now-minus-lag forgery class).
- R3 ``same_source_slice_not_independent``: two ``pass`` entries declaring
  the same ``evidence_source`` and the same ``data_cutoff`` — one time
  slice cannot confirm twice.
- W1 ``same_source_multiple``: two ``pass`` entries sharing a source with
  different or undeclared cutoffs — sequential slices are complementary,
  not independent (warn, not block).
- W2 ``attestation_incomplete``: a ``data_cutoff`` without an
  ``evidence_source`` cannot be checked for independence.

Enforcement is opt-in: an artifact that declares no ``evidence_source`` /
``data_cutoff`` anywhere keeps the legacy semantics (a placeholder
``report_ref`` may legitimately back several gate entries in manual-attach
flows).  Once any gate attests, all rules apply to the whole artifact.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = "holdout_governance.evidence_semantics.v1"


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _cutoff_equal(left: Any, right: Any) -> bool:
    """Compare declared cutoffs (parsed when possible, raw string fallback)."""
    left_parsed = _parse_ts(left)
    right_parsed = _parse_ts(right)
    if left_parsed is not None and right_parsed is not None:
        try:
            return left_parsed == right_parsed
        except TypeError:  # naive vs aware comparison
            return str(left).strip() == str(right).strip()
    return str(left or "").strip() == str(right or "").strip() and bool(
        str(left or "").strip()
    )


def check_artifact_evidence(artifact: dict[str, Any]) -> dict[str, Any]:
    """Run the evidence-semantics rules over one v0.2 artifact (pure, read-only).

    Returns ``{schema_version, attested, ok, blockers, warns}``.
    ``attested`` is True when at least one gate entry declares
    ``evidence_source`` or ``data_cutoff``; R1 (duplicate content) runs
    always, R2/R3/W1/W2 only make sense on attested entries.
    """
    gates = [g for g in artifact.get("gates", []) if isinstance(g, dict)]
    blockers: list[str] = []
    warns: list[str] = []

    attested = any(
        str(gate.get("evidence_source") or "").strip()
        or str(gate.get("data_cutoff") or "").strip()
        for gate in gates
    )
    if not attested:
        # Legacy / manual-attach artifacts (same placeholder report_ref may
        # legitimately back several gate entries) are untouched: attestation
        # is the opt-in boundary for the stricter semantics.
        return {
            "schema_version": SCHEMA_VERSION,
            "attested": False,
            "ok": True,
            "blockers": [],
            "warns": [],
        }

    # R1: the same report bytes must not be counted twice.
    by_ref: dict[str, list[str]] = {}
    for gate in gates:
        ref = str(gate.get("report_ref") or "").strip()
        if ref:
            by_ref.setdefault(ref, []).append(str(gate.get("gate_id") or "?"))
    for ref, gate_ids in by_ref.items():
        if len(gate_ids) > 1:
            blockers.append(
                f"duplicate_evidence_content:{','.join(gate_ids)}:"
                f"{ref[:20]}"
            )

    pass_entries: list[dict[str, Any]] = []
    for gate in gates:
        gate_id = str(gate.get("gate_id") or "?")
        source = str(gate.get("evidence_source") or "").strip()
        cutoff = str(gate.get("data_cutoff") or "").strip()
        if cutoff and not source:
            warns.append(f"attestation_incomplete:{gate_id}:data_cutoff_without_source")
        run_at = str(gate.get("run_at") or "").strip()

        # R2: the data time cannot be later than the run that produced it.
        if cutoff:
            cutoff_ts = _parse_ts(cutoff)
            run_ts = _parse_ts(run_at)
            if cutoff_ts is None:
                warns.append(f"unparseable_data_cutoff:{gate_id}")
            elif run_ts is None:
                warns.append(f"attestation_incomplete:{gate_id}:no_run_at")
            else:
                try:
                    if cutoff_ts > run_ts:
                        blockers.append(
                            f"data_cutoff_after_run_at:{gate_id}:"
                            f"{cutoff}>{run_at}"
                        )
                except TypeError:
                    warns.append(f"unparseable_data_cutoff:{gate_id}:tz_mismatch")

        if gate.get("status") == "pass":
            pass_entries.append(
                {"gate_id": gate_id, "source": source, "cutoff": cutoff}
            )

    # R3 / W1: same source cannot confirm twice.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for entry in pass_entries:
        if entry["source"]:
            by_source.setdefault(entry["source"], []).append(entry)
    for source, entries in by_source.items():
        if len(entries) < 2:
            continue
        paired: set[tuple[str, str]] = set()
        for left in entries:
            for right in entries:
                if left is right:
                    continue
                key = tuple(sorted((left["gate_id"], right["gate_id"])))
                if key in paired:
                    continue
                paired.add(key)
                if left["cutoff"] and _cutoff_equal(left["cutoff"], right["cutoff"]):
                    blockers.append(
                        f"same_source_slice_not_independent:"
                        f"{left['gate_id']},{right['gate_id']}:{source}"
                    )
                else:
                    warns.append(
                        f"same_source_multiple:{source}:"
                        f"{left['gate_id']},{right['gate_id']}"
                    )
    # dedupe warnings (pairwise emission can repeat the same source pair)
    warns = list(dict.fromkeys(warns))
    blockers = list(dict.fromkeys(blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        "attested": True,
        "ok": not blockers,
        "blockers": blockers,
        "warns": warns,
    }
