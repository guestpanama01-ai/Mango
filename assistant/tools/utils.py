"""Herramientas de utilidad: calculadora y hora actual."""
from __future__ import annotations

import ast
import operator
from datetime import datetime

from assistant.tools.registry import tool

# Operadores permitidos para la calculadora (evita ejecuciones maliciosas)
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_node(node: ast.AST) -> float:
    """Evalúa un nodo del AST de forma segura."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Expresión matemática no permitida")

@tool(description="Realiza cálculos matemáticos precisos. Usa esto en lugar de calcular mentalmente.")
def calculator(expression: str) -> str:
    """Calcula una expresión matemática (ej: '2 + 2 * 3', '10 / 2')."""
    try:
        # Parseamos la expresión de forma segura
        tree = ast.parse(expression, mode='eval')
        result = _eval_node(tree.body)
        
        # Formatear para quitar el .0 si es un entero
        if isinstance(result, float) and result.is_integer():
            result = int(result)
            
        return f"El resultado de '{expression}' es: {result}"
    except Exception as e:
        return f"Error en el cálculo: No pude calcular '{expression}'."

@tool(description="Devuelve la fecha y hora actual del sistema.")
def get_current_time() -> str:
    """Obtiene la fecha y hora actual formateada."""
    now = datetime.now()
    return now.strftime("La fecha y hora actual es: %A, %d de %B de %Y, a las %H:%M:%S")