from copy import deepcopy


COMMON = """Return compact JSON matching the supplied schema, using actual findings rather than
placeholders. Keep each explanation to one short sentence. Merge observations only when fact,
object identity, time, and source agree; keep distinct or conflicting evidence separate.

Use unique IDs: r for requirements, e for evidence, s for steps, and z for reasoning claims.
Frame IDs are ONE-BASED sampled-video positions; reference only supplied frames.

candidate_answer is a choice letter or one number encoded as a string in the requested units, or
JSON null when unavailable. Never output the literal string "null". State uncertainty without
inventing facts."""

NATIVE = """Answer directly from the supplied video using native visual and spatial reasoning; no
supplementary tools are available. Identify the concrete facts needed for the answer(e.g.,
identity, count, position, relation, dimension, or time) and record the corresponding native
observations.

Label a requirement SUPPORTED only when the observations resolve it; otherwise label it
UNRESOLVED and state the missing information. Requirements describe facts, not the final answer
task. Every SUPPORTED requirement must reference matching evidence through requirement_id and
evidence_ids. unresolved_requirements contains exactly the UNRESOLVED IDs. Preserve object
identity, time, and spatial reference frame.

Native evidence uses method native, acquisition_step native_N0, and null tool-source fields. Put
usable numerical quantities in claim.value and units, basis, and uncertainty in claim.text.
Physical estimates based on familiar-object sizes are assumptions, not measurements. Return the
best-supported candidate without duplicating the same observation across frames."""

PLANNER = """Plan residual acquisition while preserving native requirements and observations. Retain all
requirements and add any relevant requirement omitted by the native state. Every requirement
targeted by supplementary acquisition, including additions during REPLAN, must appear in
unresolved_requirements.

A plan step may invoke one registered primitive operation or a composition of registered
primitives that you construct for the task. For each internal operation, declare its arguments,
input references, dependencies, and documented output fields. Declare the outputs exposed by the
composite and preserve a separate raw record for each internal operation.

Prefer plans with at most five steps. This is a recommendation, not a hard limit. If more than
five steps are needed, review the plan for redundant acquisitions, unnecessary intermediate
operations, or an unsuitable solution strategy. Revise the plan where appropriate and retain
additional steps when they are necessary.

Use only registered primitives and documented output fields. Reference V, evidence IDs, or
preceding operation outputs as inputs and declare dependencies. Measured arguments use {ref,
field}.

object_detection takes category descriptions, not instance IDs. reconstruct_geometry uses at
most 16 frames. localize_objects requires outputs from preceding object_detection and
reconstruct_geometry operations, with both dependencies declared. These operations may appear in
separate steps or within a composite step, provided that their dependency order is preserved.
inspect_frames is not a detector.

Detection boxes are 4D pixel bounds; localization exposes 3D centers at locations.0.center.
Reconstruction returns an artifact and camera matrices, not object positions, metric scale, or
gravity. Never invent output paths. A missed detection does not establish absence. Use targeted
frame inspection when sufficient.

On REPLAN, repair the diagnosed gap by changing the affected acquisition steps. Changing only
expected_output or repeating an unchanged failed plan is not a repair."""

PERCEIVER = """Interpret only the current acquisition, its input records, and source frames. Produce
observations for the target requirements, not the final answer. Cite raw tool-record IDs, not
step IDs. For a tool-extracted value, set tool_field to the actual output-relative path and
claim.value to that value. Direct visual claims use tool_field null and may use tool_record_id
null. Give numerical quantities explicit units and a short basis in claim.text.

Preserve object identity, time, coordinate frame, and scale; report unresolved requirements and
conflicts.

A failed tool is not evidence. Detection alone establishes neither unique identity nor absence;
first-appearance claims require checking preceding sampled frames. VGGT has unknown metric scale
and gravity, so metric conversion or a horizontal reference requires supporting evidence.
Approximate physical estimates must state the visible cue and assumed reference size."""

REASONER = """Reason only from active evidence. Each claim's support_ids must reference active evidence or
earlier supported claims. Track identity, time, coordinates, units, and conflicts. Return the
best-supported candidate and retain unresolved requirements or conflicts.

For arithmetic, provide an operator, traced operands, and result; semantic claims use
calculation null. Evidence operands reference claim.value, computed operands reference
calculation.result, and every operand appears in support_ids. Do not create a numeric
claim.value for a semantic conclusion solely to make it referenceable; cite the underlying
numerical evidence instead.

final_conclusion and candidate_answer must agree on the option or quantity. Put uncertainty in
the reasoning, not an answer range. Retain estimates supported by explicit evidence and
assumptions when exact calibration is unavailable."""

