"""Publish a small bootstrap and immutable per-sector history files."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_web_data():
    output = ROOT / 'outputs'
    data = json.loads((output / 'sector_real_data.json').read_text(encoding='utf-8'))
    directory = output / 'sector-history'
    directory.mkdir(exist_ok=True)
    manifest = {}
    metrics = {}
    for name, metric in data['metrics'].items():
        text = json.dumps(metric, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        filename = f'{data["codes"][name]}.{digest}.json'
        (directory / filename).write_text(text, encoding='utf-8')
        manifest[name] = f'sector-history/{filename}'
        metrics[name] = metric if name == '电子' else {'latest': metric['latest']}
    data['metrics'] = metrics
    data['historyFiles'] = manifest
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    (output / 'sector_web_data.js').write_text('window.SECTOR_REAL_DATA = ' + text + ';\n', encoding='utf-8')
    page = output / 'index.html'
    html = re.sub(r'(sector_web_data\.js\?v=)[^"\s]+',
                  lambda m: m[1] + hashlib.sha256(text.encode()).hexdigest()[:12],
                  page.read_text(encoding='utf-8'))
    page.write_text(html, encoding='utf-8')
    print(f'Web bootstrap: {len(text.encode()):,} bytes; {len(manifest)} lazy histories')


if __name__ == '__main__':
    build_web_data()
