import unidecode
import chardet

PARAGRAPH_LIMIT = 1000000
def split_into_paragraphs(text):
    line_counter = 0
    paragraphs = []
    counter = 0
    text = unidecode.unidecode(text).replace("'", '')
    text = '\n'.join(line.strip() for line in text.split('\n'))
    remaining_text = text
    while remaining_text.find('\n\n') >= 0 and counter < PARAGRAPH_LIMIT:
        counter += 1
        paragraph = remaining_text[:remaining_text.find('\n\n')]
        paragraphs.append((paragraph, line_counter))
        line_counter += paragraph.count('\n')
        remaining_text = remaining_text[len(paragraph) + 2:]
        line_counter += 2
    if remaining_text:
        paragraphs.append((remaining_text, line_counter))

    return paragraphs

def load_text(filename):
    with open(filename, 'rb') as f:
        result = chardet.detect(f.read(1024))

    encoding = result['encoding']
    if encoding == 'ascii':
        encoding = 'utf-8'

    with open(filename, 'r', encoding=encoding) as text_file:
        text = text_file.read()

    return text

