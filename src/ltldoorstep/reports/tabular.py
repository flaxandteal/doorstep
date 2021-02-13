import itertools
from typing import Union
from .report import Report, ReportItem
from ..aspect import Aspect

class TabularCellReportItem(ReportItem):
    @property
    def content(self):
        if self.properties and '_content' in self.properties:
            return self.properties['_content']
        return super().content

class TabularReport(Report):

    preset = 'tabular'

    @staticmethod
    def table_string_from_issue(issue):
        sheet = issue.item.location['sheet'] if 'sheet' in issue.item.location else None
        table = issue.item.location['table'] if 'table' in issue.item.location else None
        return TabularReport.table_string_from_sheet_table(sheet, table)

    @classmethod
    def get_rich_item_class(cls, item):
        if 'entity' in item and 'type' in item['entity'] and item['entity']['type'] == 'Cell':
            return TabularCellReportItem

        return ReportItem

    @staticmethod
    def table_string_from_sheet_table(sheet, table):
        table_string = ':'

        if sheet is not None:
            table_string += f'{sheet}'
        if table is not None:
            table_string += f':{table}'

        if table_string == ':':
            table_string = ''

        return table_string

    def add_issue(self, log_level, code, message, row_number=None, column_number=None, row=None, error_data=None,
                  at_top=False, sheet=None, table=None, cell_content: Union[Aspect, str, None] = None):
        """This function will add an issue to the report and takes as parameters the processor, the log level, code, message"""

        report_item_cls = ReportItem

        if row and self.properties['headers']:
            if isinstance(self.properties['headers'], dict):
                table_string = self.table_string_from_sheet_table(sheet, table)

                if table_string in self.properties['headers']:
                    headers = self.properties['headers'][table_string]
                else:
                    headers = []
            else:
                headers = self.properties['headers']

            if isinstance(row, dict):
                base = {k: None for k in headers}
                base.update(row)
                row = base
            else:
                row_pairs = itertools.zip_longest(headers, row)
                row = {k: v for k, v in row_pairs if k is not None}

        location = {'row': row_number, 'column': column_number}

        if sheet is not None:
            location['sheet'] = sheet

        if table is not None:
            location['table'] = table

        context = None
        properties = None
        definition = None
        if row_number:
            if column_number:
                typ = 'Cell'
                if row:
                    context_location = dict(location)
                    context_location['column'] = None
                    report_item_cls = TabularCellReportItem
                    context = [ReportItem('Row', context_location, row, None)]
                    if column_number < len(row):
                        definition = row[headers[column_number]]
                        if cell_content and cell_content != definition:
                            properties = {
                                '_content': cell_content
                            }
            else:
                typ = 'Row'
                definition = row
        else:
            if column_number:
                typ = 'Column'
            elif table:
                typ = 'Table'
            elif sheet:
                typ = 'Sheet'
            else:
                typ = 'Global'

        item = report_item_cls(typ, location, definition, properties)

        super(TabularReport, self).add_issue(log_level, code, message, item, error_data=error_data, context=context, at_top=at_top)
