import hashlib
import inspect
import json
import math
import tempfile
from pathlib import Path

import numpy as np


OPERATION_NAMES = (
    "inspect_frames", "object_detection", "reconstruct_geometry", "localize_objects",
    "compute_distance", "compute_closest_point_distance", "project_to_bev",
    "observer_pose", "project_to_observer", "compute_rel_dir", "classify_dir",
    "cluster_detections", "associate_instance",
)


def _vector(value):
    out = np.asarray(value, dtype=float)
    if out.shape != (3,) or not np.isfinite(out).all():
        raise ValueError("Expected a finite 3D vector")
    return out


def _points(value):
    out = np.asarray(value, dtype=float)
    if out.size == 0:
        return np.empty((0, 3))
    if out.ndim != 2 or out.shape[1] != 3 or not np.isfinite(out).all():
        raise ValueError("Expected finite 3D points")
    return out


def _unit(value):
    out = _vector(value)
    norm = np.linalg.norm(out)
    if norm <= 1e-12:
        raise ValueError("A direction vector must be nonzero")
    return out / norm


def _shared_frame(*records):
    frames = {r.get("coordinate_frame") for r in records if r.get("coordinate_frame")}
    if len(frames) > 1:
        raise ValueError("Inputs use different coordinate frames")
    return next(iter(frames), None)


def _frame_ids(frames, frame_ids, maximum=None):
    ids = list(frame_ids)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Frame IDs must be nonempty and unique")
    if any(type(i) is not int or not 1 <= i <= len(frames) for i in ids):
        raise ValueError("Frame IDs are one-based sampled-video positions")
    if maximum is not None and len(ids) > maximum:
        raise ValueError("Too many frames for this operation")
    return ids


def inspect_frames(frames, frame_ids):
    """Return source references; the caller supplies these images to Perceiver."""
    return {"frame_ids": _frame_ids(frames, frame_ids), "source": "V"}


def compute_distance(a, b):
    """Euclidean distance; the caller must establish common coordinates/units."""
    return {"distance": float(np.linalg.norm(_vector(a) - _vector(b))),
            "units": "input coordinate units"}


def compute_closest_point_distance(object_a, object_b):
    """AABB distance using center +/- extent_10_90 / 2; otherwise center distance.

    The public serialization uses the median center and percentile span to form
    symmetric axis-aligned bounds. This approximation is not surface geometry.
    """
    frame = _shared_frame(object_a, object_b)
    a, b = _vector(object_a["center"]), _vector(object_b["center"])
    if "extent_10_90" in object_a and "extent_10_90" in object_b:
        ea, eb = _vector(object_a["extent_10_90"]), _vector(object_b["extent_10_90"])
        if (ea < 0).any() or (eb < 0).any():
            raise ValueError("Object extents cannot be negative")
        alo, ahi, blo, bhi = a - ea / 2, a + ea / 2, b - eb / 2, b + eb / 2
        overlap = (np.maximum(alo, blo) + np.minimum(ahi, bhi)) / 2
        pa = np.where(ahi < blo, ahi, np.where(bhi < alo, alo, overlap))
        pb = np.where(ahi < blo, blo, np.where(bhi < alo, bhi, overlap))
        kind = "axis_aligned_bounds"
    else:
        pa, pb, kind = a, b, "center_approximation"
    return {"distance": float(np.linalg.norm(pa - pb)), "distance_type": kind,
            "closest_point_a": pa.tolist(), "closest_point_b": pb.tolist(),
            "coordinate_frame": frame}


def project_to_bev(points, up):
    """Project onto the plane normal to up; this does not infer gravity."""
    up = _unit(up)
    seed = np.eye(3)[np.argmin(abs(up))]
    right = _unit(np.cross(seed, up))
    forward = np.cross(up, right)
    return {"points": (_points(points) @ np.stack([right, forward], axis=1)).tolist(),
            "basis": [right.tolist(), forward.tolist()]}


