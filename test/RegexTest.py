import re

re_compiled = re.compile('bytes=([0-9]*)\\-([0-9]*)?')

tests = [
    'bytes=1234-5678',
    'bytes=1234-',
]

for t in tests:
    print("Test %s" % t)
    m = re_compiled.search(t)
    g1 = m.group(1)
    print("Group1 = %s" % g1)
    g2 = m.group(2)
    print("Group2 = %s" % g2)
    print('---')


