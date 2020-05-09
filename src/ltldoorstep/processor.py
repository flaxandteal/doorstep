import os
import logging

from .reports.report import Report, get_report_class_from_preset, combine_reports
from .context import DoorstepContext

class DoorstepProcessor:
    preset = None
    code = None
    description = None
    _context = None

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, context):
        if type(context) is dict:
            context = DoorstepContext.from_dict(context)
        self._context = context

    @classmethod
    def make_report(cls):
        report = get_report_class_from_preset(cls.preset)

        if cls.code:
            code = cls.code
        else:
            code = _("(unknown processor)")

        if cls.description:
            description = cls.description
        else:
            description = _("(no processor description provided)")

        return report(code, description)

    def initialize(self, report=None, context=None):
        if report is None:
            report = self.make_report()
        self._report = report
        self.context = context

    @classmethod
    def make(cls):
        new = cls()
        new.initialize()
        return new

    def compile_report(self, filename=None, context=None):
        return self._report.compile(filename, context)

    def get_report(self):
        return self._report

    def set_report(self, report):
        self._report = report

    def build_workflow(self, filename, context={}):
        if not isinstance(context, DoorstepContext):
            context = DoorstepContext.from_dict(context)
        self.context = context
        return self.get_workflow(filename, context)

    def get_workflow(self, filename, context):
        return {}
