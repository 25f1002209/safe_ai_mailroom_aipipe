import os, json, hashlib, re
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from asgiref.wsgi import WsgiToAsgi
from database import init_db, get_db, transaction
from decision_engine import make_proposal
from security import canonical_json, sha256_hex, proposal_digest, verify_receipt

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_REQUEST_BYTES", "524288"))
ASGI_APP = WsgiToAsgi(app)
PROFILE = "ga5-mailroom-action-gate/v2"
ALLOWED = {"create_draft", "update_internal_record", "send_approved_notice",
           "request_confirmation", "quarantine_item", "no_action"}

@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "request_too_large"}), 413

def bad(message, code=400):
    return jsonify({"error": message}), code

def is_obj(x):
    return isinstance(x, dict)

def validate_propose(body):
    if not is_obj(body) or body.get("profile") != PROFILE or body.get("operation") != "propose":
        raise ValueError("invalid_propose_envelope")
    for key in ("evaluationId", "receiptVerifier", "corpus", "allowedActions", "dossiers"):
        if key not in body:
            raise ValueError("missing_" + key)
    if not isinstance(body["evaluationId"], str) or not body["evaluationId"]:
        raise ValueError("invalid_evaluationId")
    rv = body["receiptVerifier"]
    if not is_obj(rv) or rv.get("algorithm") != "Ed25519" or not is_obj(rv.get("publicKeyJwk")):
        raise ValueError("invalid_receiptVerifier")
    jwk = rv["publicKeyJwk"]
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519" or not isinstance(jwk.get("x"), str):
        raise ValueError("invalid_public_key_jwk")
    if not isinstance(body["allowedActions"], list) or not set(body["allowedActions"]).issubset(ALLOWED):
        raise ValueError("invalid_allowedActions")
    ds = body["dossiers"]
    if not isinstance(ds, list) or not ds:
        raise ValueError("invalid_dossiers")
    ids = []
    for d in ds:
        if not is_obj(d) or not isinstance(d.get("dossierId"), str) or not d["dossierId"]:
            raise ValueError("invalid_dossier")
        ids.append(d["dossierId"])
        if not isinstance(d.get("sources"), list):
            raise ValueError("invalid_sources")
        line_ids = []
        for s in d["sources"]:
            if not is_obj(s) or not isinstance(s.get("lines"), list):
                raise ValueError("invalid_source")
            for line in s["lines"]:
                if not is_obj(line) or not isinstance(line.get("lineId"), str) or not isinstance(line.get("text"), str):
                    raise ValueError("invalid_line")
                line_ids.append(line["lineId"])
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("duplicate_line_ids")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_dossier_ids")
    return ds

