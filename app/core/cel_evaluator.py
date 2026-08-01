"""Small deterministic CEL-compatible evaluator for EiraOS constraints.

This is intentionally a constrained CEL subset.  It supports the operators
used by EiraOS policy documents while rejecting Python execution primitives,
attribute introspection, comprehensions, lambdas and arbitrary function calls.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any


class CELError(ValueError):
    pass


class CELSyntaxError(CELError):
    pass


class CELEvaluationError(CELError):
    pass


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[Tt ].*)?$")


def _translate_cel(expression: str) -> str:
    translated = expression.replace("&&", " and ").replace("||", " or ")
    translated = re.sub(r"!(?!=)", " not ", translated)
    translated = re.sub(r"\btrue\b", "True", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bfalse\b", "False", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bnull\b", "None", translated, flags=re.IGNORECASE)
    return translated.strip()


def _parse_temporal(value: str) -> datetime | date | None:
    if not _ISO_DATE.match(value):
        return None
    try:
        if "T" not in value.upper() and " " not in value:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalise_pair(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, str) and isinstance(right, str):
        left_temporal = _parse_temporal(left)
        right_temporal = _parse_temporal(right)
        if left_temporal is not None and right_temporal is not None:
            if isinstance(left_temporal, datetime) and left_temporal.tzinfo is None:
                left_temporal = left_temporal.replace(tzinfo=timezone.utc)
            if isinstance(right_temporal, datetime) and right_temporal.tzinfo is None:
                right_temporal = right_temporal.replace(tzinfo=timezone.utc)
            return left_temporal, right_temporal
    if isinstance(left, str) and isinstance(right, (date, datetime)):
        parsed = _parse_temporal(left)
        if parsed is not None:
            left = parsed
    if isinstance(right, str) and isinstance(left, (date, datetime)):
        parsed = _parse_temporal(right)
        if parsed is not None:
            right = parsed
    return left, right


class _Evaluator:
    def __init__(self, context: Mapping[str, Any], *, max_nodes: int = 128) -> None:
        self.context = context
        self.max_nodes = max_nodes
        self.visited = 0

    def evaluate(self, node: ast.AST) -> Any:
        self.visited += 1
        if self.visited > self.max_nodes:
            raise CELEvaluationError("expression_too_complex")
        method = getattr(self, f"eval_{type(node).__name__}", None)
        if method is None:
            raise CELEvaluationError(f"unsupported_node:{type(node).__name__}")
        return method(node)

    def eval_Expression(self, node: ast.Expression) -> Any:
        return self.evaluate(node.body)

    def eval_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (str, int, float, bool, type(None))):
            return node.value
        raise CELEvaluationError("unsupported_constant")

    def eval_Name(self, node: ast.Name) -> Any:
        if node.id.startswith("_") or node.id not in self.context:
            raise CELEvaluationError(f"unknown_identifier:{node.id}")
        return self.context[node.id]

    def eval_Attribute(self, node: ast.Attribute) -> Any:
        if node.attr.startswith("_"):
            raise CELEvaluationError("private_attribute_denied")
        value = self.evaluate(node.value)
        if isinstance(value, Mapping) and node.attr in value:
            return value[node.attr]
        raise CELEvaluationError(f"missing_attribute:{node.attr}")

    def eval_Subscript(self, node: ast.Subscript) -> Any:
        value = self.evaluate(node.value)
        key = self.evaluate(node.slice)
        if not isinstance(value, (Mapping, list, tuple, str)):
            raise CELEvaluationError("value_not_subscriptable")
        try:
            return value[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise CELEvaluationError("missing_subscript") from exc

    def eval_List(self, node: ast.List) -> list[Any]:
        return [self.evaluate(item) for item in node.elts]

    def eval_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.evaluate(item) for item in node.elts)

    def eval_Dict(self, node: ast.Dict) -> dict[Any, Any]:
        return {
            self.evaluate(key): self.evaluate(value)
            for key, value in zip(node.keys, node.values)
            if key is not None
        }

    def eval_BoolOp(self, node: ast.BoolOp) -> bool:
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not bool(self.evaluate(value)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value in node.values:
                if bool(self.evaluate(value)):
                    return True
            return False
        raise CELEvaluationError("unsupported_boolean_operator")

    def eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        value = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            return not bool(value)
        if isinstance(node.op, ast.USub) and isinstance(value, (int, float)):
            return -value
        if isinstance(node.op, ast.UAdd) and isinstance(value, (int, float)):
            return value
        raise CELEvaluationError("unsupported_unary_operator")

    def eval_BinOp(self, node: ast.BinOp) -> Any:
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        operators = {
            ast.Add: lambda: left + right,
            ast.Sub: lambda: left - right,
            ast.Mult: lambda: left * right,
            ast.Div: lambda: left / right,
            ast.FloorDiv: lambda: left // right,
            ast.Mod: lambda: left % right,
        }
        operation = operators.get(type(node.op))
        if operation is None:
            raise CELEvaluationError("unsupported_binary_operator")
        try:
            return operation()
        except (ArithmeticError, TypeError) as exc:
            raise CELEvaluationError("invalid_binary_operation") from exc

    def eval_Compare(self, node: ast.Compare) -> bool:
        left = self.evaluate(node.left)
        for operation, comparator in zip(node.ops, node.comparators):
            right = self.evaluate(comparator)
            normal_left, normal_right = _normalise_pair(left, right)
            try:
                if isinstance(operation, ast.Eq):
                    passed = normal_left == normal_right
                elif isinstance(operation, ast.NotEq):
                    passed = normal_left != normal_right
                elif isinstance(operation, ast.Lt):
                    passed = normal_left < normal_right
                elif isinstance(operation, ast.LtE):
                    passed = normal_left <= normal_right
                elif isinstance(operation, ast.Gt):
                    passed = normal_left > normal_right
                elif isinstance(operation, ast.GtE):
                    passed = normal_left >= normal_right
                elif isinstance(operation, ast.In):
                    passed = normal_left in normal_right
                elif isinstance(operation, ast.NotIn):
                    passed = normal_left not in normal_right
                elif isinstance(operation, ast.Is):
                    passed = normal_left is normal_right
                elif isinstance(operation, ast.IsNot):
                    passed = normal_left is not normal_right
                else:
                    raise CELEvaluationError("unsupported_comparison")
            except TypeError as exc:
                raise CELEvaluationError("incompatible_comparison") from exc
            if not passed:
                return False
            left = right
        return True

    def eval_IfExp(self, node: ast.IfExp) -> Any:
        branch = node.body if bool(self.evaluate(node.test)) else node.orelse
        return self.evaluate(branch)

    def eval_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise CELEvaluationError("function_call_denied")
        name = node.func.id
        if name == "has" and len(node.args) == 1:
            try:
                self.evaluate(node.args[0])
                return True
            except CELEvaluationError:
                return False
        args = [self.evaluate(arg) for arg in node.args]
        if (
            name == "size"
            and len(args) == 1
            and isinstance(args[0], (Mapping, list, tuple, str))
        ):
            return len(args[0])
        if name == "timestamp" and len(args) == 1 and isinstance(args[0], str):
            parsed = _parse_temporal(args[0])
            if isinstance(parsed, datetime):
                return parsed
        if name == "date" and len(args) == 1 and isinstance(args[0], str):
            parsed = _parse_temporal(args[0])
            if isinstance(parsed, date):
                return parsed.date() if isinstance(parsed, datetime) else parsed
        raise CELEvaluationError(f"function_call_denied:{name}")


class CELEvaluator:
    def __init__(
        self, *, max_expression_length: int = 2048, max_nodes: int = 128
    ) -> None:
        self.max_expression_length = max_expression_length
        self.max_nodes = max_nodes

    def compile(self, expression: str) -> ast.Expression:
        if not isinstance(expression, str) or not expression.strip():
            raise CELSyntaxError("expression_required")
        if len(expression) > self.max_expression_length:
            raise CELSyntaxError("expression_too_long")
        try:
            parsed = ast.parse(_translate_cel(expression), mode="eval")
        except (SyntaxError, ValueError) as exc:
            raise CELSyntaxError("invalid_expression") from exc
        if sum(1 for _ in ast.walk(parsed)) > self.max_nodes:
            raise CELSyntaxError("expression_too_complex")
        return parsed

    def evaluate(
        self,
        expression: str,
        *,
        candidate: Mapping[str, Any],
        world: Mapping[str, Any],
    ) -> bool:
        try:
            parsed = self.compile(expression)
            return bool(
                _Evaluator(
                    {
                        "candidate": candidate,
                        "world": world,
                        # Compatibility with Sprint 1 constraints while new
                        # policies use the explicit candidate.payload path.
                        "payload": candidate.get("payload", {}),
                    },
                    max_nodes=self.max_nodes,
                ).evaluate(parsed)
            )
        except (CELError, ArithmeticError, TypeError, ValueError):
            return False
