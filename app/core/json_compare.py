"""JSON equality shared by functional and load-test business assertions."""


def json_equal(actual, expected):
    # JSON has a distinct boolean type. Python otherwise considers True == 1,
    # including inside dicts and lists. Integers and floats are both JSON numbers.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            json_equal(value, expected[key]) for key, value in actual.items())
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            json_equal(left, right) for left, right in zip(actual, expected))
    return actual == expected


def json_contains(actual, expected):
    if isinstance(actual, list):
        return any(json_equal(item, expected) for item in actual)
    # Preserve string substring and object-key membership semantics. Invalid
    # operand types still raise and are reported as failed assertions by callers.
    return expected in actual