def observer_pose(observer, facing, locations, up):
    """Resolve exact object/instance IDs, then construct supplied-reference axes.

    locations may be a mapping keyed by IDs or a list containing object_id,
    instance_id, or object. Ambiguous matches are rejected, never selected silently.
    """
    def lookup(name):
        if isinstance(locations, dict):
            return locations[name]
        found = [r for r in locations if name in
                 (r.get("object_id"), r.get("instance_id"), r.get("object"))]
        if len(found) != 1:
            raise ValueError("Observer/facing reference must identify one location")
        return found[0]

    origin, target = lookup(observer), lookup(facing)
    _shared_frame(origin, target)
    position = _vector(origin["center"])
    forward = _unit(_vector(target["center"]) - position)
    up = _unit(up)
    right = _unit(np.cross(forward, up))
    return {"observer_position": position.tolist(), "forward_vector": forward.tolist(),
            "right_vector": right.tolist(), "up_vector": up.tolist()}


def project_to_observer(points, observer_position, forward_vector, right_vector, up_vector):
    """Apply the dot products in Appendix C.3 without changing supplied axes."""
    right, forward, up = map(_vector, (right_vector, forward_vector, up_vector))
    if any(np.linalg.norm(v) <= 1e-12 for v in (right, forward, up)):
        raise ValueError("Observer basis vectors must be nonzero")
    relative = _points(points) - _vector(observer_position)
    return {"observer_coordinates": (relative @ np.stack([right, forward, up], axis=1)).tolist(),
            "right_vector": right.tolist(), "forward_vector": forward.tolist(),
            "up_vector": up.tolist()}


def _direction(x, y, z, back_angle, length=None):
    if not math.isfinite(back_angle) or not 0 <= back_angle <= 180:
        raise ValueError("back_angle must lie in [0, 180] degrees")
    length = math.sqrt(x*x + y*y + z*z) if length is None else length
    if length <= 1e-12:
        return "unknown", None
    theta = math.degrees(math.acos(float(np.clip(y / length, -1, 1))))
    if theta >= back_angle or math.isclose(theta, back_angle, abs_tol=1e-10):
        return "back", theta
    # The paper has no forward class. Public tie convention: x == 0 -> right.
    return ("left" if x < 0 else "right"), theta


def compute_rel_dir(target, observer, forward, right, up, back_angle=135):
    """Use the true angle to forward, including when supplied up is not orthogonal."""
    f, r, u = map(_unit, (forward, right, up))
    delta = _vector(target) - _vector(observer)
    x, y, z = float(delta @ r), float(delta @ f), float(delta @ u)
    direction, theta = _direction(x, y, z, back_angle, length=float(np.linalg.norm(delta)))
    return {"direction": direction, "right_component": x, "forward_component": y,
            "turn_angle_deg": theta}


def classify_dir(observer, back_angle=135):
    """Classify orthonormal-frame [right, forward, up]; None means unsupported.

    For nonorthogonal axes, use compute_rel_dir with the original 3D vectors so
    the true angle to the forward direction is retained.
    """
    if observer is None:
        return "unknown"
    return _direction(*_vector(observer), back_angle)[0]


def cluster_detections(points, radius):
    """Radius-graph connected components, with zero-based member indices."""
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius must be positive and finite")
    pts = _points(points)
    remaining, clusters = set(range(len(pts))), []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        group, pending = [start], [start]
        while pending:
            i = pending.pop()
            neighbors = sorted(j for j in remaining if np.linalg.norm(pts[i] - pts[j]) <= radius)
            remaining.difference_update(neighbors)
            group.extend(neighbors)
            pending.extend(neighbors)
        clusters.append(sorted(group))
    return {"clusters": clusters, "count": len(clusters), "radius": radius}


def associate_instance(locations, radius):
    """Group same-category locations; this is a geometric cue, not identity proof."""
    _shared_frame(*locations)
    # Validate radius even for an empty input.
    cluster_detections([], radius)
    categories = {}
    for i, record in enumerate(locations):
        categories.setdefault(record["object"], []).append(i)
    instances = []
    for indices in categories.values():
        groups = cluster_detections([locations[i]["center"] for i in indices], radius)
        for group in groups["clusters"]:
            members = [indices[i] for i in group]
            instances.append({"instance_id": "instance_{}".format(len(instances)),
                              "member_indices": members,
                              "frame_ids": sorted({locations[i]["frame_id"] for i in members}),
                              "cluster_center": np.mean([locations[i]["center"] for i in members], axis=0).tolist(),
                              "association_radius": radius})
    return {"instances": instances}


