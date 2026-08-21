def json_matches(expected, actual) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False

        for key, expected_value in expected.items():
            if key not in actual:
                return False

            if not json_matches(expected_value, actual[key]):
                return False
        return True

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False

        if len(expected) > len(actual):
            return False

        return all(json_matches(expected_item, actual_item) for expected_item, actual_item in zip(expected, actual, strict=False))
    return expected == actual
