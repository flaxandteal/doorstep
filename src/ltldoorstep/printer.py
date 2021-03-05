import colorama
import io
import pandas
from collections import OrderedDict
import re
import uuid
import os
import logging
import json
import tabulate
import gettext
from enum import Enum
from .reports.report import Report
from .artifact import ArtifactType
from .encoders import json_dumps
from .aspect import AnnotatedTextAspect


LEVEL_MAPPING = {
    logging.ERROR: 'ERR',
    logging.WARNING: 'WNG',
    logging.INFO: 'INF'
}

class OutputSorting(Enum):
    LOCATION = 1
    CODE = 2

class OutputGrouping(Enum):
    NONE = 0
    LOCATION = 1
    CODE = 2
    LEVEL = 3

class Printer:
    output_type = None

    def __init__(self, debug=False, target=None):
        self._output_sections = []
        self._debug = debug
        self._target = target

    def get_output_type(self):
        if not self.output_type:
            raise NotImplementedError("No output type provided for this printer")
        return self.output_type

    def print_status_output(self, status):
        raise NotImplementedError("No report builder implemented for this printer")

    def get_debug(self):
        return self._debug

    def build_report(self):
        raise NotImplementedError("No report builder implemented for this printer")

    def get_output(self):
        raise NotImplementedError("No outputter implemented for this printer")

    def get_target(self):
        return self._target

    def print_output(self):
        output = self.get_output()

        if self._target is None:
            return str(output)
        elif isinstance(self._target, io.IOBase):
            self._target.write(output)
        else:
            with open(self._target, 'w') as target_file:
                target_file.write(output)

class CsvPrinter(Printer):
    output_type = ArtifactType(mime='text/csv', is_bytes=False, encoding='utf-8')

    def __init__(self, debug=False, target=None):
        super().__init__(debug, target)
        self.grouping = OutputGrouping.NONE
        self.detailed = False
        self.sort = OutputSorting.LOCATION

    def print_status_output(self, status):
        fn_table = []

        for fn, fst in status.items():
            fn_table.append([
                fst['name'],
                fst['available'],
                fst['total']
            ])

        output = tabulate.tabulate(fn_table)

        if self._target is None:
            print(output)
        else:
            with open(self._target, 'w') as target_file:
                target_file.write(output)

    def get_output(self):
        return '\n\n'.join([
            df.to_csv(None, index=False)
            for df in
            self._output_sections
        ])

    def build_report(self, result_sets):
        levels = OrderedDict([
            (logging.INFO, []),
            (logging.WARNING, []),
            (logging.ERROR, [])
        ])

        general_output = []
        results = []

        if isinstance(result_sets, Report):
            report = result_sets
        else:
            report = Report.parse(result_sets)

        if report.preset == 'tabular':
            location_headings = ['Row', 'Column']
            location = lambda item: [
                item.location['row'] if 'row' in item.location else None,
                item.location['column'] if 'column' in item.location else None
            ]
            location_casts = ['Int64', 'Int64']
        elif report.preset == 'geojson':
            location_headings = ['Index']
            location = lambda item: [
                item.location['index'] if 'index' in item.location else None
            ]
            location_casts = ['Int64']
        elif report.preset == 'document':
            location_headings = ['Line']
            location = lambda item: [
                item.location['from']['line'] if 'from' in item.location else None
            ]
            location_casts = ['Int64']
        else:
            location_headings = ['Location']
            location = lambda item: [str(item.location)]
            location_casts = [str]

        headings = location_headings + [
            'Level',
            'Processor',
            'Code',
        ]
        headings += ['Message']

        if self.grouping == OutputGrouping.LEVEL:
            groups = levels
            get_group = lambda item, level: levels[level]
        elif self.grouping == OutputGrouping.NONE:
            all_issues = []
            groups = {'': all_issues}
            get_group = lambda item, level: all_issues

        extra_columns = []
        for log_level in LEVEL_MAPPING:
            for issue in report.get_issues(log_level):
                if 'export-columns' in issue.error_data:
                    for col, _ in issue.error_data['export-columns']:
                        # This avoids confusing duplication of names, but puts
                        # the onus on the processor creator to ensure they do
                        # not duplicate column names if they mean different things
                        if col not in extra_columns:
                            extra_columns.append(col)

        headings += extra_columns

        for log_level in LEVEL_MAPPING:
            for issue in report.get_issues(log_level):
                item = issue.get_item()
                item_str = str(item.definition)

                if 'export-columns' in issue.error_data:
                    export_columns = {k: v for k, v in issue.error_data['export-columns']}
                else:
                    export_columns = {}

                item_row = location(item) + [
                    LEVEL_MAPPING[log_level],
                    issue.processor,
                    issue.code
                ] + [issue.message] + [
                    (
                        export_columns[col]
                        if col in export_columns else
                        None
                    )
                    for col in extra_columns
                ]
                get_group(item, log_level).append(item_row)

        for group in groups.values():
            df = pandas.DataFrame(group, columns=headings)
            for heading, cast in zip(location_headings, location_casts):
                df[heading] = df[heading].astype(cast, errors='ignore')

            if self.sort == OutputSorting.CODE:
                df['sort_val'] = df['Processor'] + '|' + df['Code']
                sort_vals = ['sort_val']
            elif self.sort == OutputSorting.LOCATION:
                sort_vals = location_headings

            df = df.sort_values(sort_vals, na_position='first')

            if not self.detailed:
                del df['Processor']
                del df['Code']
            if 'sort_val' in df:
                del df['sort_val']

            self.add_section(df)

    def add_section(self, output):
        self._output_sections.append(output)

