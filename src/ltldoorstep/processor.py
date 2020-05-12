import os
import logging

from .reports.report import Report, get_report_class_from_preset, combine_reports
from .context import DoorstepContext
from .printer import get_printer, get_printer_types
from .artifact import ArtifactType


class DoorstepProcessor:
    preset = None
    code = None
    description = None
    artifacts_expected = None
    _context = None

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, context):
        if type(context) is dict:
            context = DoorstepContext.from_dict(context)
        self._context = context

    def set_artifacts_to_be_requested(self, artifacts):
        self.artifacts_expected = artifacts

    def get_artifact_type(self, artifact) -> ArtifactType:
        if artifact.startswith('report:'):
            report_type = artifact.replace('report:', '')

            printer_types = get_printer_types()
            if not report_type in printer_types:
                raise RuntimeError(_("Report type must be one of: {}").format(', '.join(printer_types)))

            prnt = get_printer(report_type, debug=False, target=None)

            return prnt.get_output_type()
        else:
            raise NotImplementedError("Attempt to find unknown artifact {} (type missing, check get_artifact_type in your processor)".format(artifact))

    def get_artifact(self, artifact, target=None):
        if artifact.startswith('report:'):
            report = self.get_report()

            report_type = artifact.replace('report:', '')

            printer_types = get_printer_types()
            if not report_type in printer_types:
                raise RuntimeError(_("Report type must be one of: {}").format(', '.join(printer_types)))

            prnt = get_printer(report_type, debug=False, target=target)

            prnt.build_report(report)

            return prnt.print_output()
        else:
            raise NotImplementedError("Attempt to find unknown artifact {}".format(artifact))


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
