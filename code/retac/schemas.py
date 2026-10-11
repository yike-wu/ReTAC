from copy import deepcopy

from .tools import OPERATION_NAMES


def obj(properties, required=None, extra=False):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else list(required),
            "additionalProperties": extra}


def array(items, minimum=None, maximum=None):
    result = {"type": "array", "items": items}
    if minimum is not None:
        result["minItems"] = minimum
    if maximum is not None:
        result["maxItems"] = maximum
    return result


STRING = {"type": "string"}
ID = {"type": "string", "minLength": 1}
IDS = array(ID)
NUMBER = {"type": "number"}
NULL_STRING = {"type": ["string", "null"]}
REF = obj({"ref": ID, "field": ID})
VECTOR = array(NUMBER, 3, 3)
POINTS = array(VECTOR)
FRAME_IDS = {**array({"type": "integer", "minimum": 1}, 1), "uniqueItems": True}


def referenced(schema):
    return {"anyOf": [schema, REF]}


LOCATION = obj({"center": VECTOR, "extent_10_90": VECTOR,
                "coordinate_frame": NULL_STRING, "object": ID,
                "object_id": ID, "instance_id": ID,
                "frame_id": {"type": "integer", "minimum": 1},
                "valid_points": {"type": "integer", "minimum": 0}},
               required=["center"], extra=True)
LOCATIONS = {"anyOf": [array(LOCATION), {"type": "object", "additionalProperties": LOCATION}]}
BACK_ANGLE = {"type": "number", "minimum": 0, "maximum": 180, "default": 135}

# These describe *planned* arguments. The tool runtime consumes resolved values.
OPERATION_ARGUMENTS = {
    "inspect_frames": obj({"frame_ids": FRAME_IDS}),
    "object_detection": obj({
        "objects": array(ID, 1, 8), "frame_ids": FRAME_IDS,
        "box_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.35},
        "text_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.25},
    }, required=["objects", "frame_ids"]),
    "reconstruct_geometry": obj({"frame_ids": {**FRAME_IDS, "maxItems": 16}}),
    "localize_objects": obj({"detection_step": ID, "geometry_step": ID}),
    "compute_distance": obj({"a": referenced(VECTOR), "b": referenced(VECTOR)}),
    "compute_closest_point_distance": obj({"object_a": referenced(LOCATION), "object_b": referenced(LOCATION)}),
    "project_to_bev": obj({"points": referenced(POINTS), "up": referenced(VECTOR)}),
    "observer_pose": obj({"observer": ID, "facing": ID, "locations": referenced(LOCATIONS), "up": referenced(VECTOR)}),
    "project_to_observer": obj({"points": referenced(POINTS), "observer_position": referenced(VECTOR),
                                "forward_vector": referenced(VECTOR), "right_vector": referenced(VECTOR),
                                "up_vector": referenced(VECTOR)}),
    "compute_rel_dir": obj({"target": referenced(VECTOR), "observer": referenced(VECTOR),
                            "forward": referenced(VECTOR), "right": referenced(VECTOR),
                            "up": referenced(VECTOR), "back_angle": BACK_ANGLE},
                           required=["target", "observer", "forward", "right", "up"]),
    "classify_dir": obj({"observer": {"anyOf": [VECTOR, REF, {"type": "null"}]},
                         "back_angle": BACK_ANGLE}, required=["observer"]),
    "cluster_detections": obj({"points": referenced(POINTS), "radius": {"type": "number", "exclusiveMinimum": 0}}),
    "associate_instance": obj({"locations": referenced(array({**LOCATION, "required": ["center", "object", "frame_id"]})),
                               "radius": {"type": "number", "exclusiveMinimum": 0}}),
}

