"""Store an ONNX graph's weights as fp16 and compute in fp32.

Every large float32 initializer is replaced by a float16 one followed by a Cast back to float32. ONNX
Runtime folds those casts when it loads the model, so the file is half the size and the maths is the
fp32 maths with weights rounded once to fp16. That matters for two reasons a blanket fp16 conversion
(onnxconverter-common) gets wrong here:

  - CPU: ONNX Runtime's CPU provider has few native fp16 kernels, so a true fp16 graph is upcast around
    nearly every node and runs slower than fp32.
  - Mixed graphs: the Swin / ViT exports contain Equal / Where / Resize nodes that are built from
    float constants, and the converter leaves them with mismatched types (the session fails to load).

Small tensors (norm scales, biases, the front end's DFT and mel matrices) stay float32.
"""

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

FP16_MAX = 65504.0


def store_weights_fp16(model: onnx.ModelProto, min_elems: int = 4096, keep=lambda name: False) -> dict:
    """Rewrites `model` in place and returns {"converted": n, "kept": n, "max_abs_error": float}."""
    graph = model.graph
    casts = []
    kept = 0
    worst = 0.0
    new_inits = []
    for init in graph.initializer:
        count = int(np.prod(init.dims)) if init.dims else 1
        if init.data_type != TensorProto.FLOAT or count < min_elems or keep(init.name):
            new_inits.append(init)
            kept += 1
            continue
        arr = numpy_helper.to_array(init)
        peak = float(np.abs(arr).max())
        if peak > FP16_MAX:
            raise SystemExit(f"{init.name}: |max| {peak} does not fit in fp16")
        half = arr.astype(np.float16)
        worst = max(worst, float(np.abs(half.astype(np.float32) - arr).max()))
        half_name = init.name + "__fp16"
        new_inits.append(numpy_helper.from_array(half, half_name))
        casts.append(
            helper.make_node(
                "Cast", [half_name], [init.name], name=init.name + "__cast", to=TensorProto.FLOAT
            )
        )
    del graph.initializer[:]
    graph.initializer.extend(new_inits)
    # Cast nodes only read initializers, so they can lead the node list and keep it topologically sorted.
    nodes = list(graph.node)
    del graph.node[:]
    graph.node.extend(casts + nodes)
    return {"converted": len(casts), "kept": kept, "max_abs_error": worst}
