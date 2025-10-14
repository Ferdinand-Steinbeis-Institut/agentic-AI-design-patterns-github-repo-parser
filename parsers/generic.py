"""
generic.py 

Description: Helper functions that handle raw code or txt and convert them to symbol representations that fit into the DB schema

"""
#source: take the whole source code of a file as a string, lineno: the line number where a code block 
#starts (for classes and functions), end_lineno: the number where it ends 
def slice_by_lines(source: str, lineno: int, end_lineno: int) -> str:
    if not lineno or not end_lineno:
        return ""
    lines = source.splitlines()
    # abstract syntax tree follows 1-based line numering
    start = max(lineno - 1, 0)
    end = min(end_lineno, len(lines))
    return "\n".join(lines[start:end])

# single file "symbol" builder for configs/docs
def make_single_symbol(kind: str, name: str, source_text: str):
    return [{
        "kind": kind,
        "name": name,
        "lineno": None,
        "end_lineno": None,
        "signature": None,
        "docstring": None,
        "parent_name": None,
        "source": source_text or "",
    }]