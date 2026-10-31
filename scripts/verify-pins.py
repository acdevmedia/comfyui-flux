"""Check every pinned model against Hugging Face's authoritative LFS hashes.

check-source.py can only see that a checksum is shaped like one. This asks Hugging Face what the
file at the pinned revision really is, so a wrong SHA256 or size is caught in CI instead of as a
crash loop on a paid Pod, where the downloader fetches the whole file, rejects it, restarts and
fetches it again.

    python3 scripts/verify-pins.py          verify every profile, exit 1 on any mismatch
    python3 scripts/verify-pins.py --fix    rewrite sha256 and size from Hugging Face
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r'[0-9a-f]{64}')
TOKEN = os.environ.get('HF_TOKEN', '').strip()
if TOKEN.startswith(('{{', 'YOUR_')):
    TOKEN = ''


def request(url):
    headers = {'User-Agent': 'acdev-verify-pins'}
    if TOKEN:
        headers['Authorization'] = 'Bearer ' + TOKEN
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90)


def tree(repo, revision):
    """path -> (sha256, size) for every file at a revision, following pagination."""
    files, url = {}, f'https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=1&expand=1'
    while url:
        response = request(url)
        for entry in json.load(response):
            lfs = entry.get('lfs') or {}
            files[entry['path']] = (lfs.get('oid'), lfs.get('size') or entry.get('size'))
        link = response.headers.get('Link') or ''
        url = link.split('<')[1].split('>')[0] if 'rel="next"' in link else None
    return files


def profiles():
    found = sorted(ROOT.glob('versions/*/profile.json'))
    top = ROOT / 'config/profile.json'
    return found + ([top] if top.exists() else [])


def main():
    fix = '--fix' in sys.argv
    cache, bad, skipped = {}, 0, 0
    for path in profiles():
        profile = json.loads(path.read_text())
        changed = False
        for model in profile.get('models', []):
            key = (model['repo'], model['revision'])
            if key not in cache:
                cache[key] = tree(*key)
            sha, size = cache[key].get(model['file'], (None, None))
            # A pin must always be a real SHA256, whatever Hugging Face says today.
            if not HEX64.fullmatch(model['sha256']):
                print('INVALID  %s: %s pins %r, which is not a SHA256' % (path.relative_to(ROOT), model['destination'], model['sha256']))
                bad += 1
                continue
            if sha is None:
                print('MISSING  %s: %s is not at %s@%s' % (path.relative_to(ROOT), model['file'], *key))
                bad += 1
                continue
            if not HEX64.fullmatch(sha):
                # Gated repositories mask hashes from anonymous callers. Never trust or write that.
                print('SKIPPED  %s: %s cannot be verified (Hugging Face returned %r); set HF_TOKEN '
                      'for an account that accepted the gate' % (path.relative_to(ROOT), model['destination'], sha))
                skipped += 1
                continue
            if (sha, size) == (model['sha256'], model['size']):
                continue
            print('%s  %s: %s\n         pinned %s (%s bytes)\n         actual %s (%s bytes)' % (
                'FIXED  ' if fix else 'MISMATCH', path.relative_to(ROOT), model['destination'],
                model['sha256'], model['size'], sha, size))
            if fix:
                model['sha256'], model['size'] = sha, size
                changed = True
            else:
                bad += 1
        if fix and changed:
            path.write_text(json.dumps(profile, indent=2) + '\n')
    if bad:
        raise SystemExit('%d pin(s) do not match Hugging Face' % bad)
    print('PASS: every verifiable pin matches Hugging Face (%d repositories checked%s)' % (
        len(cache), ', %d skipped as unverifiable without a token' % skipped if skipped else ''))


if __name__ == '__main__':
    main()
