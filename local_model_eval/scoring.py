"""Deterministic fixture scoring; never execute model-produced Python or shell."""

import ast
import json
import operator


def parse_json(text):
    stripped = text.strip()
    try:
        return json.loads(stripped), 'strict'
    except ValueError:
        if stripped.startswith('```') and stripped.endswith('```') and '\n' in stripped:
            return json.loads(stripped.split('\n', 1)[1].rsplit('```', 1)[0]), 'fenced'
        raise


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Div: operator.truediv}


def expression_value(source, variables):
    if not isinstance(source, str) or len(source) > 300:
        raise ValueError('expression exceeds fixture grammar')
    tree = ast.parse(source, mode='eval')
    if len(list(ast.walk(tree))) > 50:
        raise ValueError('expression too complex')

    def visit(node):
        if isinstance(node, ast.Expression):
            value = visit(node.body)
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.Name):
            value = variables[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
            value = OPS[type(node.op)](visit(node.left), visit(node.right))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'min', 'max', 'abs'} and not node.keywords and 1 <= len(node.args) <= 3:
            value = {'min': min, 'max': max, 'abs': abs}[node.func.id](*[visit(a) for a in node.args])
        else:
            raise ValueError('expression uses unsupported syntax')
        if type(value) not in (int, float) or not -1e9 <= value <= 1e9:
            raise ValueError('expression exceeds numeric bounds')
        return value

    return visit(tree)


def score(case, text):
    formatting = None
    try:
        answer, formatting = parse_json(text)
        if not isinstance(answer, dict):
            raise ValueError('answer must be a JSON object')
        kind = case['kind']
        if kind == 'review':
            findings = answer['findings']
            if not isinstance(findings, list) or len(findings) > 20:
                raise ValueError('invalid findings list')
            actual = {(f['line'], f['kind']) for f in findings}
            expected = {(f['line'], f['kind']) for f in case['expected']}
            return {'passed': actual == expected and len(actual) == len(findings), 'format': formatting,
                    'true_positives': len(actual & expected), 'false_positives': len(actual - expected),
                    'missed': len(expected - actual)}
        if kind == 'repair':
            results = [expression_value(answer['expression'], row['inputs']) == row['expected'] for row in case['checks']]
            return {'passed': all(results), 'format': formatting, 'checks_passed': sum(results), 'checks': len(results)}
        if kind == 'regression':
            rows = answer['cases']
            if not isinstance(rows, list) or not 1 <= len(rows) <= 12:
                raise ValueError('expected 1..12 test inputs')
            killed, valid = False, True
            for row in rows:
                x, low, high = [row[k] for k in ('value', 'lower', 'upper')]
                if any(type(v) is not int or abs(v) > 10000 for v in (x, low, high)) or low > high or type(row['expected']) is not bool:
                    raise ValueError('invalid regression input')
                correct = low <= x <= high
                valid &= row['expected'] == correct
                killed |= row['expected'] != (x >= low or x <= high)
            return {'passed': bool(valid and killed), 'format': formatting, 'oracle_valid': bool(valid), 'mutant_killed': bool(killed)}
        if kind == 'plan':
            steps = answer['steps']
            valid = isinstance(steps, list) and all(isinstance(s, str) for s in steps) and isinstance(answer['risks'], list)
            return {'passed': None, 'format': formatting, 'structure_valid': valid,
                    'manual_review_required': True, 'rubric': case['rubric']}
        raise ValueError('unknown case kind')
    except (ValueError, TypeError, KeyError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        result = {'passed': False, 'error': str(exc)}
        if formatting is not None:
            result['format'] = formatting
        return result