class TermColorPrinter(Printer):
    output_type = ArtifactType(mime='text/plain', is_bytes=False, encoding='utf-8')

    def print_status_output(self, status):
        fn_table = []

        for fn, fst in status.items():
            fn_table.append([
                fst['name'],
                fst['available'],
                fst['total']
            ])

        output = tabulate.tabulate(fn_table)

        if self._target is None:
            print(output)
        else:
            with open(self._target, 'w') as target_file:
                target_file.write(output)

    def get_output(self):
        return '\n\n'.join(self._output_sections)

    def build_report(self, result_sets):
        levels = {
            logging.INFO: [],
            logging.WARNING: [],
            logging.ERROR: []
        }

        general_output = []
        results = []

        if isinstance(result_sets, Report):
            report = result_sets
        else:
            report = Report.parse(result_sets)

        for log_level in LEVEL_MAPPING:
            for issue in report.get_issues(log_level):
                item = issue.get_item()
                item_str = str(item.definition)
                if len(item_str) > 40:
                    item_str = item_str[:37] + '...'
                levels[log_level].append([
                    issue.processor,
                    str(item.location),
                    issue.code,
                    issue.message,
                    item_str
                ])

        output_sections = []
        if levels[logging.ERROR]:
            self.add_section('\n'.join([
                'Errors',
                tabulate.tabulate(levels[logging.ERROR]),
            ]), colorama.Fore.RED + colorama.Style.BRIGHT)

        if levels[logging.WARNING]:
            self.add_section('\n'.join([
                'Warnings',
                tabulate.tabulate(levels[logging.WARNING]),
            ]), colorama.Fore.YELLOW + colorama.Style.BRIGHT)

        if levels[logging.INFO]:
            self.add_section('\n'.join([
                'Information',
                tabulate.tabulate(levels[logging.INFO])
            ]))

    def add_section(self, output, style=None):
        if style:
            output = style + output + colorama.Style.RESET_ALL
        self._output_sections.append(output)


class JsonPrinter(Printer):
    output_type = ArtifactType(mime='application/json', is_bytes=False, encoding='utf-8')

    def print_status_output(self, status):
        return json_dumps(status)

    def get_output(self):
        return self._output

    def build_report(self, result_sets):
        if isinstance(result_sets, Report):
            report = result_sets
        else:
            report = Report.parse(result_sets)

        result_sets = report.__serialize__()
        self._output = json_dumps(result_sets)

