"""
ipynb_parser.py 

Description: Helper function to handle .ipynb parsing in repositories and extracting its symbols

"""
import json

# notebook parser
def parse_ipynb_symbols(nb_text: str):
    try:
        notebooks = json.loads(nb_text)
    except Exception:
        return []
    out = []
    cells = notebooks.get("cells", [])
    for i, cell in enumerate(cells):
        ctype = cell.get("cell_type", "")
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        kind = "notebook_code" if ctype == "code" else "notebook_markdown"
        out.append({
            "kind": kind,
            "name": f"cell_{i}_{ctype}",
            "lineno": None,
            "end_lineno": None,
            "signature": None,
            "docstring": None,
            "parent_name": None,
            "source": src,
        })
    return out
