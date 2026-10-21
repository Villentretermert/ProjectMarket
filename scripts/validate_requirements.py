"""Check PM-001 traceability; this does not run product acceptance tests."""

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def main():
    requirements = json.loads((ROOT / 'planning/requirements.json').read_text(encoding='utf-8'))['requirements']
    tasks = json.loads((ROOT / 'planning/issues.json').read_text(encoding='utf-8'))['issues']
    task_ids = {item['id'] for item in tasks}
    matrix = (ROOT / 'docs/requirements/ACCEPTANCE_MATRIX.md').read_text(encoding='utf-8')
    stories = (ROOT / 'docs/requirements/USER_STORIES.md').read_text(encoding='utf-8')
    story_ids = set(re.findall(r'^## (US\d+) ', stories, re.MULTILINE))
    seen, questions, errors = set(), set(), []
    for requirement in requirements:
        key = requirement['id']
        if key in seen:
            errors.append(f'Duplicate requirement: {key}')
        seen.add(key)
        questions.update(re.findall(r'Q\d{2}', requirement['source']))
        if requirement['story'] not in story_ids:
            errors.append(f'{key}: missing story')
        if not requirement['tasks'] or not set(requirement['tasks']) <= task_ids:
            errors.append(f'{key}: invalid task references')
        if not requirement['scenario'].strip() or f'| {key} |' not in matrix:
            errors.append(f'{key}: missing scenario or matrix row')
        if requirement['status'] != 'specified':
            errors.append(f'{key}: PM-001 cannot certify unimplemented product acceptance')
    expected_questions = {f'Q{i:02}' for i in range(1, 18)}
    if not expected_questions <= questions:
        errors.append(f'Missing question coverage: {sorted(expected_questions - questions)}')
    if len(requirements) != 30 or len(story_ids) != 16:
        errors.append('Expected 30 requirements and 16 stories')
    for source in [ROOT / 'README.md', *sorted((ROOT / 'docs').rglob('*.md'))]:
        for target in re.findall(r'\]\(([^)]+)\)', source.read_text(encoding='utf-8')):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            if not (source.parent / target.split('#')[0]).exists():
                errors.append(f'Broken local link in {source.relative_to(ROOT)}: {target}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(json.dumps({'result': 'PASS', 'requirements': len(requirements), 'stories': len(story_ids), 'questions_covered': len(expected_questions), 'product_tests_run': False}))


if __name__ == '__main__':
    main()