CHECK_COMMON = """Evaluate every named criterion independently: PASS requires support, FAIL a definite error, and
UNKNOWN insufficient support to decide. Identify specific targets. For FAIL or UNKNOWN, propose
a concrete supported correction when available; otherwise set action to null and revision to
empty.

REPERCEIVE repeats the existing operation, arguments, inputs, dependencies, and frame selection.
Changed acquisition requires REPLAN; REREASON changes reasoning only. Recovery target lists
contain IDs.

If a later check raises a specific concern about an earlier PASS, report upstream_concern with
stage, criterion, target, reason, and revision. The controller rechecks that criterion before
routing recovery; do not overturn a PASS on a hypothesis."""

PLAN_CHECK = """You receive the question, options, plan, tool interfaces, and reference metadata, but NO video,
observations, reasoning, or answer.

plan_completeness: Check whether the plan covers the entities, relations, and references needed
for the answer; could an omitted fact change the answer while planned facts remain fixed?

operation_feasibility: Check primitive operations, arguments, input references, output
capability, and dependency order both within composite steps and across plan steps.
Native-supported requirements need no reacquisition. inspect_frames can acquire spatial or
temporal observations, not only object presence. Judge what execution COULD supply; withheld
observations are not a planning failure. Metric quantities require a feasible calibration or
estimation procedure.

A supported planning failure proposes REPLAN; without a concrete supported revision, stop
unverified."""

PERCEPTION_CHECK = """Compare all active native and supplementary evidence with the cited frames and raw operation
records. Check source_validity and requirement_coverage separately. Preserve object identity,
time, coordinate frame, and scale.

source_validity: Check every active evidence record. Validate its frame references, operation
records, and cited output fields, then determine whether the source supports the observation.
Return PASS when support is established, FAIL for a definite inconsistency, and UNKNOWN when the
source is inaccessible or support is ambiguous. Include an individual check for every active
evidence ID in the observations field defined by the supplied schema.

requirement_coverage: Check whether each requirement is resolved by valid active evidence.
Return PASS for a resolved requirement. Return FAIL when the required evidence is missing or
contradicted. Return UNKNOWN when support or relevance remains uncertain. A record whose source
validity is UNKNOWN does not by itself establish either coverage or a definite coverage failure.
Consider any other active evidence for the same requirement.

Propose REPERCEIVE when repeating the affected acquisition with unchanged operations, arguments,
inputs, dependencies, and frame selection can repair the evidence. If the acquisition must
change, or a native error has no corresponding acquisition step, report a targeted planning
concern with a concrete proposed revision. The controller rechecks the implicated planning
criterion before selecting REPLAN. If no concrete supported revision is available, set action to
null and revision to empty."""

REASON_CHECK = """Check evidence_support, inference_validity, and answer_consistency along evidence -> cited
claims -> conclusion -> answer. Validate premises, semantic or geometric inferences, and
calculations. Map conclusions to option IDs and check units and requested rounding.

A plausible answer does not excuse unsupported premises. A specific evidence gap first raises a
perception concern; if the plan and evidence are valid, reasoning, calculation, mapping, or
formatting errors propose REREASON."""


BODIES = {
    "common": COMMON,
    "native": NATIVE,
    "planner": PLANNER,
    "perceiver": PERCEIVER,
    "reasoner": REASONER,
    "check_common": CHECK_COMMON,
    "plan_check": PLAN_CHECK,
    "perception_check": PERCEPTION_CHECK,
    "reason_check": REASON_CHECK,
}

MAIN_ROLES = ("native", "planner", "perceiver", "reasoner")
CHECK_ROLES = ("plan_check", "perception_check", "reason_check")
ROLES = MAIN_ROLES + CHECK_ROLES


def compose(role):
    """Compose exactly the prefixes specified by Appendix E."""
    if role in MAIN_ROLES:
        parts = (COMMON, BODIES[role])
    elif role in CHECK_ROLES:
        parts = (COMMON, CHECK_COMMON, BODIES[role])
    else:
        raise ValueError("Unknown role: {}".format(role))
    return "\n\n".join(parts)


def build_instructions(role):
    """Return prompt text and a portable public JSON schema, without a model call."""
    from .schemas import for_role
    return {"instructions": compose(role), "output_schema": deepcopy(for_role(role))}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Preview the paper prompts.")
    parser.add_argument("role", choices=ROLES)
    args = parser.parse_args()
    print(compose(args.role))