class HtmlPrinter(Printer):
    class AnnotatedTextSubprinter:
        def get_output(self, aspect):
            uniqid = uuid.uuid4()
            annotations = [ann.render() for ann in aspect.get_annotations()]
            content = f"""
            <script>
                annotations['content-{uniqid}'] = {json_dumps(annotations)};
            </script>
            <div id="content-{uniqid}" class="annotation-box">
            {aspect.plaintext}
            </div>
            """
            return content

    output_type = ArtifactType(mime='text/html', is_bytes=False, encoding='utf-8')

    def print_status_output(self, status):
        output = status

        if self._target is None:
            print(output)
        else:
            with open(self._target, 'w') as target_file:
                target_file.write(output)

    def get_output(self):
        templates = [
            os.path.join(
                os.path.dirname(__file__),
                'templates',
                template
            ) for template in ('head.html', 'tail.html')
        ]

        with open(templates[0], 'r') as head_f:
            output = head_f.read()

        output += '\n' + '\n<hr/>\n'.join(self._output_sections) + '\n'

        with open(templates[1], 'r') as tail_f:
            output += tail_f.read()

        return output

    def build_report(self, result_sets):
        levels = {
            logging.INFO: [],
            logging.WARNING: [],
            logging.ERROR: []
        }

        general_output = []
        results = []

        if isinstance(result_sets, Report):
            report = result_sets
        else:
            report = Report.parse(result_sets)

        def _location_to_string(location):
            if type(location) is dict:
                return '<br/>'.join(['{}: {}'.format(k.upper(), v) for k, v in location.items()])

            return str(location)

        ann_text_ptr = self.AnnotatedTextSubprinter()
        for log_level in LEVEL_MAPPING:
            for issue in report.get_issues(log_level):
                item = issue.get_item()
                context = issue.get_context()
                content = item.content
                if isinstance(content, AnnotatedTextAspect):
                    content = ann_text_ptr.get_output(content)

                if context and report.properties['headers'] and context[0].definition:
                    headers = zip(report.properties['headers'], context[0].definition)
                else:
                    headers = []

                levels[log_level].append([
                    issue.processor,
                    _location_to_string(item.location),
                    issue.code,
                    issue.message.replace('\n', '<br/>'),
                    content,
                    issue.error_data,
                    item.properties if item.properties else '',
                    ['{}:{}'.format(*p) for p in headers]
                ])

        level_labels = [
            (logging.ERROR, 'Errors', 'error'),
            (logging.WARNING, 'Warnings', 'warnings'),
            (logging.INFO, 'Info', 'info')
        ]

        if report.properties['issues-skipped']:
            skipped = '<h3>Issues Skipped</h3>\n<table width=100%>\n'
            skipped += '<thead><tr><th>' + '</th><th>'.join([
                _('Issue'), _('Skipped'), _('Kept'), _('Total')
            ]) + '</tr></thead>\n'
            for code, count in report.properties['issues-skipped'].items():
                row = '<tr><td>{}</td>'.format(code)
                for cell in count:
                    row += '<td>{}</td>'.format(cell)
                row += '</tr>\n'
                skipped += row
            skipped += '</table>\n'
            self.add_section(skipped)

        addslashes = re.compile(r'"')
        for level_code, level_title, level_class in level_labels:
            if levels[level_code]:
                table = ['<h3>{}</h3>'.format(level_title), '<table>']

                table.append('<thead><tr><th>' + '</th><th>'.join([
                    _('Processor'),
                    _('Location'),
                    _('Issue'),
                    _('Description'),
                    _('On Item'),
                    _('Issue Data'),
                    _('Item'),
                    _('Context')
                ]) + '</tr></thead>')
                table.append('<tbody>')

                for error in levels[level_code]:
                    row = '<tr>'
                    for cell in error:
                        if type(cell) is str:
                            row += '<td>{}</td>'.format(cell)
                        else:
                            row += '<td class="field-json" data-json="{}"></td>'.format(addslashes.sub(r'&quot;', json_dumps(cell)))

                    table.append(row)

                table.append('</tbody>')
                table.append('</table>')
                self.add_section('\n'.join(table), level_class)

    def add_section(self, output, style=None):
        self._output_sections.append('<div class="{style}">\n{section}\n</div>'.format(style=style, section=output))

_printers = {
    'json': JsonPrinter,
    'ansi': TermColorPrinter,
    'csv': CsvPrinter,
    'html': HtmlPrinter
}

def get_printer_types():
    global _printers

    return list(_printers.keys())

def get_printer(prntr, debug, target):
    global _printers

    if prntr not in _printers:
        raise RuntimeError(_("Unknown output format"))

    return _printers[prntr](debug, target=target)