def localize_objects(detection_step, geometry_step):
    """Consume resolved detection/geometry outputs using shared sampled frames."""
    geometry = geometry_step
    artifact = Path(geometry["artifact"])
    if geometry.get("artifact_sha256") and hashlib.sha256(artifact.read_bytes()).hexdigest() != geometry["artifact_sha256"]:
        raise ValueError("Geometry artifact checksum mismatch")
    with np.load(artifact, allow_pickle=False) as data:
        ids = data["frame_ids"].tolist()
        locations = []
        for detection in detection_step["detections"]:
            if detection["frame_id"] not in ids:
                continue
            i = ids.index(detection["frame_id"])
            points, confidence = data["world_points"][i], data["world_points_conf"][i]
            h, w = points.shape[:2]
            ow, oh = data["original_sizes"][i]
            # VGGT pad preprocessing: nearest multiple of 14, then symmetric pad.
            ratio = max(h, w) / max(ow, oh)
            nw, nh = round(ow * ratio / 14) * 14, round(oh * ratio / 14) * 14
            if nw <= 0 or nh <= 0:
                raise ValueError("Degenerate image dimensions after preprocessing")
            ox, oy = (w - nw) // 2, (h - nh) // 2
            x1, y1, x2, y2 = detection["box"]
            x1, x2 = np.clip([int(x1*nw/ow+ox), int(x2*nw/ow+ox)], 0, w)
            y1, y2 = np.clip([int(y1*nh/oh+oy), int(y2*nh/oh+oy)], 0, h)
            if x2 <= x1 or y2 <= y1:
                continue
            ps, cs = points[y1:y2, x1:x2].reshape(-1, 3), confidence[y1:y2, x1:x2].reshape(-1)
            good = np.isfinite(ps).all(axis=1) & np.isfinite(cs)
            if not good.any():
                continue
            good &= cs >= np.median(cs[good])
            ps = ps[good]
            if len(ps) < 10:
                continue
            locations.append({**detection, "center": np.median(ps, axis=0).tolist(),
                              "extent_10_90": (np.percentile(ps, 90, axis=0) - np.percentile(ps, 10, axis=0)).tolist(),
                              "valid_points": len(ps), "coordinate_frame": geometry["coordinate_frame"]})
    return {"locations": locations, "centers": [r["center"] for r in locations],
            "coordinate_frame": geometry["coordinate_frame"],
            "metric_scale": "unknown", "gravity": "unknown"}


