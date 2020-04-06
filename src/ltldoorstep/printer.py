import colorama
import re
import os
import logging
import json
import tabulate
import gettext
from .processor import Report


LEVEL_MAPPING = [
    logging.ERROR,
    logging.WARNING,
    logging.INFO
]

class Printer:
    def __init__(self, debug=False, target=None):
        self._output_sections = []
        self._debug = debug
        self._target = target

    def print_status_output(self, status):
        raise NotImplementedError("No report builder implemented for this printer")

    def get_debug(self):
        return self._debug

    def build_report(self):
        raise NotImplementedError("No report builder implemented for this printer")

    def get_output(self):
        raise NotImplementedError("No outputter implemented for this printer")

    def print_output(self):
        output = self.get_output()

        if self._target is None:
            print(output)
        else:
            with open(self._target, 'w') as target_file:
                target_file.write(output)

class TermColorPrinter(Printer):
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
        # logging.warn("Report ***** %s " % report)

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
    def print_status_output(self, status):
        return json.dumps(status)

    def get_output(self):
        return self._output

    def build_report(self, result_sets):
        self._output = json.dumps(result_sets)

class HtmlPrinter(Printer):
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

        for log_level in LEVEL_MAPPING:
            for issue in report.get_issues(log_level):
                item = issue.get_item()
                levels[log_level].append([
                    issue.processor,
                    str(item.location),
                    issue.code,
                    issue.message,
                    str(item.definition) if item.definition else '',
                    issue.error_data,
                    item.properties if item.properties else ''
                ])

        level_labels = [
            (logging.ERROR, 'Errors', 'error'),
            (logging.WARNING, 'Warnings', 'warnings'),
            (logging.INFO, 'Info', 'info')
        ]

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
                    _('Item')
                ]) + '</tr></thead>')
                table.append('<tbody>')

                for error in levels[level_code]:
                    row = '<tr>'
                    for cell in error:
                        if type(cell) is str:
                            row += '<td>{}</td>'.format(cell)
                        else:
                            row += '<td class="field-json" data-json="{}"></td>'.format(addslashes.sub(r'&quot;', json.dumps(cell)))

                    table.append(row)

                table.append('</tbody>')
                table.append('</table>')
                self.add_section('\n'.join(table), level_class)

    def add_section(self, output, style=None):
        self._output_sections.append('<div class="{style}">\n{section}\n</div>'.format(style=style, section=output))

_printers = {
    'json': JsonPrinter,
    'ansi': TermColorPrinter,
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
