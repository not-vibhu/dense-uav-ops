"""Fetch NASA DAIDALUS at a pinned revision and build this repository's streaming bridge.

DAIDALUS is NASA software under the NASA Open Source Agreement. It is cloned into
the ignored artifacts/ directory and linked into a local binary; neither its
source nor the binary is part of this repository's MIT-licensed code.

Usage: python scripts/build_daidalus.py
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    pins = json.loads((ROOT / 'integrations/daidalus/pins.json').read_text())
    checkout = ROOT / 'artifacts/upstream/daidalus'
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not checkout.exists():
        subprocess.run(['git', 'clone', '--no-checkout', 'https://github.com/nasa/daidalus.git', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'checkout', '--detach', pins['daidalus']], check=True)
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if head != pins['daidalus']:
        raise SystemExit(f'{checkout} is at {head}, not the pinned {pins["daidalus"]}')
    subprocess.run(['make', '-j4', 'lib'], cwd=checkout / 'C++', check=True)
    out = ROOT / 'artifacts/daidalus'
    out.mkdir(parents=True, exist_ok=True)
    binary = out / 'daidalus-bridge'
    bridge = ROOT / 'integrations/daidalus/bridge.cpp'
    subprocess.run(['c++', '-std=c++14', '-O2', '-I' + str(checkout / 'C++/include'), str(bridge),
                    str(checkout / 'C++/lib/DAIDALUS2.a'), '-o', str(binary)], check=True)
    configuration = ROOT / pins['configuration']
    manifest = dict(daidalus=pins['daidalus'], license=pins['license'], binary=str(binary),
                    binary_sha256=sha256(binary), bridge_sha256=sha256(bridge),
                    configuration=str(configuration), configuration_sha256=sha256(configuration))
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(out / 'manifest.json')


if __name__ == '__main__':
    main()
