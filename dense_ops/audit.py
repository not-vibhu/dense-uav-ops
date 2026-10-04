"""Signed causal records and independently signed checkpoint anchors.

Verification requires an externally trusted head and public-key registry digest.
Signatures attest record authorship, not navigation truth or legal liability.
"""
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Journal:
    def __init__(self, actors):
        self.keys = {str(a): Ed25519PrivateKey.generate() for a in actors}
        self.witness = Ed25519PrivateKey.generate()
        self.public = {a: k.public_key().public_bytes_raw().hex() for a, k in self.keys.items()}
        self.public['witness'] = self.witness.public_key().public_bytes_raw().hex()
        self.events = []
        self.head = '0'*64
        self.sequence = {a: 0 for a in self.keys}

    def sign(self, actor, payload):
        actor = str(actor)
        body = {'actor': actor, 'payload': payload}
        return dict(body, signature=self.keys[actor].sign(b'dense-ops-message-v1\0'+canonical(body)).hex())

    @staticmethod
    def authenticate(message, public):
        body = {k: message[k] for k in ('actor', 'payload')}
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public[body['actor']])).verify(
            bytes.fromhex(message['signature']), b'dense-ops-message-v1\0'+canonical(body))
        return body['payload']

    def append(self, actor, time, kind, payload):
        actor = str(actor)
        event = {'sequence': self.sequence[actor], 'time': time, 'kind': kind, 'payload': payload, 'parent': self.head}
        signed = self.sign(actor, event)
        self.head = digest(signed)
        self.sequence[actor] += 1
        self.events.append(signed)
        return self.head

    def anchor(self):
        body = dict(head=self.head, count=len(self.events), registry_sha256=digest(self.public))
        return dict(body, witness_signature=self.witness.sign(b'dense-ops-anchor-v1\0'+canonical(body)).hex())


def verify(events, public, trusted_anchor):
    body = {k: trusted_anchor[k] for k in ('head', 'count', 'registry_sha256')}
    if digest(public) != body['registry_sha256']:
        raise ValueError('Untrusted public-key registry')
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public['witness'])).verify(
        bytes.fromhex(trusted_anchor['witness_signature']), b'dense-ops-anchor-v1\0'+canonical(body))
    head = '0'*64
    seq = {}
    for message in events:
        event = Journal.authenticate(message, public)
        actor = message['actor']
        if event['parent'] != head or event['sequence'] != seq.get(actor, 0):
            raise ValueError('Missing, reordered or forked event')
        seq[actor] = seq.get(actor, 0)+1
        head = digest(message)
    if head != body['head'] or len(events) != body['count']:
        raise ValueError('Checkpoint mismatch or missing tail')
    return True
