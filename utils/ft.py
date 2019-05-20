from gensim.models import FastText as ft
model=ft.load_fasttext_format("wiki.en.bin")

with open('ted_topics', 'r') as tt:
    topics = tt.readlines()

topics = [t.strip().split(' ') for t in topics]
 'topics',
 "for t in topics: print(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity']))",
 "[(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics]",
 "[(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics].sort(key=lambda x: x[0])",
 "sorted([(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics], key=lambda x: x[0])",
 "sorted([(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics], key=lambda x: x[0], reverse=True)",
 "sorted([(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics], key=lambda x: x[1], reverse=True)",
 "sorted([(t, model.wv.n_similarity(t, ['a', 'nasty', 'insanity'])) for t in topics], key=lambda x: x[1], reverse=False)",
 "test = lambda sentence: sorted([(t, model.wv.n_similarity(t, sentence.split(' '))) for t in topics], key=lambda x: x[1], reverse=False)",
 "test('walking around a park')",
 "test('talking to the flowers')",
 "test('dispensing physicians')",
 "with open('/tmp/test.csv', 'r') as tc:\n    tcl = tc.readlines()\n    ",
 "tx = ' '.join(tcl).replace(',', ' ')",
 'tx',
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 'tx',
 "re_num = re.compile('\\d*')",
 'import re',
 "re_num = re.compile('\\d*')",
 "re_num.sub('', tx)",
 "re_ws = re.compile('\\s+')",
 "re_ws.sub(' ', tx)",
 "re_num(re_ws.sub(' ', tx))",
 "re_num(re_ws.sub(' ', tx)[0])",
 "re_num(re_ws.sub(' ', tx).group(0))",
 "re_num.sub('', re_ws.sub(' ', tx))",
 "re_ws.sub(' ', re_num.sub('', tx))",
 "test(re_ws.sub(' ', re_num.sub('', tx)))",
 "test(re_ws.sub(' ', re_num.sub('', tx))).replace(' A ', '')",
 "re_ws.sub(' ', re_num.sub('', tx))",
 "re_sw = re.compile(r'\\b\\w\\b')",
 "re_ws.sub('', re_ws.sub(' ', re_num.sub('', tx)))",
 "re_sw = re.compile(r'\\bA\\b')",
 "re_ws.sub('', re_ws.sub(' ', re_num.sub('', tx)))",
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 "re_ws.sub('', re_ws.sub(' ', re_num.sub('', tx)))",
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 'tx',
 "re_ws.sub('', re_sw.sub(' ', re_num.sub('', tx)))",
 "re_ws.sub(' ', re_ws.sub('', re_num.sub('', tx)))",
 "re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 "re_sw = re.compile(r'\\b\\w\\b')",
 "re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'test(asdf)',
 'sadf',
 'asdf',
 "re_num = re.compile('[^\\w\\s]')",
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'asdf',
 "re_num = re.compile('[^A-Za-z\\s]')",
 'asdf',
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'asdf',
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx))).strip()",
 'asdf',
 'test(asdf)',
 'In']


 "re_ws.sub('', re_ws.sub(' ', re_num.sub('', tx)))",
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 "re_ws.sub('', re_ws.sub(' ', re_num.sub('', tx)))",
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 'tx',
 "re_ws.sub('', re_sw.sub(' ', re_num.sub('', tx)))",
 "re_ws.sub(' ', re_ws.sub('', re_num.sub('', tx)))",
 "re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 "re_sw = re.compile(r'\\b\\w\\b')",
 "re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'test(asdf)',
 'sadf',
 'asdf',
 "re_num = re.compile('[^\\w\\s]')",
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'asdf',
 "re_num = re.compile('[^A-Za-z\\s]')",
 'asdf',
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx)))",
 'asdf',
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx))).strip()",
 'asdf',
 'test(asdf)',
 'In',
 "with open('/tmp/test.csv', 'r') as tc:\n    \n    tcl = tc.readlines()\n    \n    ",
 "tx = ' '.join(tcl).replace(',', ' ').replace('\\n', ' ')",
 "asdf = re_ws.sub(' ', re_sw.sub('', re_num.sub('', tx))).strip()",
 'asdf',
 'test(asdf)',
 "with open('/tmp/test.csv', 'r') as tc:\n    \n    tcl = tc.readlines()\n    \n    ",
 "for line in tcl:.replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl: .replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl: .replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl: .replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl: tc = line.replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl: tc = line.replace(',', ' ').replace('\\n', ' ')",
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip())))\n    ",
 'n = 0',
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip())))\n    ",
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip()))[-1])\n    \n    ",
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, line, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip()))[-1])\n    \n    \n    ",
 'test("Prisons in Northern Ireland")',
 'test("Prisons")',
 'model.most_similar("Prisons")',
 'model.most_similar("prisons")',
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, line, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip()).lower())[-1])\n    \n    \n    \n    ",
 'model.most_similar("Careers")',
 'model.most_similar("careers")',
 "for line in tcl:\n    line = line.replace(',', ' ').replace('\\n', ' ')\n    n += 1\n    print(n, line, test(re_ws.sub(' ', re_sw.sub('', re_num.sub('', line)).strip()).lower())[-1])\n    ",
 'In']


