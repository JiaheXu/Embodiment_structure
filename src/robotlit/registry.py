"""Versioned, closed vocabulary. Scientific fields never accept arbitrary paths."""

FACETS = {key: "bool" for key in [
    "model.world_action_joint", "model.future_world_prediction", "model.robot_action_prediction",
    "representation.object_centric", "robot.bimanual_control", "policy.vision_conditioned",
    "policy.language_conditioned", "policy.outputs_robot_actions", "policy.multiview_input",
    "camera.extrinsics_supplied_train", "camera.extrinsics_supplied_infer",
    "camera.extrinsics_estimated_infer", "camera.registered_3d_required_train",
    "camera.registered_3d_required_infer", "camera.intrinsics_supplied_infer",
    "camera.depth_required_infer", "camera.calibration_noise_tested", "evaluation.real_robot",
]}
FACETS.update({"representation.object_types": "strings", "camera.modalities": "strings",
               "camera.placements": "strings", "policy.view_count_min": "int",
               "camera.calibration_test_details": "object",
               "robot.left_hand_type": "hand", "robot.right_hand_type": "hand"})

RECORDS = {
    "input_stream": {"phase": "phase", "modality": "str", "semantic_type": "str", "placement": "str",
                     "required": "bool", "history_frames": "int", "width": "int", "height": "int",
                     "port_name": "str", "dtype": "str", "axes": "strings", "layout": "str",
                     "frame": "str", "representation_level": "str", "upstream_io_ids": "strings"},
    "output_stream": {"phase": "phase", "action_space": "str", "convention": "str", "frame": "str",
                      "unit": "str", "prediction_horizon": "int", "actions_per_inference": "int",
                      "components": "strings", "rotation_representation": "str", "rotation_order": "str",
                      "port_name": "str", "dimension": "int", "representation_level": "str"},
    "method_detail": {"representation_role": "str", "fusion_stage": "str", "learning_paradigm": "str",
                      "adaptation_type": "str", "controller_dependency": "str", "phase": "phase",
                      "training_total": "number", "count_unit": "str", "count_scope": "str",
                      "domain": "str", "latency": "number", "hardware": "str", "timing_boundary": "str",
                      "memory": "number", "failure_condition": "str", "observed_failure": "str",
                      "proposed_cause": "str", "view_count_evaluated": "int"},
    "dataset_use": {"dataset.name": "str", "dataset.version": "str", "role": "str", "split": "str",
                    "episode_count": "int", "demo_count": "int", "count_scope": "str", "domain": "str",
                    "annotation_types": "strings", "phase": "phase", "mixture_weight": "number"},
    "reported_result": {"metric_name": "str", "normalized_value": "number", "unit": "str",
                        "aggregation": "str", "trial_count": "int", "success_count": "int", "seed_count": "int",
                        "raw_value": "number", "raw_scale": "str", "uncertainty_kind": "str",
                        "measurement_origin": "str", "checkpoint": "str", "metric_definition": "str",
                        "protocol.benchmark": "str", "protocol.version": "str", "protocol.task": "str",
                        "protocol.tasks": "strings", "protocol.robot": "str", "protocol.split": "str",
                        "protocol.success_definition": "str", "protocol.execution": "str"},
    "artifact_mention": {"kind": "str", "availability_state": "availability", "license_statement": "str",
                         "url": "str", "revision": "str", "observation_date": "str"},
}


def validate_value(kind, value):
    valid = {"bool": lambda v: type(v) is bool, "int": lambda v: type(v) is int,
             "number": lambda v: type(v) in (int, float) and __import__("math").isfinite(v),
             "str": lambda v: isinstance(v, str), "strings": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
             "object": lambda v: isinstance(v, dict),
             "hand": lambda v: v in ("parallel_gripper", "dexterous_hand", "other"),
             "phase": lambda v: v in ("pretrain", "train", "finetune", "inference", "evaluation"),
             "availability": lambda v: v in ("reported_available", "reported_planned", "reported_unavailable", "unknown")}
    if not valid[kind](value):
        raise ValueError(f"Expected {kind}, got {value!r}")


def validate_filter(kind, operator, value):
    allowed = {"bool": {"eq"}, "int": {"eq", "gte", "lte", "in"},
               "number": {"eq", "gte", "lte", "in"}, "strings": {"eq", "contains"},
               "object": {"eq"}}.get(kind, {"eq", "in"})
    if operator not in allowed:
        raise ValueError(f"Operator {operator} is invalid for {kind}")
    if operator == "in":
        if not isinstance(value, list) or not value:
            raise ValueError("in requires a nonempty array")
        for member in value:
            validate_value(kind, member)
    else:
        validate_value("str" if kind == "strings" and operator == "contains" else kind, value)
