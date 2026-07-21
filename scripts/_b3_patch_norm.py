#!/usr/bin/env python3
"""B3: inject Norm Code nodes into classification-stage2-hierarchy-dev.

Does NOT modify classification-stage2-dev.
Does NOT change Load stub SQL or Fin empty path.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF_PATH = ROOT / "workflows" / "classification-stage2-hierarchy-dev.json"
NODES_DIR = ROOT / "scripts" / "hierarchy_nodes"

PRODUCT_NAME = "Norm — Normalize Product"
DICT_NAME = "Norm — Normalize Dict"
STICKY_NAME = "🔗 Norm — B3 (wire Dict later)"


def load_js(name: str) -> str:
    return (NODES_DIR / name).read_text(encoding="utf-8")


def main() -> None:
    wf = json.loads(WF_PATH.read_text(encoding="utf-8"))
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Remove prior Norm inject if re-run
    drop = {PRODUCT_NAME, DICT_NAME, STICKY_NAME}
    nodes[:] = [n for n in nodes if n.get("name") not in drop]

    product_code = load_js("norm_normalize_product.js")
    dict_code = load_js("norm_normalize_dict.js")

    product_node = {
        "parameters": {"jsCode": product_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, -1296],
        "id": str(uuid.uuid4()),
        "name": PRODUCT_NAME,
        "notes": "B3 Norm: product text + attrs; no SQL/LLM",
    }
    dict_node = {
        "parameters": {"jsCode": dict_code},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, -1100],
        "id": str(uuid.uuid4()),
        "name": DICT_NAME,
        "notes": "B3 Norm: categories_dict keys + dirty flags; unwired until Dir",
    }
    sticky = {
        "parameters": {
            "content": (
                "## Norm (B3)\n\n"
                "**Live:** Attach → Normalize Product → Limit\n\n"
                "**Dict:** Normalize Dict is on canvas but **not** "
                "in live In-path.\n"
                "Wiring in **B4 / Dir**: `Dir — Load Categories` → "
                "`Norm — Normalize Dict` → Dir Merge.\n\n"
                "No SQL writes. No LLM. Helpers: `norm_helpers_v1`.\n"
                "`is_device_sku_like` = heuristic flag only (not reject)."
            ),
            "height": 280,
            "width": 380,
            "color": 4,
        },
        "id": str(uuid.uuid4()),
        "name": STICKY_NAME,
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [320, -1560],
    }

    # Insert after Attach Run ID node for readability
    insert_at = next(
        (i for i, n in enumerate(nodes) if n.get("name") == "Load — Attach Run ID"),
        len(nodes),
    )
    nodes[insert_at + 1 : insert_at + 1] = [product_node, dict_node, sticky]

    # Rewire: Attach → Norm Product → Limit Batch
    connections["Load — Attach Run ID"] = {
        "main": [[{"node": PRODUCT_NAME, "type": "main", "index": 0}]]
    }
    connections[PRODUCT_NAME] = {
        "main": [[{"node": "Load — Limit Batch", "type": "main", "index": 0}]]
    }
    # Dict intentionally has no connections entry

    # Safety asserts
    load = next(n for n in nodes if n["name"] == "Load — Select Batch")
    assert "WHERE false" in load["parameters"]["query"], "Load stub must stay WHERE false"
    assert PRODUCT_NAME in {n["name"] for n in nodes}
    assert DICT_NAME in {n["name"] for n in nodes}
    assert connections["Load — Attach Run ID"]["main"][0][0]["node"] == PRODUCT_NAME
    assert connections[PRODUCT_NAME]["main"][0][0]["node"] == "Load — Limit Batch"
    assert DICT_NAME not in connections

    WF_PATH.write_text(
        json.dumps(wf, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Patched {WF_PATH}")
    print(f"  + {PRODUCT_NAME}")
    print(f"  + {DICT_NAME} (unwired)")
    print(f"  + {STICKY_NAME}")
    print("  wire: Attach → Norm Product → Limit Batch")


if __name__ == "__main__":
    main()
