import json, hashlib, base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_hex(data):
    if not isinstance(data, (bytes, bytearray)):
        data = canonical_json(data)
    return hashlib.sha256(data).hexdigest()

def proposal_digest(proposal):
    normalized = {
        "dossierId": proposal["dossierId"],
        "callId": proposal["callId"],
        "action": proposal["action"],
        "target": proposal.get("target"),
        "payload": proposal["payload"],
        "evidence": sorted(proposal["evidence"])
    }
    return sha256_hex(canonical_json(normalized))

def verify_receipt(evaluation_id, input_digest, receipt, public_jwk):
    try:
        raw = base64.urlsafe_b64decode(public_jwk["x"] + "=" * (-len(public_jwk["x"]) % 4))
        public_key = Ed25519PublicKey.from_public_bytes(raw)
        signed_receipt = {k:v for k,v in receipt.items() if k != "receiptSignature"}
        signed_object = {
            "profile": "ga5-mailroom-action-gate/v2",
            "evaluationId": evaluation_id,
            "inputDigest": input_digest,
            "receipt": signed_receipt
        }
        signature = base64.b64decode(receipt["receiptSignature"], validate=True)
        public_key.verify(signature, canonical_json(signed_object))
        return True
    except Exception:
        return False