OUTPUT_FIELDS = {
    "inspect_frames": ["frame_ids", "source"],
    "object_detection": ["frame_ids", "detections", "detections.*.frame_id", "detections.*.object",
                         "detections.*.box", "detections.*.score", "earliest_detection_frame"],
    "reconstruct_geometry": ["frame_ids", "artifact", "artifact_sha256", "coordinate_frame",
                             "camera_extrinsics", "camera_intrinsics", "metric_scale", "gravity"],
    "localize_objects": ["locations", "locations.*.center", "locations.*.extent_10_90",
                         "locations.*.valid_points", "locations.*.object", "locations.*.frame_id",
                         "locations.*.coordinate_frame", "centers", "coordinate_frame", "metric_scale", "gravity"],
    "compute_distance": ["distance", "units"],
    "compute_closest_point_distance": ["distance", "distance_type", "closest_point_a", "closest_point_b", "coordinate_frame"],
    "project_to_bev": ["points", "basis"],
    "observer_pose": ["observer_position", "forward_vector", "right_vector", "up_vector"],
    "project_to_observer": ["observer_coordinates", "forward_vector", "right_vector", "up_vector"],
    "compute_rel_dir": ["direction", "right_component", "forward_component", "turn_angle_deg"],
    # classify_dir returns a scalar string. '$' denotes the scalar output itself.
    "classify_dir": ["$"],
    "cluster_detections": ["clusters", "count", "radius"],
    "associate_instance": ["instances", "instances.*.instance_id", "instances.*.member_indices",
                           "instances.*.frame_ids", "instances.*.cluster_center", "instances.*.association_radius"],
}

REQ_FIELDS = {"id": ID, "description": STRING, "object_id": NULL_STRING,
              "object_ids": IDS, "temporal_reference": NULL_STRING, "spatial_reference": NULL_STRING}
REQUIREMENT = obj(REQ_FIELDS, required=["id"])
NATIVE_REQUIREMENT = obj({**REQ_FIELDS, "status": {"enum": ["SUPPORTED", "UNRESOLVED"]},
                          "evidence_ids": IDS, "reason": STRING},
                         required=["id", "status", "evidence_ids"])
SOURCE = obj({"video": NULL_STRING, "frame_ids": FRAME_IDS,
              "frame_range": array({"type": "integer", "minimum": 1}, 2, 2),
              "tool_record_id": NULL_STRING, "tool_field": NULL_STRING}, required=[])
EVIDENCE = obj({"id": ID, "requirement_id": ID, "object_id": NULL_STRING, "object_ids": IDS,
                "claim": {"anyOf": [STRING, obj({"text": STRING, "value": {}}, required=["text"])]},
                "sources": SOURCE, "method": ID, "acquisition_step": ID, "input_record_ids": IDS,
                "temporal_reference": NULL_STRING, "spatial_reference": NULL_STRING},
               required=["id", "requirement_id", "claim", "sources", "method", "acquisition_step", "input_record_ids"])
NATIVE = obj({"requirements": array(NATIVE_REQUIREMENT, 1), "evidence": array(EVIDENCE),
              "unresolved_requirements": IDS, "candidate_answer": NULL_STRING})


def primitive_schema(name, internal=False):
    fields = {"id": ID, "operation": {"const": name}, "arguments": OPERATION_ARGUMENTS[name],
              "input_references": IDS, "dependencies": IDS, "expected_output": STRING,
              "output_fields": array({"enum": OUTPUT_FIELDS[name]}, 1)}
    required = ["id", "operation", "arguments", "input_references", "dependencies", "expected_output"]
    if internal:
        required.append("output_fields")
    else:
        fields["target_requirement"] = array(ID, 1)
        required.append("target_requirement")
    return obj(fields, required=required)


PRIMITIVE = {"oneOf": [primitive_schema(name) for name in OPERATION_NAMES]}
INTERNAL_OPERATION = {"oneOf": [primitive_schema(name, internal=True) for name in OPERATION_NAMES]}
COMPOSITE = obj({"id": ID, "operation": {"const": "composite"}, "target_requirement": array(ID, 1),
                 "operations": array(INTERNAL_OPERATION, 1), "input_references": IDS,
                 "dependencies": IDS, "expected_output": STRING,
                 "exposed_outputs": {"type": "object", "minProperties": 1, "additionalProperties": REF}})
