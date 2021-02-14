"""This is the report object that will be used for the standardisation of processors reporting
The Report superclass can be inherited for different forms of reporting i.e. tabular, GeoJSON etc."""


import logging
import json
import os
from ..context import DoorstepContext
from ..encoders import Serializable, json_dumps
from ..artifact import ArtifactRecord, ArtifactType
from ..aspect import get_aspect_class

# Delta allows us to avoid adding totals together and
# double-counting existing, kept, rows
def _merge_issues_skipped(skip_a, skip_b, recounting=False):
    if skip_b:
        for code, tpl in skip_b.items():
            if len(tpl) == 3:
                (skipped, kept, total) = tpl
            else:
                (skipped, total) = tpl
                kept = 100
            if code in skip_a:
                existing = skip_a[code]
                if recounting:
                    skip_a[code] = (existing[0] + skipped, existing[1], existing[2] + total - existing[1])
                else: # merging
                    skip_a[code] = (existing[0] + skipped, existing[1] + kept, existing[2] + total)
            else:
                skip_a[code] = (skipped, kept, total)
    return skip_a

def get_report_class_from_preset(preset):
    if preset not in _report_class_from_preset:
        raise NotImplementedError(_(
            "This version of doorstep does not have the requested Report preset type"
        ))
    return _report_class_from_preset[preset]

class ReportItem:
    def __init__(self, typ, location, definition, properties):
        self.type = typ
        self.location = location
        self.definition = definition
        self.properties = dict(properties) if properties else None

    def __str__(self):
        return json_dumps(self.render())

    def __repr__(self):
        return '(|Item: %s|)' % str(self)

    @property
    def content(self):
        if self.properties:
            return self.properties
        elif self.definition:
            return self.definition
        return ''

    # DO NOT OVERRIDE
    @classmethod
    def parse(cls, data):
        properties = data['properties']
        if properties:
            for prop, value in properties.items():
                if isinstance(value, object):
                    properties[prop] = get_aspect_class(value['_aspect']).parse(value)
        if data['entity']:
            if 'definition' in data['entity']:
                definition = data['entity']['definition']
                if definition and isinstance(definition, dict) and '_aspect' in definition:
                    definition = get_aspect_class(definition['_aspect']).parse(definition)
            else:
                definition = None

            return cls(
                typ=data['entity']['type'] if data['entity'] else None,
                location=data['entity']['location'] if data['entity'] else None,
                definition=definition,
                properties=properties
            )
        else:
            # FIXME: args
            return cls(definition=None, location=None, typ=None, properties=properties)

    # DO NOT OVERRIDE
    def render(self):
        definition = self.definition
        if hasattr(definition, '__serialize__'):
            definition = self.definition.__serialize__()

        return {
            'entity': {
                'type': self.type,
                'location': self.location,
                'definition': definition
            },
            'properties': {
                k: v.__serialize__() if hasattr(v, '__serialize__') else v
                for k, v in self.properties.items()
            } if self.properties else None
        }

class ReportItemLiteral(ReportItem):
    def __init__(self, literal):
        self.literal = literal

    def render(self):
        return self.literal

class ReportIssue:
    def __init__(self, level, item, context, processor, code, message, error_data=None):
        self.level = level
        self.processor = processor
        self.code = code
        self.message = message
        self.item = item
        self.context = context

        if error_data is None:
            error_data = {}
        self.error_data = error_data

    def __str__(self):
        return json_dumps(self.render())

    def __repr__(self):
        return '(|Issue: %s|)' % str(self)

    def get_identifier(self):
        return '{}|{}'.format(self.processor, self.code)

    def get_item(self):
        return self.item

    def get_context(self):
        return self.context

    @classmethod
    def parse(cls, level, data, report_cls=None):
        # This allows different presets to use rich items.
        # HOWEVER, they should never affect the parsing itself or re-rendering -
        # it cannot be guaranteed that a rich item will be consistently used
        # in parsing.
        if report_cls is None:
            parse_item = ReportItem.parse
        else:
            parse_item = lambda item: report_cls.get_rich_item_class(item).parse(item)

        return cls(
            level=level,
            processor=data['processor'],
            code=data['code'],
            message=data['message'],
            item=parse_item(data['item']),
            context=[parse_item(c) for c in data['context']] if data['context'] else None,
            error_data=(data['error-data'] if 'error-data' in data else {})
        )

    def render(self):
        return {
            'processor': self.processor,
            'code' : self.code,
            'message' : self.message,
            'item': self.item.render(),
            'context': [c.render() for c in self.context] if self.context else None,
            'error-data': self.error_data
        }

class ReportIssueLiteral(ReportIssue):
    def __init__(self, level, literal, literal_item):
        self.level = level
        self.literal = literal
        self.item = ReportItemLiteral(literal_item)

    def render(self):
        return self.literal

