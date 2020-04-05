from .report import Report, ReportItem
import itertools

class TabularReport(Report):

    preset = 'tabular'

    @staticmethod
    def table_string_from_issue(issue):
        sheet = issue.item.location['sheet'] if 'sheet' in issue.item.location else None
        table = issue.item.location['table'] if 'table' in issue.item.location else None
        return TabularReport.table_string_from_sheet_table(sheet, table)

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

    def add_issue(self, log_level, code, message, row_number=None, column_number=None, row=None, error_data=None, at_top=False, sheet=None, table=None):
        """This function will add an issue to the report and takes as parameters the processor, the log level, code, message"""

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
        if row_number:
            if column_number:
                typ = 'Cell'
                if row:
                    context_location = dict(location)
                    context_location['column'] = None
                    context = [ReportItem('Row', context_location, row, None)]
            else:
                typ = 'Row'
                properties = row
        else:
            if column_number:
                typ = 'Column'
            elif table:
                typ = 'Table'
            elif sheet:
                typ = 'Sheet'
            else:
                typ = 'Global'

        item = ReportItem(typ, location, properties, None)

        super(TabularReport, self).add_issue(log_level, code, message, item, error_data=error_data, context=context, at_top=at_top)
