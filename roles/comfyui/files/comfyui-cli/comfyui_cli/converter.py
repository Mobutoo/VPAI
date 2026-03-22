"""Convert ComfyUI UI-format workflows to API-format for execution.

UI format: { "nodes": [...], "links": [...], "groups": [...] }
  - Each node has: id, type, widgets_values (positional), inputs (link slots)
  - Links: [link_id, origin_node_id, origin_slot, target_node_id, target_slot, type]

API format: { "node_id": { "class_type": "...", "inputs": { named_key: value } } }
  - Widget values mapped to named inputs via /object_info metadata
  - Links resolved to ["source_node_id_str", output_index]
"""
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def is_api_format(workflow: Dict) -> bool:
    """Detect if workflow is already in API format."""
    if "nodes" in workflow and "links" in workflow:
        return False
    # API format: top-level keys are node IDs mapping to dicts with class_type
    for key, val in workflow.items():
        if isinstance(val, dict) and "class_type" in val:
            return True
    return False


def ui_to_api(workflow: Dict, object_info: Dict) -> Dict[str, Any]:
    """Convert UI-format workflow to API-format.

    Args:
        workflow: UI-format workflow JSON (has "nodes" and "links" keys)
        object_info: Response from GET /object_info (node class metadata)

    Returns:
        API-format workflow dict
    """
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    # Build link lookup: link_id -> (origin_node_id, origin_slot_index)
    link_map = {}
    for link in links:
        # link = [link_id, origin_node_id, origin_slot, target_node_id, target_slot, type_name]
        if len(link) >= 4:
            link_id = link[0]
            origin_node_id = link[1]
            origin_slot = link[2]
            link_map[link_id] = (str(origin_node_id), origin_slot)

    api_workflow = {}

    for node in nodes:
        node_id = str(node["id"])
        class_type = node.get("type", "")

        # Skip reroute and other utility nodes
        if class_type in ("Reroute", "Note", "PrimitiveNode"):
            continue

        # Get input spec from object_info
        node_info = object_info.get(class_type, {})
        required_inputs = node_info.get("input", {}).get("required", {})
        optional_inputs = node_info.get("input", {}).get("optional", {})

        # Merge required + optional input specs (preserving order)
        all_input_specs = {}
        all_input_specs.update(required_inputs)
        all_input_specs.update(optional_inputs)

        # Build set of input names that are satisfied by links (not widgets)
        node_inputs = node.get("inputs", [])
        linked_input_names = {
            inp.get("name") for inp in node_inputs if inp.get("link") is not None
        }

        # Separate widget inputs (non-link) from link inputs
        widget_input_names = []
        for input_name, input_spec in all_input_specs.items():
            # Skip inputs that are connected via links — they are NOT widget values
            if input_name in linked_input_names:
                continue
            # Widget inputs have types like "INT", "FLOAT", "STRING", or combo lists
            if isinstance(input_spec, list) and len(input_spec) > 0:
                input_type = input_spec[0]
                if isinstance(input_type, str) and input_type.isupper():
                    # Primitive type → widget value
                    widget_input_names.append(input_name)
                elif isinstance(input_type, list):
                    # Combo/enum → widget value
                    widget_input_names.append(input_name)

        # Map widgets_values to named inputs
        widgets_values = node.get("widgets_values", [])
        inputs = {}

        widget_idx = 0
        for input_name in widget_input_names:
            if widget_idx < len(widgets_values):
                inputs[input_name] = widgets_values[widget_idx]
                widget_idx += 1

        # Map link connections from node.inputs
        for node_input in node_inputs:
            input_name = node_input.get("name", "")
            link_id = node_input.get("link")
            if link_id is not None and link_id in link_map:
                origin_node_id, origin_slot = link_map[link_id]
                inputs[input_name] = [origin_node_id, origin_slot]

        api_workflow[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
        }

        # Preserve _meta if present
        if "title" in node:
            api_workflow[node_id]["_meta"] = {"title": node["title"]}

    return api_workflow