class ToolRuntime:
    """Execute individual primitives; composite scheduling belongs to the controller.

    config may provide detector_path, vggt_path, and tool_device. Weights and VGGT
    source must be installed separately. No weights are downloaded automatically.
    """

    def __init__(self, config=None):
        self.config = dict(config or {})
        self.detector = self.vggt = None

    def object_detection(self, frames, objects, frame_ids, box_threshold=0.35, text_threshold=0.25):
        ids = _frame_ids(frames, frame_ids)
        if not 1 <= len(objects) <= 8 or any(not isinstance(o, str) or not o.strip() for o in objects):
            raise ValueError("Provide one to eight object descriptions")
        if any(not math.isfinite(t) or not 0 <= t <= 1 for t in (box_threshold, text_threshold)):
            raise ValueError("Detection thresholds must lie in [0, 1]")
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        if self.detector is None:
            model_path = self.config["detector_path"]
            processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
            model = AutoModelForZeroShotObjectDetection.from_pretrained(model_path, local_files_only=True)
            self.detector = processor, model.to(self.config.get("tool_device", "cpu")).eval()
        processor, model = self.detector
        signature = inspect.signature(processor.post_process_grounded_object_detection)
        detections = []
        for fid in ids:
            for obj in objects:
                inputs = processor(images=frames[fid-1], text=obj.lower().rstrip(".")+".", return_tensors="pt")
                inputs = inputs.to(self.config.get("tool_device", "cpu"))
                with torch.inference_mode():
                    prediction = model(**inputs)
                kwargs = {"target_sizes": [frames[fid-1].size[::-1]], "text_threshold": text_threshold}
                kwargs["box_threshold" if "box_threshold" in signature.parameters else "threshold"] = box_threshold
                result = processor.post_process_grounded_object_detection(prediction, inputs.input_ids, **kwargs)[0]
                for box, score in zip(result["boxes"], result["scores"]):
                    detections.append({"frame_id": fid, "object": obj,
                                       "box": box.detach().cpu().tolist(), "score": float(score)})
        return {"frame_ids": ids, "detections": detections,
                "earliest_detection_frame": min((d["frame_id"] for d in detections), default=None)}

    def reconstruct_geometry(self, frames, frame_ids, artifact_dir, record_id):
        ids = _frame_ids(frames, frame_ids, maximum=16)
        if not record_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in record_id):
            raise ValueError("record_id must be a filename-safe identifier")
        import torch
        from contextlib import nullcontext
        from vggt.models.vggt import VGGT
        from vggt.utils.load_fn import load_and_preprocess_images
        from vggt.utils.pose_enc import pose_encoding_to_extri_intri
        device = self.config.get("tool_device", "cuda")
        if self.vggt is None:
            root = Path(self.config["vggt_path"])
            if (root / "model.safetensors").exists():
                self.vggt = VGGT.from_pretrained(str(root), local_files_only=True)
            else:
                config = json.loads((root / "config.json").read_text()) if (root / "config.json").exists() else {}
                self.vggt = VGGT(**config)
                self.vggt.load_state_dict(torch.load(root / "model.pt", map_location="cpu", weights_only=True))
            self.vggt = self.vggt.to(device).eval()
        with tempfile.TemporaryDirectory(prefix="retac_vggt_") as temporary:
            paths = []
            for fid in ids:
                path = Path(temporary) / (str(fid) + ".png")
                frames[fid-1].save(path)
                paths.append(str(path))
            images = load_and_preprocess_images(paths, mode="pad").to(device)
            amp = torch.autocast("cuda", dtype=torch.bfloat16) if str(device).startswith("cuda") else nullcontext()
            with torch.inference_mode(), amp:
                prediction = self.vggt(images)
                extrinsics, intrinsics = pose_encoding_to_extri_intri(prediction["pose_enc"], images.shape[-2:])
            arrays = {key: prediction[key][0].float().cpu().numpy() for key in ("world_points", "world_points_conf")}
            arrays.update(camera_extrinsics=extrinsics[0].float().cpu().numpy(),
                          camera_intrinsics=intrinsics[0].float().cpu().numpy(),
                          frame_ids=np.array(ids), original_sizes=np.array([frames[i-1].size for i in ids]))
        destination = Path(artifact_dir)
        destination.mkdir(parents=True, exist_ok=True)
        artifact = destination / (record_id + "_geometry.npz")
        if artifact.exists():
            raise FileExistsError("Choose a new record_id; raw geometry records are immutable")
        np.savez_compressed(artifact, **arrays)
        return {"frame_ids": ids, "artifact": str(artifact),
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "coordinate_frame": record_id, "metric_scale": "unknown", "gravity": "unknown",
                "camera_extrinsics": arrays["camera_extrinsics"].tolist(),
                "camera_intrinsics": arrays["camera_intrinsics"].tolist()}

    def execute(self, operation, arguments, *, frames=None, artifact_dir=None, record_id=None):
        """Execute one primitive with resolved inputs, never a full agentic plan.

        Each localize_objects argument is a resolved operation-output dictionary.
        Resolving {ref, field}, retaining raw records, and composite execution are
        responsibilities of the unreleased orchestration layer.
        """
        if operation not in OPERATION_NAMES:
            raise ValueError("Unregistered primitive: " + operation)
        if operation == "inspect_frames":
            return inspect_frames(frames, **arguments)
        if operation == "object_detection":
            return self.object_detection(frames, **arguments)
        if operation == "reconstruct_geometry":
            if artifact_dir is None or record_id is None:
                raise ValueError("Reconstruction requires artifact_dir and record_id")
            return self.reconstruct_geometry(frames, artifact_dir=artifact_dir, record_id=record_id, **arguments)
        return globals()[operation](**arguments)
