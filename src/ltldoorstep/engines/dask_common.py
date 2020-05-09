"""Common routines for dask engine."""

import os
from dask import threaded
from ltldoorstep.reports.report import Report

def execute(filename, module_name, context):
    """Import and run a workflow on a data file."""
    mod = __import__(module_name)
    return run(filename, mod, context)

def run(filename, mod, context, compiled=True):
    """Real runner for a given ltldoorstep processor module and datafile."""

    processor = mod.processor()
    workflow = processor.build_workflow(filename, context)

    result = threaded.get(workflow, 'output', num_workers=2)

    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], Report):
        processor.set_report(result[1])
    elif isinstance(result, Report):
        processor.set_report(result)

    if compiled:
        return processor.compile_report(filename, context)
    return processor.get_report()
