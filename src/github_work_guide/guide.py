"""Deterministic reading of Issue/PR text for work guidance (no model, no network).

Only recognises existing headings, label lines and references, and quotes exact source excerpts.
It never turns prose into a confirmed dependency, a completion or an approval.
"""
import re

SECTIONS = (
    ('goal', ('goal', '目的', '目標')),
    ('scope', ('scope', '作業', '範囲', '対象範囲')),
    ('done', ('done', '完了条件', 'acceptance criteria', '受入条件')),
    ('verification', ('verification', '検証')),
    ('dependencies', ('dependencies', '依存')),
    ('non_goals', ('non-goals', 'non goals', '対象外')),
    ('boundaries', ('boundaries', '境界')),
    ('context', ('context', '背景')),
)
LABELS = {'goal': '目的/Goal', 'scope': '作業/Scope', 'done': '完了条件/Done', 'verification': '検証/Verification',
          'dependencies': '依存/Dependencies', 'non_goals': '対象外/Non-goals', 'boundaries': '境界/Boundaries',
          'context': '背景/Context'}
EXPECTED = ('goal', 'scope', 'done', 'verification', 'dependencies', 'non_goals')
NONE_WORDS = {'none', 'なし', '依存なし', 'n/a'}
QUOTE_LIMIT = 300
NAME_SCORE = 0.3  # share of a dependency term's tokens found in an Issue title; a hint, never a decision

FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
HEADING = re.compile(r'^\s{0,3}(#{1,6})[ \t]+(.*?)[ \t#]*$')
LABEL = re.compile(r'^\s*(?:[-*]\s+)?(依存|dependencies|depends on)\s*[:：]\s*(.*?)\s*$', re.I)
URL = re.compile(r'https://github\.com/([\w.-]+/[\w.-]+)(?:/(issues|pull)/(\d+))?[A-Za-z0-9_./%#?=&+~:@!$,;-]*')
QUALIFIED = re.compile(r'(?<![\w.-])([\w.-]+/[\w.-]+)#(\d+)(?!\d)')
SHORT = re.compile(r'(?<![\w.&-])#(\d+)(?!\d)')
KEYWORD = re.compile(r'(?i)(\b(refs?|related(?: to)?|part of|close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b|関連)\s*[:：]?\s*$')
CHECKBOX = re.compile(r'^\s*[-*]\s+\[([ xX])\]')
TIME = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ')


def canonical(heading):
    norm = heading.strip().strip(':：').strip().lower()
    for name, aliases in SECTIONS:
        for alias in aliases:
            if norm == alias or (norm.startswith(alias) and norm[len(alias)] in ' /（(:：'):
                return name
    return None


class Text:
    """One source text (body or comment) with exact line offsets for quoting."""

    def __init__(self, owner, where, text):
        self.owner, self.where, self.text = owner, where, text
        self.lines = text.split('\n')
        self.offsets, pos = [], 0
        for line in self.lines:
            self.offsets.append(pos)
            pos += len(line) + 1
        self.headings, self.fenced = [], set()
        fence = None  # opening marker; a block closes only with the same character, at least as long, and nothing after
        for i, line in enumerate(self.lines):
            m = FENCE.match(line.rstrip('\r'))
            if fence is None and m and not (m.group(1)[0] == '`' and '`' in m.group(2)):
                fence = m.group(1)
                self.fenced.add(i)
                continue
            if fence is not None:
                self.fenced.add(i)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                    fence = None
                continue
            m = HEADING.match(line.rstrip('\r'))
            if m:
                self.headings.append((i, len(m.group(1)), m.group(2)))

    def prefix(self):
        return self.owner if self.where == 'body' else f'{self.owner}:{self.where}'

    def excerpt(self, start, end):
        """Lines start..end-1 as an exact substring, capped at QUOTE_LIMIT characters."""
        end = max(start + 1, end)
        text = '\n'.join(self.lines[start:end])
        while end - start > 1 and not self.lines[end - 1].strip():
            end -= 1
            text = '\n'.join(self.lines[start:end])
        label = f'{self.prefix()}:L{start + 1}' + (f'-L{end}' if end - start > 1 else '')
        return evidence_entry(label, text[:QUOTE_LIMIT], len(text) > QUOTE_LIMIT)

    def window(self, line, begin, finish):
        """Part of one line around a match (exact substring)."""
        text = self.lines[line]
        a, b = max(0, begin - 100), min(len(text), finish + 60)
        return evidence_entry(f'{self.prefix()}:L{line + 1}:{a + 1}', text[a:b], a > 0 or b < len(text))


def evidence_entry(label, quote, truncated):
    return {'id': label, 'quote': quote, 'truncated': truncated}


def sections(text):
    result = []
    for index, (line, level, heading) in enumerate(text.headings):
        end = text.headings[index + 1][0] if index + 1 < len(text.headings) else len(text.lines)
        parent = next((h for h in reversed(text.headings[:index]) if h[1] < level), None)
        result.append({'name': canonical(heading), 'line': line, 'end': end, 'heading': heading,
                       'parent': parent[0] if parent else None,
                       'content': '\n'.join(text.lines[line + 1:end]).strip()})
    return result


