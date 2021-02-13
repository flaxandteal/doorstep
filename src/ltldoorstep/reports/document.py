import itertools
from typing import Union, Optional
from .report import Report, ReportItem
from ..aspect import Aspect

class DocumentReport(Report):

    preset = 'document'

    # NB: line and character start at _0_
    def add_issue(self, log_level, code, message, line_number=None, character_number=None, line_to_number=None, character_to_number=None,
            snippet: Optional[str] = None, error_data=None, at_top=False, content: Union[Aspect, str, None] = None):
        """This function will add an issue to the report and takes as parameters the processor, the log level, code, message"""

        report_item_cls = ReportItem

        if isinstance(content, Aspect):
            plaintext_content = content.plaintext
        elif content is not None:
            plaintext_content = str(content)
        elif snippet is not None:
            plaintext_content = str(snippet)
        else:
            plaintext_content = None

        if line_number is not None and line_to_number is None:
            line_to_number = line_number
            if plaintext_content:
                line_to_number += plaintext_content.count('\n')
        if character_number is not None and character_to_number is None and plaintext_content is not None:
            if plaintext_content.rfind('\n') > -1:
                character_to_number = len(plaintext_content) - plaintext_content.rfind('\n')
            else:
                character_to_number = character_number + len(plaintext_content)

        location = {
            'from': {'line': line_number, 'character': character_number},
            'to' :{'line': line_to_number, 'character': character_to_number}
        }

        context = None
        properties = None
        definition = None
        if line_number is not None:
            if character_number is not None:
                typ = 'Span'
                definition = content
                if None not in (snippet, content, line_number, character_number):
                    try:
                        offset = snippet.index(plaintext_content)
                    except ValueError:
                        raise RuntimeError(
                            'Issue added for document report where the content did ' +
                            'not appear in the provided contextual snippet'
                        )

                    before = snippet[:offset]
                    before_line = line_number - before.count('\n'),
                    # TODO: no support for special chars here
                    before_character = character_number - len(before)
                    if before.rfind('\n') > -1:
                        before_character += before.rfind('\n')

                    after = snippet[offset + len(plaintext_content):]
                    after_line = line_to_number + after.count('\n')
                    # TODO: no support for special chars here
                    if after.rfind('\n') > -1:
                        after_character = len(after) - after.rfind('\n')
                    else:
                        after_character = character_to_number + len(after)

                    context_location = {
                        'from': {
                            'line': before_line,
                            'character': before_character
                        },
                        'to': {
                            'line': after_line,
                            'character': after_character
                        }
                    }
                    context = [ReportItem('Span', context_location, snippet, None)]
            else:
                typ = 'Line'
                definition = content
        else:
            typ = 'Global'
            definition = content

        item = report_item_cls(typ, location, definition, properties)

        super(DocumentReport, self).add_issue(log_level, code, message, item, error_data=error_data, context=context, at_top=at_top)
