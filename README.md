# ReTAC: Residual Test-Time Agentic Computation for Video Spatial Reasoning
## Release status

This is the official pre-release repository for ReTAC. **The full research implementation will be released upon acceptance of the paper.**

The current release contains spatial tools, published prompts, portable output schemas, and a controller interface skeleton.

| Component | Public now |
| --- | --- |
| [tools.py](code/retac/tools.py) | 13 spatial primitives, including optional GroundingDINO/VGGT adapters |
| [prompts.py](code/retac/prompts.py) | Role instructions, shared-prefix composition |
| [schemas.py](code/retac/schemas.py) | State and output structures |
| [controller.py](code/retac/controller.py) | Method signatures and responsibilities  |



See also the [code directory and usage guide](code/README.md).

## Using the public modules

Use Python 3.9 or newer. Run the following commands from the repository root:

```bash
cd code
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```



### Prompts and schemas

`prompts.py` contains the nine main-method prompt blocks, including two shared prefixes. Native, Planner, Perceiver, and Reasoner use `COMMON`; the three verification roles use `COMMON` followed by `CHECK_COMMON`.

```python
from jsonschema import Draft7Validator
from retac.prompts import build_instructions
from retac.schemas import for_role, operation_interfaces

planner = build_instructions("planner")
print(planner["instructions"])
Draft7Validator.check_schema(planner["output_schema"])
interfaces = operation_interfaces()

```




### Spatial tools

```python
from retac.tools import ToolRuntime

tools = ToolRuntime()
result = tools.execute("compute_distance", {
    "a": [0.0, 0.0, 0.0],
    "b": [3.0, 4.0, 0.0],
})
print(result)  # {'distance': 5.0, 'units': 'input coordinate units'}
```

| Group | Operations |
| --- | --- |
| Acquisition and localization | `inspect_frames`, `object_detection`, `reconstruct_geometry`, `localize_objects` |
| Distance | `compute_distance`, `compute_closest_point_distance` |
| Projection and direction | `project_to_bev`, `observer_pose`, `project_to_observer`, `compute_rel_dir`, `classify_dir` |
| Grouping and association | `cluster_detections`, `associate_instance` |

Detection and reconstruction additionally require PyTorch, Transformers, Pillow, the [VGGT package](https://github.com/facebookresearch/vggt), and local model weights.



## Code organization

The public Python package and its dependencies are in `code/`. The project homepage remains at the repository root.



```text
requirements.txt    Dependencies for public numerical/schema modules
retac/
  __init__.py
  tools.py          Spatial tools
  prompts.py        Prompts
  schemas.py        State, plan, evidence, and verification structures
  controller.py     Interface skeleton

Full-release components (not included in this pre-release):
  controller internals  Native routing, residual execution, evidence bookkeeping,
                        staged verification, selective recovery
  client.py             MLLM requests, multimodal input packaging
  metrics.py            Benchmark scoring and aggregation
  run.py                Dataset loading, result serialization
  configs/              Model, dataset, tool, and experiment configurations
  tests/                Method test
```