def validate_proposal(p, dossier, allowed):
    if not is_obj(p):
        raise ValueError("model_proposal_not_object")
    required = {"dossierId", "callId", "action", "target", "payload", "evidence"}
    if set(p) != required:
        raise ValueError("proposal_fields_mismatch")
    if p["dossierId"] != dossier["dossierId"] or p["action"] not in allowed:
        raise ValueError("proposal_identity_or_action_invalid")
    if not isinstance(p["callId"], str) or not re.fullmatch(r"[A-Za-z0-9._:-]{12,128}", p["callId"]):
        raise ValueError("invalid_callId")
    if not isinstance(p["evidence"], list) or not p["evidence"] or len(p["evidence"]) != len(set(p["evidence"])):
        raise ValueError("invalid_evidence")
    known = {ln["lineId"] for src in dossier["sources"] for ln in src["lines"]}
    if any(x not in known for x in p["evidence"]):
        raise ValueError("unknown_evidence_line")
    if not isinstance(p["payload"], dict):
        raise ValueError("invalid_payload")
    if p["action"] == "no_action":
        if p["target"] is not None or set(p["payload"]) != {"reasonCode", "referenceId"}:
            raise ValueError("invalid_no_action_schema")
        if p["payload"]["reasonCode"] not in {"ALREADY_COMPLETED", "DUPLICATE", "INFORMATIONAL"}:
            raise ValueError("invalid_no_action_reason")
    elif p["action"] == "create_draft":
        if not isinstance(p["target"], dict) or set(p["target"]) != {"kind","id"} or p["target"]["kind"] != "draft_queue":
            raise ValueError("invalid_draft_target")
        if set(p["payload"]) != {"recipient","referenceId","status","template"} or p["payload"]["template"] != "order_status":
            raise ValueError("invalid_draft_payload")
    elif p["action"] == "update_internal_record":
        if not isinstance(p["target"], dict) or set(p["target"]) != {"kind","id"} or p["target"]["kind"] != "case_record":
            raise ValueError("invalid_record_target")
        if set(p["payload"]) != {"field","sourceEventId","value"} or p["payload"]["field"] != "delivery_window":
            raise ValueError("invalid_record_payload")
    elif p["action"] == "send_approved_notice":
        if not isinstance(p["target"], dict) or set(p["target"]) != {"kind","id"} or p["target"]["kind"] != "email":
            raise ValueError("invalid_email_target")
        if set(p["payload"]) != {"referenceId","status","template"} or p["payload"]["template"] != "approved_delivery_notice":
            raise ValueError("invalid_notice_payload")
    elif p["action"] == "request_confirmation":
        if not isinstance(p["target"], dict) or set(p["target"]) != {"kind","id"} or p["target"]["kind"] != "approval_queue":
            raise ValueError("invalid_approval_target")
        if set(p["payload"]) != {"claimedSender","questionCode","referenceId"} or p["payload"]["questionCode"] != "VERIFY_REQUEST":
            raise ValueError("invalid_confirmation_payload")
    elif p["action"] == "quarantine_item":
        if not isinstance(p["target"], dict) or set(p["target"]) != {"kind","id"} or p["target"] != {"kind":"security_queue","id":"mailroom"}:
            raise ValueError("invalid_quarantine_target")
        if set(p["payload"]) != {"artifactId","reasonCode"} or p["payload"]["reasonCode"] != "INDIRECT_PROMPT_INJECTION":
            raise ValueError("invalid_quarantine_payload")
    return p

@app.post("/")
@app.post("/v1/mailroom/actions")
def mailroom():
    if request.mimetype != "application/json":
        return bad("content_type_must_be_application_json", 415)
    body = request.get_json(silent=True)
    if not is_obj(body):
        return bad("malformed_json")
    try:
        if body.get("profile") != PROFILE:
            raise ValueError("invalid_profile")
        if body.get("operation") == "propose":
            return handle_propose(body)
        if body.get("operation") == "commit":
            return handle_commit(body)
        raise ValueError("invalid_operation")
    except ValueError as e:
        return bad(str(e), 422)

def handle_propose(body):
    dossiers = validate_propose(body)
    evaluation_id = body["evaluationId"]
    input_digest = sha256_hex(canonical_json(dossiers))
    request_fingerprint = sha256_hex(canonical_json(body))
    conn = get_db()
    old = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (evaluation_id,)).fetchone()
    if old:
        if old["request_fingerprint"] != request_fingerprint:
            return bad("evaluation_id_content_conflict", 409)
        return app.response_class(old["propose_response"], status=200, mimetype="application/json")

    proposals = []
    # Validate the whole dossier set before writing evaluation state.
    for dossier in dossiers:
        cached = conn.execute(
            "SELECT proposal_json FROM dossier_cache WHERE dossier_id=? AND content_fingerprint=?",
            (dossier["dossierId"], sha256_hex(canonical_json(dossier)))
        ).fetchone()
        if cached:
            p = json.loads(cached["proposal_json"])
        else:
            p = make_proposal(dossier, body["allowedActions"], body["corpus"])
            validate_proposal(p, dossier, set(body["allowedActions"]))
            p = validate_proposal(p, dossier, set(body["allowedActions"]))
        proposals.append(p)

    response = {
        "profile": PROFILE, "evaluationId": evaluation_id,
        "status": "awaiting_receipts", "inputDigest": input_digest,
        "proposals": proposals
    }
    response_text = canonical_json(response).decode("utf-8")
    with transaction(conn):
        conn.execute("""INSERT INTO evaluations
          (evaluation_id, request_fingerprint, input_digest, verifier_jwk, propose_response, state)
          VALUES (?,?,?,?,?,?)""",
          (evaluation_id, request_fingerprint, input_digest,
           canonical_json(body["receiptVerifier"]["publicKeyJwk"]).decode(),
           response_text, "awaiting_receipts"))
        for d, p in zip(dossiers, proposals):
            fp = sha256_hex(canonical_json(d))
            conn.execute("""INSERT OR IGNORE INTO dossier_cache
              (dossier_id, content_fingerprint, proposal_json) VALUES (?,?,?)""",
              (d["dossierId"], fp, canonical_json(p).decode()))
            pd = proposal_digest(p)
            conn.execute("""INSERT INTO proposals
              (evaluation_id,dossier_id,call_id,action,proposal_digest,proposal_json)
              VALUES (?,?,?,?,?,?)""",
              (evaluation_id,p["dossierId"],p["callId"],p["action"],pd,canonical_json(p).decode()))
    return jsonify(response)

