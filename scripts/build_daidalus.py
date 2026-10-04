"""Fetch an immutable official NASA revision and build the original bridge."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    pins = json.loads((ROOT/'integrations/daidalus/pins.json').read_text())
    checkout = ROOT/'artifacts/upstream/daidalus'
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not checkout.exists():
        subprocess.run(['git', 'clone', '--no-checkout', 'https://github.com/nasa/daidalus.git', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'checkout', '--detach', pins['daidalus']], check=True)
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if head != pins['daidalus']:
        raise ValueError('Existing checkout differs from pin; prepare the pinned revision explicitly')
    subprocess.run(['make', '-j4', 'lib'], cwd=checkout/'C++', check=True)
    out = ROOT/'artifacts/nasa'
    out.mkdir(parents=True, exist_ok=True)
    binary = out/'daidalus-bridge'
    subprocess.run(['c++', '-std=c++11', '-O2', '-I'+str(checkout/'C++/include'),
                    str(ROOT/'integrations/daidalus/bridge.cpp'), str(checkout/'C++/lib/DAIDALUS2.a'),
                    '-o', str(binary)], check=True)
    config = checkout/pins['configuration']
    manifest = dict(pins, binary=str(binary), configuration_path=str(config),
                    binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                    configuration_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                    bridge_sha256=hashlib.sha256((ROOT/'integrations/daidalus/bridge.cpp').read_bytes()).hexdigest())
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(out/'manifest.json')


if __name__ == '__main__':
    main()
