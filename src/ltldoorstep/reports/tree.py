import itertools
import re
from typing import Union, Optional
from jsonpath_ng import parse as jsonpath_parse
from .report import Report, ReportItem
from ..aspect import Aspect

def _match_to_branch(match):
    branch_path = re.sub(r'\[(\d+)\]', r'[0]', str(match.full_path))
    # TODO: handle . in path names
    layers = branch_path.split('.')
    level = match.value
    for layer in layers[-1::-1]:
        level = [level] if layer == '[0]' else {layer: level}
    return branch_path, level

class TreeReport(Report):

    preset = 'tree'

    # NB: line and character start at _0_
    def add_issue(self, log_level, code, message, json_path=None, content=None,
            error_data=None, at_top=False, tree=None, context_json_path=None):
        """This function will add an issue to the report and takes as parameters the processor, the log level, code, message"""

        report_item_cls = ReportItem

        if isinstance(content, Aspect):
            plaintext_content = content.plaintext
        elif content is not None:
            plaintext_content = str(content)
        else:
            plaintext_content = None

        context = None
        properties = None
        definition = content
        if json_path:
            typ = 'Branch'
            location = {
                'path': str(json_path),
                'branch': None
            }
            if tree:
                match = jsonpath_parse(location['path']).find(tree)[0]
                location['branch'] = _match_to_branch(match)
                if not context_json_path:
                    context_json_path = f'{json_path}.`parent`'
                context_match = jsonpath_parse(context_json_path).find(tree)[0]

                context_location = {
                    'path': str(context_match.full_path),
                    'branch': _match_to_branch(context_match)
                }

                # TODO: better handling
                context = [ReportItem('Branch', context_location, None, None)]
        else:
            typ = 'Global'

        item = report_item_cls(typ, location, definition, properties)

        super(TreeReport, self).add_issue(log_level, code, message, item, error_data=error_data, context=context, at_top=at_top)