def handle_commit(body):
    if body.get("profile") != PROFILE or body.get("operation") != "commit":
        raise ValueError("invalid_commit_envelope")
    for k in ("evaluationId","inputDigest","receipts"):
        if k not in body: raise ValueError("missing_" + k)
    if not isinstance(body["receipts"], list) or not body["receipts"]:
        raise ValueError("invalid_receipts")
    conn = get_db()
    ev = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (body["evaluationId"],)).fetchone()
    if not ev:
        return bad("unknown_evaluation", 409)
    if body["inputDigest"] != ev["input_digest"]:
        return bad("input_digest_mismatch", 409)
    if ev["state"] == "completed":
        if ev["commit_fingerprint"] == sha256_hex(canonical_json(body)):
            return app.response_class(ev["commit_response"], status=200, mimetype="application/json")
        return bad("evaluation_already_committed", 409)

    proposals = conn.execute("SELECT * FROM proposals WHERE evaluation_id=? ORDER BY dossier_id", (body["evaluationId"],)).fetchall()
    expected = {p["dossier_id"]: p for p in proposals}
    receipts = body["receipts"]
    seen = set()
    if len(receipts) != len(expected):
        raise ValueError("receipt_count_mismatch")
    verified = []
    for r in receipts:
        if not is_obj(r): raise ValueError("invalid_receipt")
        did = r.get("dossierId")
        if did in seen or did not in expected: raise ValueError("duplicate_or_unknown_receipt")
        seen.add(did)
        stored = expected[did]
        if r.get("callId") != stored["call_id"] or r.get("action") != stored["action"]:
            raise ValueError("receipt_proposal_scope_mismatch")
        if r.get("proposalDigest") != stored["proposal_digest"]:
            raise ValueError("proposal_digest_mismatch")
        if not isinstance(r.get("accepted"), bool) or not all(isinstance(r.get(k),str) and r[k] for k in ("receiptId","receiptSignature")):
            raise ValueError("malformed_receipt")
        if not verify_receipt(body["evaluationId"], body["inputDigest"], r, json.loads(ev["verifier_jwk"])):
            raise ValueError("invalid_receipt_signature")
        verified.append(r)

    outcomes = []
    with transaction(conn):
        for r in verified:
            status = "executed" if r["accepted"] is True else "rejected"
            conn.execute("""INSERT INTO receipts
              (evaluation_id,dossier_id,call_id,receipt_id,receipt_json)
              VALUES (?,?,?,?,?)""",
              (body["evaluationId"],r["dossierId"],r["callId"],r["receiptId"],canonical_json(r).decode()))
            outcomes.append({
                "dossierId":r["dossierId"], "callId":r["callId"], "action":r["action"],
                "proposalDigest":r["proposalDigest"], "receiptId":r["receiptId"], "status":status
            })
        response = {"profile":PROFILE,"evaluationId":body["evaluationId"],"status":"completed",
                    "inputDigest":body["inputDigest"],"outcomes":outcomes}
        response_text = canonical_json(response).decode()
        conn.execute("UPDATE evaluations SET state='completed', commit_fingerprint=?, commit_response=? WHERE evaluation_id=?",
                     (sha256_hex(canonical_json(body)),response_text,body["evaluationId"]))
    return jsonify(response)

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