class Report(Serializable):
    preset = None
    max_issues_per_code = 100

    @classmethod
    def get_rich_item_class(cls, item):
        return ReportItem

    @classmethod
    def get_preset(cls):
        if not cls.preset:
            raise NotImplementedError(_("This report class must have a preset type"))

        return cls.preset

    def has_processor(self, processor, include_subprocessors):
        if include_subprocessors:
            group = [self.processor] + self.get_subprocessors()
        else:
            group = [self.processor]

        if ':' in processor:
            comp = lambda p: processor == p
        else:
            comp = lambda p: p.split(':')[0] == processor

        return any([comp(p) for p in group])

    def get_subprocessors(self):
        subprocessors = set()
        for level in self.issues.values():
            for issue in level:
                subprocessors.add(issue.processor)
        return list(subprocessors)

    def __serialize__(self):
        return self.compile()

    def __str__(self):
        return json_dumps(self.__serialize__())

    def __repr__(self):
        return '(|Report: %s|)' % str(self)

    def __init__(self, processor, info, filename='', context=None, headers=None, encoding='utf-8', time=0., row_count=None, supplementary=None, issues=None, issues_skipped=None, artifacts=None):
        if issues is None:
            self.issues = {
                logging.ERROR: [],
                logging.WARNING: [],
                logging.INFO: []
            }
        else:
            self.issues = issues

        if context is None:
            context = {}
        if supplementary is None:
            supplementary = []
        if artifacts is None:
            artifacts = {}

        self.processor = processor
        self.info = info
        self.supplementary = supplementary
        self.filename = filename
        self.context = context
        self.processors_count = {}
        self.artifacts = artifacts

        if issues_skipped is None:
            issues_skipped = {}

        if artifacts is None:
            artifacts = {}

        self.properties = {
            'row-count': row_count,
            'time': time,
            'encoding': encoding,
            'preset': self.get_preset(),
            'issues-skipped': issues_skipped,
            'headers': headers
        }

    def record_artifact(self, key, uri, typ: ArtifactType):
        if self.processor:
            key = '{}#{}'.format(self.processor, key)
        self.artifacts[key] = ArtifactRecord(uri=uri, mime=typ.mime, is_bytes=typ.is_bytes, encoding=typ.encoding)

    def get_issues(self, level=None):
        if level:
            return self.issues[level]
        return sum(list(self.issues.values()), [])

    def get_issues_by_code(self, code, level=None):
        issues = self.get_issues(level)
        return [issue for issue in issues if issue.code == code]

    def append_issue(self, issue, prepend=False):
        if prepend:
            self.issues[issue.level].insert(0, issue)
        else:
            self.issues[issue.level].append(issue)

    @classmethod
    def load(cls, file_obj):
        return cls.parse(json.load(file_obj))

    @classmethod
    def parse(cls, dictionary):
        cls = get_report_class_from_preset(dictionary['preset'])

        issues = {
            logging.INFO: [],
            logging.WARNING: [],
            logging.ERROR: []
        }
        # table = {}
        filename = dictionary['filename']

        row_count = None
        time = None
        encoding = None
        issues_skipped = {}
        artifacts = {}
        headers = None

        context = None
        if 'context' in dictionary:
            if isinstance(dictionary['context'], DoorstepContext):
                context = dictionary['context']
            else:
                context = DoorstepContext.from_dict(dictionary['context'])

        for table in dictionary['tables']:
            issues[logging.ERROR] += [
                ReportIssue.parse(logging.ERROR, issue, cls)
                for issue in
                    table['errors']
            ]

            issues[logging.WARNING] += [
                ReportIssue.parse(logging.WARNING, issue, cls)
                for issue in
                    table['warnings']
            ]

            issues[logging.INFO] += [
                ReportIssue.parse(logging.INFO, issue, cls)
                for issue in
                    table['informations']
            ]

            if context is None:
                context = DoorstepContext(context_format=table['format'])

            row_count = table['row-count'] if 'time' in table else None
            time = table['time'] if 'time' in table else None
            encoding = table['encoding'] if 'encoding' in table else None
            headers = table['headers'] if 'headers' in table else None

        supplementary = dictionary['supplementary']
        issues_skipped = dictionary['issues-skipped'] if 'issues-skipped' in dictionary else {}
        artifacts = {k: ArtifactRecord(**v) for k, v in dictionary['artifacts'].items()} if 'artifacts' in dictionary else {}

        return cls(
            '(unknown)',
            '(parsed by ltldoorstep)',
            filename=filename,
            supplementary=supplementary,
            row_count=row_count,
            time=time,
            encoding=encoding,
            headers=headers,
            context=context,
            issues=issues,
            issues_skipped=issues_skipped,
            artifacts=artifacts
        )

    def update(self, additional):
        for level, issues in additional.issues.items():
            self.issues[level] += issues

        self.supplementary += additional.supplementary

        for prop in ('row-count', 'encoding', 'headers', 'preset'):
            if self.properties[prop] is None:
                self.properties[prop] = additional.properties[prop]

        self.properties['issues-skipped'] = _merge_issues_skipped(
            self.properties['issues-skipped'],
            additional.properties['issues-skipped']
        )

        self.artifacts.update(additional.artifacts)

    @staticmethod
    def table_string_from_issue(issue):
        return ''

    def compile(self, filename=None, context=None):
        supplementary = self.supplementary

        if filename is None:
            filename = self.filename

        if not filename:
            filename = 'unknown.csv'

        if context is None:
            context = self.context

        if context and context.context_format:
            frmt = context.context_format
        else:
            root, frmt = os.path.splitext(filename)
            if frmt and frmt[0] == '.':
                frmt = frmt[1:]

        table_strings = {self.table_string_from_issue(issue) for issues in self.issues.values() for issue in issues}
        table_strings = sorted(list(table_strings))
        issues_by_table = {ts: {logging.ERROR: [], logging.WARNING: [], logging.INFO: []} for ts in table_strings}

        codes_count = {}
        skipped = {}
        for level, issue_list in self.issues.items():
            for issue in issue_list:
                code = issue.get_identifier()
                if code not in codes_count:
                    codes_count[code] = 0

                codes_count[code] += 1

                # Limit the number of issues one code can contribute
                if codes_count[code] > self.max_issues_per_code:
                    continue

                if codes_count[code] == self.max_issues_per_code:
                    total = len([1 for lvl, ilist in self.issues.items() for iss in ilist if iss.get_identifier() == code])
                    if total > codes_count[code]:
                        skipped[code] = [total - codes_count[code], codes_count[code], total]

                issues_by_table[self.table_string_from_issue(issue)][level].append(issue)

        skipped = _merge_issues_skipped(skipped, self.properties['issues-skipped'], recounting=True)
        artifacts = {k: {'uri': a.uri, 'is_bytes': a.is_bytes, 'mime': a.mime, 'encoding': a.encoding} for k, a in self.artifacts.items()}

        tables = []
        total_items = {
            logging.ERROR: 0,
            logging.WARNING: 0,
            logging.INFO: 0
        }
        total_valid = True
        for table_string in table_strings:
            table = issues_by_table[table_string]
            report = {k: [item.render() for item in v] for k, v in table.items()}
            item_count = sum([len(r) for r in report.values()])

            for level, items in report.items():
                total_items[level] += len(items)

            valid = not bool(report[logging.ERROR])
            total_valid = valid and total_valid

            tables.append(
                {
                    'format': frmt,
                    'errors': report[logging.ERROR],
                    'warnings': report[logging.WARNING],
                    'informations': report[logging.INFO],
                    'row-count': self.properties['row-count'],
                    'headers': self.properties['headers'],
                    'source': f'{filename}{table_string}',
                    'time': self.properties['time'],
                    'valid': valid,
                    'scheme': 'file',
                    'encoding': self.properties['encoding'],
                    'schema': None,
                    'item-count': item_count,
                    'error-count': len(report[logging.ERROR]),
                    'warning-count': len(report[logging.ERROR]),
                    'information-count': len(report[logging.ERROR])
                }
            )

        results = {
            'supplementary': supplementary,
            'item-count': sum(total_items.values()),
            'error-count': sum(total_items.values()), # Legacy
            'counts': {
                'errors': total_items[logging.ERROR],
                'warnings': total_items[logging.WARNING],
                'informations': total_items[logging.INFO]
            },
            'valid': total_valid,
            'issues-skipped': skipped,
            'artifacts': artifacts,
            'tables': tables,
            'filename': filename,
            'preset': self.get_preset(),
            'warnings': [],
            'table-count': 1,
            'time': self.properties['time']
        }

        return results

    def add_supplementary(self, typ, source, name):
        logging.warning('Adding supplementary')
        logging.warning((typ, source, name))
        self.supplementary.append({
            'type': typ,
            'source': source,
            'name': name
        })

    def set_properties(self, **properties):
        for arg in self.properties:
            if arg in properties:
                self.properties[arg] = properties[arg]


    def add_issue(self, log_level, code, message, item=None, error_data=None, context=None, at_top=False):
        """This function will add an issue to the report and takes as parameters the processor, the log level, code, message"""

        if log_level not in self.issues:
            raise RuntimeError(_('Log-level must be one of logging.INFO, logging.WARNING or logging.ERROR'))

        if not isinstance(item, ReportItem):
            item = ReportItemLiteral(item)

        issue = ReportIssue(log_level, item=item, context=context, processor=self.processor, code=code, message=message, error_data=error_data)

        self.append_issue(issue, prepend=at_top)

# TODO: fix for multiple tables
def properties_from_report(report):
    table = report['tables'][0]
    return {
        'row-count': table['row-count'],
        'time': report['time'],
        'encoding': table['encoding'],
        'preset': report['preset'],
        'issues-skipped': report['issues-skipped'],
        'headers': table['headers']
    }

def combine_reports(*reports, base=None):
    if base is None:
        presets = {report.preset for report in reports if report.preset}

        if len(presets) != 1:
            raise RuntimeError(
                _("Report combining can only be performed on reports with the same 'preset' property")
            )
        preset = list(presets)[0]
        rcls = get_report_class_from_preset(preset)
        base = rcls(None, None)

    for report in reports:
        base.update(report)

    return base


from .geojson import GeoJSONReport
from .tabular import TabularReport
from .document import DocumentReport

_report_class_from_preset = {
    cls.get_preset(): cls for cls in
    (GeoJSONReport, TabularReport, DocumentReport)
}