PLAN = obj({"requirements": array(REQUIREMENT, 1), "unresolved_requirements": IDS,
            "steps": array({"oneOf": [PRIMITIVE, COMPOSITE]})})
# Deliberately no maxItems on steps: five is a soft recommendation in the paper.
PERCEIVER = obj({"new_evidence": array(EVIDENCE), "acquisition_failures": array(STRING),
                 "reported_unresolved_requirements": IDS, "reported_conflicts": array(STRING)})
CALCULATION = obj({"operator": ID, "operands": array(REF, 2), "result": {} })
CLAIM = obj({"id": ID, "support_ids": array(ID, 1), "conclusion": STRING,
             "calculation": {"anyOf": [{"type": "null"}, CALCULATION]}})
REASONER = obj({"reasoning": array(CLAIM), "final_conclusion": NULL_STRING, "candidate_answer": NULL_STRING,
                "unresolved_requirements": IDS, "unresolved_conflicts": array(STRING)},
               required=["reasoning", "candidate_answer", "unresolved_requirements", "unresolved_conflicts"])

VERDICT = {"enum": ["PASS", "FAIL", "UNKNOWN"]}
CHECK = obj({"result": VERDICT, "target": IDS, "reason": STRING})
CRITERIA = {"planning": ("plan_completeness", "operation_feasibility"),
            "perception": ("source_validity", "requirement_coverage"),
            "reasoning": ("evidence_support", "inference_validity", "answer_consistency")}
PROPOSAL = obj({"action": {"enum": ["REPLAN", "REPERCEIVE", "REREASON", None]},
                "target": IDS, "diagnosis": STRING, "revision": STRING})
UPSTREAM_CONCERN = obj({"stage": {"enum": ["planning", "perception"]}, "criterion": ID,
                        "target": IDS, "reason": STRING, "revision": STRING})


def verification_schema(stage):
    fields = {"criteria": obj({name: CHECK for name in CRITERIA[stage]}),
              "proposal": PROPOSAL,
              "upstream_concern": {"anyOf": [{"type": "null"}, UPSTREAM_CONCERN]}}
    if stage == "perception":
        fields["observations"] = {"type": "object", "additionalProperties": CHECK}
    return obj(fields)


# Recorded stage status is separate from a model's verdict: unevaluated != UNKNOWN.
STAGE_STATUS = {"oneOf": [
    obj({"result": VERDICT, "origin": {"enum": ["fresh", "cached", "targeted_recheck"]}}),
    obj({"result": {"type": "null"}, "origin": {"const": "not_run"}}),
]}
GENERAL_PLANNING = {"oneOf": [
    obj({"decision": {"const": "RETURN_NATIVE"}, "rationale": STRING, "plan": {"type": "null"}}),
    obj({"decision": {"const": "SUPPLEMENT"}, "rationale": STRING,
         "plan": obj({"requirements": array(REQUIREMENT, 1), "steps": PLAN["properties"]["steps"]})}),
]}
GENERAL_REFLECTION = obj({"decision": {"enum": ["ACCEPT", "RETRY"]}, "feedback": STRING})


def for_role(role):
    registry = {"native": NATIVE, "planner": PLAN, "replan": PLAN,
                "perceiver": PERCEIVER, "reasoner": REASONER,
                "plan_check": verification_schema("planning"),
                "perception_check": verification_schema("perception"),
                "reason_check": verification_schema("reasoning"),
                "general_planning": GENERAL_PLANNING, "general_reflection": GENERAL_REFLECTION}
    if role not in registry:
        raise ValueError("Unknown role: " + role)
    return {"$schema": "http://json-schema.org/draft-07/schema#", **deepcopy(registry[role])}


def operation_interfaces():
    """Tool metadata for Planner/Verifier; contains no model or execution state."""
    return {name: {"arguments": deepcopy(OPERATION_ARGUMENTS[name]),
                   "output_fields": list(OUTPUT_FIELDS[name])} for name in OPERATION_NAMES}
