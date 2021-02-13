"""Testing for report functionality"""

import json
import pytest
from ltldoorstep.printer import TermColorPrinter, JsonPrinter
import logging


@pytest.fixture()
def report():
    return {
      "supplementary": [],
      "item-count": 1,
      "error-count": 1,
      "counts": {
        "errors": 1,
        "warnings": 0,
        "informations": 0
      },
      "valid": False,
      "issues-skipped": {},
      "artifacts": {},
      "tables": [
        {
          "format": "csv",
          "errors": [
            {
              "processor": "test-proc",
              "code": "test-error",
              "message": "TEST",
              "item": {
                "entity": {
                  "type": "Cell",
                  "location": {},
                  "definition": None
                },
                "properties": None
              },
              "context": None,
              "error-data": {}
            }
          ],
          "warnings": [],
          "informations": [],
          "row-count": None,
          "headers": None,
          "source": "test.csv",
          "time": None,
          "valid": False,
          "scheme": "file",
          "encoding": None,
          "schema": None,
          "item-count": 1,
          "error-count": 1,
          "warning-count": 1,
          "information-count": 1
        }
      ],
      "filename": "test.csv",
      "preset": "tabular",
      "warnings": [],
      "table-count": 1,
      "time": None
    }

def test_term_color_printer(report):
    """check printing to terminal works"""

    printer = TermColorPrinter()
    printer.build_report(report)

    assert 'Errors' in printer.get_output()
    assert 'Warnings' not in printer.get_output()
    assert 'test-proc  {}  test-error  TEST  None' in printer.get_output()

def test_json_printer(report):
    """check building of JSON reports"""

    printer = JsonPrinter()
    printer.build_report(report)

    assert json.loads(printer.get_output()) == report
