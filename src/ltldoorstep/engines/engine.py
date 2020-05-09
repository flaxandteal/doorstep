from contextlib import contextmanager
from ltldoorstep import printer

class Engine:
    def download(self):
        return True

    def __init__(self, config=None):
        pass

    @staticmethod
    def description():
        return '(not provided)'

    @staticmethod
    def config_help():
        return None

    def add_data(self, filename, content, redirect, session):
        raise NotImplementedError("Function must be implemented")

    def add_processor(self, modules, context, session):
        raise NotImplementedError("Function must be implemented")

    async def check_processor_statuses(self):
        raise NotImplementedError("Function must be implemented")

    async def run(self, filename, workflow_module, context, bucket=None):
        raise NotImplementedError("Function must be implemented")

    async def monitor_pipeline(self, session):
        raise NotImplementedError("Function must be implemented")

    async def get_output(self, session):
        raise NotImplementedError("Function must be implemented")

    async def get_artifact(self, session, artifact, target=None):
        if artifact.startswith('report:'):
            report = await self.get_output(session)

            report_type = artifact.replace('report:', '')

            printer_types = printer.get_printer_types()
            if not report_type in printer_types:
                raise RuntimeError(_("Report type must be one of: {}").format(', '.join(printer_types)))

            prnt = printer.get_printer(report_type, debug=False, target=target)

            prnt.build_report(report)

            return prnt.get_output()
        else:
            raise NotImplementedError("Function must be implemented (unless artifact is report)")

    @contextmanager
    def make_session(self):
        raise NotImplementedError("Function must be implemented")
