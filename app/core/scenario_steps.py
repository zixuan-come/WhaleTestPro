"""Value snapshots shared by migrations, scenario saving and suite planning."""
from copy import deepcopy
from uuid import uuid4


REQUEST_FIELDS = ('method', 'url', 'path_params', 'headers', 'params', 'body')
CASE_FIELDS = ('expected_status', 'assertions', 'extract_rules', 'setup_sql', 'teardown_sql', 'datasets', 'retries')


def value(row, field, default=None):
    return row.get(field, default) if isinstance(row, dict) else getattr(row, field, default)


def case_snapshot(case, interface, *, source_id=None, step_id=None):
    number = value(case, 'id', source_id)
    name = value(case, 'name') or f'用例 #{number}（已不可用）'
    result = dict(step_id=step_id or str(uuid4()), source_case_id=number, source_case_name=name,
                  interface_id=value(case, 'interface_id'), interface_name=value(interface, 'name'), name=name,
                  missing_reason='来源用例不存在或不属于当前项目' if case is None else
                  '关联接口不存在或不属于当前项目' if interface is None else None)
    result.update({field: deepcopy(value(case, field)) for field in CASE_FIELDS})
    result['expected_status'] = value(case, 'expected_status') or 200
    result['retries'] = value(case, 'retries') or 0
    result.update({field: deepcopy(value(interface, field)) for field in REQUEST_FIELDS})
    overrides = value(case, 'request_overrides') or {}
    result.update({field: deepcopy(overrides[field]) for field in REQUEST_FIELDS[2:] if field in overrides})
    return result


def execution_config(step):
    return {key: step.get(key) for key in (*REQUEST_FIELDS, *CASE_FIELDS)}


def standalone_case_options(case):
    """True when chain execution cannot substitute for the library case."""
    datasets = value(case, 'datasets')
    return bool(datasets or (datasets is not None and not isinstance(datasets, list))
                or value(case, 'setup_sql') or value(case, 'teardown_sql')
                or value(case, 'retries', 0) not in (None, 0))


def equivalent_case_ids(steps, cases, interfaces):
    """Only an unchanged executable copy can replace an explicit library case."""
    included = set()
    for step in steps:
        number = step.get('source_case_id')
        case = cases.get(number)
        # Chains intentionally omit SQL, datasets and retry. Even an unchanged
        # metadata snapshot cannot stand in for that standalone behavior.
        if standalone_case_options(case):
            continue
        interface = interfaces.get(value(case, 'interface_id')) if case is not None else None
        if case is not None and interface is not None and not step.get('missing_reason'):
            if execution_config(step) == execution_config(case_snapshot(case, interface)):
                included.add(number)
    return included
