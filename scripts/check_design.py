"""Verify actual prototype color tokens and record contrast evidence, not full WCAG certification."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def luminance(hex_color):
    value = hex_color.lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    rgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb]
    return sum(x * weight for x, weight in zip(linear, (.2126, .7152, .0722)))


def main():
    css = (ROOT / 'design/prototype/styles.css').read_text(encoding='utf-8')
    root = css.split('}', 1)[0]
    colors = dict(re.findall(r'--([a-z]+):(#[0-9a-fA-F]{3,6})', root))
    pairs = [('text', 'panel'), ('text', 'bg'), ('muted', 'panel'), ('muted', 'bg'),
             ('panel', 'accent'), ('accent', 'soft'), ('success', 'panel'), ('danger', 'panel')]
    results = []
    for foreground, background in pairs:
        light, dark = sorted([luminance(colors[foreground]), luminance(colors[background])], reverse=True)
        ratio = (light + .05) / (dark + .05)
        results.append({'foreground': colors[foreground], 'background': colors[background], 'ratio': round(ratio, 2), 'pass': ratio >= 4.5})
    # Secondary theme, warning banner and keyboard focus have explicit colors.
    for foreground, background, minimum in [('#213247','#eaf0f8',4.5),('#253e60','#dce5f3',4.5),('#825414','#fff5df',4.5),('#a5630c','#ffffff',3)]:
        light, dark = sorted([luminance(foreground), luminance(background)], reverse=True)
        ratio = (light + .05) / (dark + .05)
        results.append({'foreground':foreground,'background':background,'ratio':round(ratio,2),'minimum':minimum,'pass':ratio>=minimum})
    payload = {'result':'PASS' if all(x['pass'] for x in results) else 'FAIL','checks':results,'scope':'Static color pairs; browser keyboard/touch/layout checks are recorded separately.'}
    target = ROOT / 'docs/task-results/assets/PM-003/contrast.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload))
    if payload['result'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
