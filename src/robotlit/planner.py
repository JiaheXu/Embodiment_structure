"""Visible local templates for the five accepted query families."""
import re

from .contracts import Predicate, QueryPlan


def plan_query(request, context=None):
    if request.plan:
        return request.plan
    q = request.question or ""
    lower = q.casefold()
    requirements, resolved = [], {}

    def require(facet, value, explanation):
        requirements.append(Predicate(id=f"r{len(requirements) + 1}", facet=facet, operator="eq", value=value, explanation=explanation))

    if re.search(r"\bwam\b|world[- ]action|世界.*动作", lower):
        resolved["WAM"] = "world-action model; joint future-world and robot-action modeling"
        require("model.world_action_joint", True, "Both world and robot action modeling in this configuration")
    if "object-centric" in lower or "object centric" in lower or "对象中心" in lower or "物体中心" in lower:
        require("representation.object_centric", True, "Explicit object-level entities participate in the method")
    if "bimanual" in lower or "双臂" in lower or "双手" in lower:
        require("robot.bimanual_control", True, "Both arms are controlled")
    if "dexterous" in lower or "灵巧" in lower:
        if any(p.facet == "robot.bimanual_control" for p in requirements):
            for side in ("left", "right"):
                require(f"robot.{side}_hand_type", "dexterous_hand", "Both hands must be dexterous")
            resolved["dexterous"] = "both left and right dexterous hands; parallel grippers do not qualify"
    if re.search(r"\bvla\b|vision[- ]language[- ]action", lower):
        resolved["VLA"] = "vision and language condition an action-producing robot system"
        for key in ("vision_conditioned", "language_conditioned", "outputs_robot_actions"):
            require(f"policy.{key}", True, resolved["VLA"])
    if re.search(r"multi[- ]?(view|camera)|multiple.*(view|camera)|多视角|多相机", lower):
        require("policy.multiview_input", True, "Multiple simultaneous views enter the policy")
        resolved["multi-view"] = "multiple simultaneous camera views used by the policy"
    if any(word in lower for word in ("without", "no supplied", "uncalibrated", "无需", "无准确")) and any(word in lower for word in ("pose", "extrinsic", "calibr", "位姿", "标定")):
        require("camera.extrinsics_supplied_infer", False, "Requires evidence for no externally supplied extrinsics at inference")
        resolved["without accurate camera pose"] = "no externally supplied extrinsics at inference; training/internal geometry remain separate"
    expansions = [q]
    if "WAM" in resolved:
        expansions.append("world action model future prediction robot actions")
    if "multi-view" in resolved:
        expansions.append("multi view wrist external RGB camera policy calibration extrinsics")
    if "VLA" in resolved:
        expansions.append("bimanual dexterous vision language action robot manipulation")
    return QueryPlan(hard_requirements=requirements, resolved_terms=resolved, search_queries=expansions[:4],
                     evidence_targets=["method", "policy inputs", "training and inference setup"], mode=request.mode,
                     project_id=request.project_id)
