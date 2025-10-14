"""
python_parser.py

Description: Parsing py src files and extracting structural info (symbols) using the abstract syntax tree of python.
Extracted symbols are normalized in dics and they get stored in the db (symbols table)

"""

import ast
from parsers.generic import slice_by_lines

#extract the source code corresponding to a given ast node (function, class, method)
def get_source_segment(source: str, node: ast.AST) -> str:
    try:
        seg = ast.get_source_segment(source, node)
        if seg:
            return seg
    except Exception:
        pass
    #store line numbers
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    return slice_by_lines(source, lineno, end_lineno) or ""

#parse a python file's text into an ast
def parse_python_symbols(source: str):
     #yield dicts for classes, functions, methods with source content
    tree = ast.parse(source) #turns raw code to syntax tree
    symbols = [] #collect dicts describing each class/method/function

    #extract argument names
    class FuncSig(ast.NodeVisitor):
        #collect/get: args(x,y), (*args), (keyword only args), (**kwargs)
        def get(self, node):
            # format of args 
            def fmt(a): return a.arg if isinstance(a, ast.arg) else "_"
            # normal positional arguments
            pos = [fmt(a) for a in node.args.args]
            # *args
            if node.args.vararg: pos.append("*" + node.args.vararg.arg)
            # keyword only arguments
            kw = [fmt(a) for a in node.args.kwonlyargs]
            # **kwargs
            if node.args.kwarg: kw.append("**" + node.args.kwarg.arg)
            # building the string
            parts = []
            if pos: parts.append(", ".join(pos))
            if kw: parts.append(", ".join(kw))
            return f"({', '.join([p for p in parts if p])})"
        
    sig = FuncSig()# just call sig. after whn need to use the helper

     #when it sees a class/method/function
    class Visitor(ast.NodeVisitor):
        #triggered when met with a class
        def visit_ClassDef(self, node: ast.ClassDef): #in ast: ast.ClassDef
            doc = ast.get_docstring(node) #for getting the docstrings in classes
            symbols.append({
                "kind": "class",
                "name": node.name,
                "lineno": getattr(node, "lineno", None),
                "end_lineno": getattr(node, "end_lineno", None),
                "signature": None,
                "docstring": doc,
                "parent_name": None, #class name irself
                "source": get_source_segment(source, node),
            })
            # methods 
            # loops through the class body and gets methods
            for b in node.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc_m = ast.get_docstring(b) #for getting doc
                    symbols.append({
                        "kind": "method",
                        "name": b.name,
                        "lineno": getattr(b, "lineno", None),
                        "end_lineno": getattr(b, "end_lineno", None),
                        "signature": sig.get(b), #get argument names
                        "docstring": doc_m,
                        "parent_name": node.name, #class it belongs to
                        "source": get_source_segment(source, b), #exact method coode
                    })
            self.generic_visit(node)

        # goes through functions    
        def record_top_level_func(self, node): 
            doc = ast.get_docstring(node) #get docstrings of functions
            symbols.append({
                "kind": "function",
                "name": node.name,
                "lineno": getattr(node, "lineno", None),
                "end_lineno": getattr(node, "end_lineno", None),
                "signature": sig.get(node),
                "docstring": doc,
                "parent_name": None,
                "source": get_source_segment(source, node),
            })
        #work for synhcronous functions
        def visit_FunctionDef(self, node: ast.FunctionDef):
            self.record_top_level_func(node)
        #work for unsychronous functions
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self.record_top_level_func(node)

    Visitor().visit(tree)#runs through whole of raw code
    return symbols
