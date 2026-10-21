"""Publish the reviewed Markdown plan using an existing Git credential helper.

No token is accepted on the command line, printed, or saved by this script.
The stable marker prevents duplicate issues when the command is rerun.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'planning/issues.json'
MAPPING = ROOT / 'planning/github-map.json'


def credentials():
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    result = subprocess.run(
        ['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n\n', text=True,
        capture_output=True, timeout=30, env=environment,
    )
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or not values.get('password'):
        raise RuntimeError('No existing GitHub credential; configure local Git authentication.')
    return values['password']


class GitHub:
    def __init__(self, token, repository):
        self.token = token
        self.base = 'https://api.github.com/repos/' + repository

    def call(self, method, suffix, data=None):
        headers = {
            'Accept': 'application/vnd.github+json',
            'Authorization': 'Bearer ' + self.token,
            'User-Agent': 'MarkeTOB-planning',
            'X-GitHub-Api-Version': '2022-11-28',
        }
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base + suffix, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Do not print headers or potentially private response bodies.
            raise RuntimeError(f'GitHub {method} {suffix}: HTTP {error.code}') from None
        except urllib.error.URLError:
            raise RuntimeError(f'GitHub {method} {suffix}: network error; inspect remote state before retry.') from None

    def issues(self):
        result = []
        page = 1
        while True:
            batch = self.call('GET', f'/issues?state=all&per_page=100&page={page}')
            result.extend(item for item in batch if 'pull_request' not in item)
            if len(batch) < 100:
                return result
            page += 1


def save_map(repository, mapping):
    payload = {'repository': repository, 'issues': mapping}
    temporary = MAPPING.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(MAPPING)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sync', action='store_true', help='Create/update issues from the reviewed local plan.')
    arguments = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    repository = manifest['repository']
    client = GitHub(credentials(), repository)
    metadata = client.call('GET', '')
    print(json.dumps({'repository': metadata['full_name'], 'can_push': metadata.get('permissions', {}).get('push', False)}), flush=True)
    remote = client.issues()
    mapping = {}
    changed = 0
    for entry in manifest['issues']:
        stable_id = entry['id']
        marker = f'<!-- marketob-plan:{stable_id} -->'
        matches = [item for item in remote if marker in (item.get('body') or '')]
        if len(matches) > 1:
            raise RuntimeError(f'Duplicate remote markers for {stable_id}; manual reconciliation required.')
        path = (ROOT / entry['path']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise RuntimeError(f'Invalid source path for {stable_id}')
        body = marker + '\n\n' + path.read_text(encoding='utf-8').strip()
        links = [f'[{dependency}]({mapping[dependency]["url"]})' for dependency in entry['depends_on']]
        body += '\n\n## Связи GitHub\n\n' + (', '.join(links) if links else 'Начальная задача плана.')
        body += f'\n\nИсходный документ: [{entry["path"]}](https://github.com/{repository}/blob/main/{entry["path"]}).\n'
        if not arguments.sync:
            if not matches:
                raise RuntimeError(f'{stable_id} has not been published.')
            item = matches[0]
            if item['title'] != entry['title'] or (item.get('body') or '').strip() != body.strip():
                raise RuntimeError(f'{stable_id} differs from the local source.')
            if entry['status'] == 'done' and item['state'] != 'closed':
                raise RuntimeError(f'{stable_id} is done locally but still open remotely.')
        elif matches:
            item = matches[0]
            needs_close = entry['status'] == 'done' and item['state'] != 'closed'
            if item['title'] != entry['title'] or (item.get('body') or '').strip() != body.strip() or needs_close:
                update = {'title': entry['title'], 'body': body}
                # Only explicit local completion closes an issue; never silently reopen it.
                if needs_close:
                    update.update(state='closed', state_reason='completed')
                item = client.call('PATCH', f'/issues/{item["number"]}', update)
                changed += 1
                time.sleep(1)
        else:
            item = client.call('POST', '/issues', {'title': entry['title'], 'body': body})
            remote.append(item)
            changed += 1
            time.sleep(1)
        mapping[stable_id] = {'number': item['number'], 'url': item['html_url'], 'state': item['state']}
        if arguments.sync:
            save_map(repository, mapping)
        print(f'{stable_id}: {item["html_url"]}', flush=True)
    if arguments.sync:
        rows = ['# GitHub Issues', '', 'Статусы ниже отражают последнюю синхронизацию. Открытая issue не означает готовность к старту; завершённые задачи закрываются после проверки.', '', '| ID | GitHub | Тип | План | GitHub |', '|---|---|---|---|---|']
        for entry in manifest['issues']:
            item = mapping[entry['id']]
            rows.append(f'| {entry["id"]} | [#{item["number"]}]({item["url"]}) | {entry["kind"]} | {entry["status"]} | {item["state"]} |')
        rows += ['', 'Повторная синхронизация: `python scripts/sync_github_plan.py --sync`. Только проверка соответствия: `python scripts/sync_github_plan.py`.', '', 'Используется существующая локальная авторизация Git; скрипт не сохраняет и не выводит токен. Перед публикацией изменённого плана прочитать регламент и проверить Markdown.']
        (ROOT / 'docs/GITHUB_ISSUES.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(json.dumps({'verified': len(mapping), 'changed': changed}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
