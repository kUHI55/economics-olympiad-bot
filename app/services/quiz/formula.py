import ast
import re
from dataclasses import dataclass
from fractions import Fraction


class UnsupportedFormula(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalMonomial:
    coefficient: Fraction
    powers: tuple[tuple[str, int], ...]

    def __str__(self) -> str:
        coefficient = "" if self.coefficient == 1 and self.powers else str(self.coefficient)
        factors = [coefficient] if coefficient else []
        factors.extend(f"{name}^{power}" if power != 1 else name for name, power in self.powers)
        return " * ".join(filter(None, factors)) or "1"


def _merge(left: CanonicalMonomial, right: CanonicalMonomial) -> CanonicalMonomial:
    powers = dict(left.powers)
    for name, power in right.powers:
        powers[name] = powers.get(name, 0) + power
        if powers[name] == 0:
            del powers[name]
    return CanonicalMonomial(left.coefficient * right.coefficient, tuple(sorted(powers.items())))


def _power(value: CanonicalMonomial, exponent: int) -> CanonicalMonomial:
    return CanonicalMonomial(
        value.coefficient**exponent,
        tuple((name, power * exponent) for name, power in value.powers),
    )


def _parse_node(node: ast.AST) -> CanonicalMonomial:
    if isinstance(node, ast.Name):
        return CanonicalMonomial(Fraction(1), ((node.id.casefold(), 1),))
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return CanonicalMonomial(Fraction(str(node.value)), ())
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _merge(CanonicalMonomial(Fraction(-1), ()), _parse_node(node.operand))
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mult):
            return _merge(_parse_node(node.left), _parse_node(node.right))
        if isinstance(node.op, ast.Div):
            return _merge(_parse_node(node.left), _power(_parse_node(node.right), -1))
        if isinstance(node.op, ast.Pow):
            exponent = _integer_literal(node.right)
            if exponent is None:
                raise UnsupportedFormula(
                    "Only integer powers are supported without a symbolic engine"
                )
            return _power(_parse_node(node.left), exponent)
    raise UnsupportedFormula("The formula is not a supported monomial")


def _integer_literal(node: ast.AST) -> int | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    return None


def canonicalise(formula: str) -> CanonicalMonomial:
    cleaned = formula.strip().replace("×", "*").replace("·", "*").replace("^", "**")
    # Formula questions normally expect the right-hand side; accept either u=U/LF or U/LF.
    if cleaned.count("=") == 1:
        cleaned = cleaned.split("=", maxsplit=1)[1].strip()
    if not cleaned or re.search(r"[^A-Za-zА-Яа-яЁё0-9_+*/().=\s-]", cleaned):
        raise UnsupportedFormula("Unsupported characters")
    try:
        expression = ast.parse(cleaned, mode="eval").body
    except SyntaxError as exc:
        raise UnsupportedFormula("Invalid formula syntax") from exc
    return _parse_node(expression)


@dataclass(frozen=True)
class FormulaComparison:
    equivalent: bool
    normalised_answer: str
    normalised_reference: str
    reason: str


class FormulaComparator:
    """Deterministic checker for common formula forms; no LLM is involved."""

    def compare(self, answer: str, reference: str) -> FormulaComparison:
        try:
            normalised_answer = canonicalise(answer)
            normalised_reference = canonicalise(reference)
        except UnsupportedFormula:
            return FormulaComparison(False, answer.strip(), reference.strip(), "unsupported")
        equivalent = normalised_answer == normalised_reference
        return FormulaComparison(
            equivalent,
            str(normalised_answer),
            str(normalised_reference),
            "equivalent" if equivalent else "different",
        )