def labels(text, found):
    inside = {i for s in found if s['name'] == 'dependencies' for i in range(s['line'], s['end'])}
    result = []
    for i, line in enumerate(text.lines):
        if i in text.fenced or i in inside:
            continue
        m = LABEL.match(line.rstrip('\r'))
        if m:
            result.append({'line': i, 'value': m.group(2)})
    return result


def references(text, repo):
    """Same-repo references and other-repo URLs, each with the exact line they come from."""
    internal, external = [], []
    for i, line in enumerate(text.lines):
        if i in text.fenced:
            continue
        masked = line
        for m in URL.finditer(line):
            masked = masked[:m.start()] + ' ' * (m.end() - m.start()) + masked[m.end():]
            if m.group(1) == repo and m.group(3):
                internal.append(ref(text, i, m, 'pr' if m.group(2) == 'pull' else 'issue', int(m.group(3)), line))
            elif m.group(1) != repo:
                external.append({'url': m.group(0).rstrip('.,;:。、'), 'repo': m.group(1),
                                 'evidence': text.window(i, m.start(), m.end())})
        for m in QUALIFIED.finditer(masked):
            masked = masked[:m.start()] + ' ' * (m.end() - m.start()) + masked[m.end():]
            if m.group(1) == repo:
                internal.append(ref(text, i, m, None, int(m.group(2)), line))
            else:
                external.append({'url': m.group(0), 'repo': m.group(1), 'evidence': text.window(i, m.start(), m.end())})
        for m in SHORT.finditer(masked):
            internal.append(ref(text, i, m, None, int(m.group(1)), line))
    return internal, external


def ref(text, line, match, kind, number, source):
    keyword = KEYWORD.search(source[:match.start()][-40:]) is not None
    return {'kind': kind, 'number': number, 'line': line, 'relation': 'refs' if keyword else 'mention',
            'evidence': text.window(line, match.start(), match.end())}


def resolve(items, kind, number):
    if kind:
        key = f'{kind}:{number}'
        return key if key in items else f'#{number}'
    for key in (f'issue:{number}', f'pr:{number}'):
        if key in items:
            return key
    return f'#{number}'


def tokens(text):
    lowered = text.lower()
    words = set(re.findall(r'[a-z][a-z0-9]{2,}', lowered))
    grams = set()
    for chunk in re.findall(r'[^\x00-\x7f、。・，（）「」／：]+', lowered):
        grams |= {chunk[i:i + 2] for i in range(len(chunk) - 1)}
    return words | grams


def name_candidates(term, items, own):
    wanted = tokens(term)
    if not wanted:
        return []
    scored = []
    for key, item in items.items():
        if item['kind'] != 'issue' or key == own:
            continue
        common = wanted & tokens(item['title'])
        score = len(common) / len(wanted)
        if score >= NAME_SCORE:
            scored.append((-score, item['number'], key, sorted(common)))
    return [{'target': key, 'state': items[key]['state'], 'score': round(-s, 2), 'matched': common,
             'confirmed': False} for s, _, key, common in sorted(scored)[:3]]


def dependency_value(value):
    """Return (numbers, None) when the text is only refs or 'none'; (None, terms) for prose."""
    text = re.sub(r'(?im)^\s*[-*]\s*depends-on:\s*', '', value).strip()
    if text.strip(' 。.').lower() in NONE_WORDS:
        return [], None
    numbers = [int(x) for x in SHORT.findall(text)]
    rest = SHORT.sub(' ', text)
    # A PR named as a dependency ("PR #25") stays prose: confirmed numbers are resolved as issues only.
    rest = re.sub(r'(?i)\b(issues?|and)\b', ' ', rest)
    if numbers and not re.sub(r'[\s、,，/／・;；\-*と及び。.]+', '', rest):
        return sorted(set(numbers)), None
    terms = [t.strip(' \t\r-*。.') for t in re.split(r'[、,，;；\n]', value)]
    return None, [t for t in terms if t]


def subtree_end(text, section):
    """End of a section including its plain subheadings (### Backend); another named section ends it."""
    level = next(lv for line, lv, _ in text.headings if line == section['line'])
    for line, lv, heading in text.headings:
        if line > section['line'] and (lv <= level or canonical(heading) is not None):
            return line
    return len(text.lines)


def subtree_content(text, section):
    return '\n'.join(text.lines[section['line'] + 1:subtree_end(text, section)]).strip()


def done_counts(text, section):
    start = section['line'] + 1
    marks = [CHECKBOX.match(line) for i, line in enumerate(text.lines[start:subtree_end(text, section)], start)
             if i not in text.fenced]  # checklist examples in code blocks are not conditions
    marks = [m.group(1) for m in marks if m]
    return sum(m in 'xX' for m in marks), len(marks)


def valid_time(value):
    return value if isinstance(value, str) and TIME.fullmatch(value) else None
