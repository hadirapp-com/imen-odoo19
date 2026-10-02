import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

ALLOWED_ORIGINS_PARAM = "imen_assessment.allowed_origins"


class ValidationError(Exception):
    pass


def _str(value, field, max_len, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{field} is required")
    if len(value) > max_len:
        raise ValidationError(f"{field} is too long (max {max_len})")
    return value


def _int(value, field, lo, hi, required=True):
    if value is None and not required:
        return None
    # bool is an int subclass in Python — reject it like zod would
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValidationError(f"{field} must be an integer between {lo} and {hi}")
    return value


def _validate_answer(a):
    if not isinstance(a, dict):
        raise ValidationError("answers items must be objects")
    return {
        "question_id": _str(a.get("questionId"), "answers.questionId", 20, required=True),
        "dna": _str(a.get("dna"), "answers.dna", 50, required=True),
        "choice_index": _int(a.get("choiceIndex"), "answers.choiceIndex", 0, 10),
        "choice_text": _str(a.get("choiceText"), "answers.choiceText", 500, required=True),
        "score": _int(a.get("score"), "answers.score", 0, 10),
    }


def _validate(body):
    """Mirrors assessment-collector/src/schema.ts."""
    if not isinstance(body, dict):
        raise ValidationError("body must be an object")

    assessment = body.get("assessment") or "imp"  # the IMP page omits this field
    if assessment not in ("imp", "ibp"):
        raise ValidationError("assessment must be 'imp' or 'ibp'")

    respondent = body.get("respondent")
    if not isinstance(respondent, dict):
        raise ValidationError("respondent is required")

    answers = body.get("answers")
    if not isinstance(answers, list) or not 1 <= len(answers) <= 200:
        raise ValidationError("answers must be a list of 1-200 items")

    scores = body.get("scores")
    if not isinstance(scores, dict):
        raise ValidationError("scores must be an object")

    return {
        "assessment": assessment,
        "name": _str(respondent.get("name"), "respondent.name", 200, required=True),
        "contact": _str(respondent.get("contact"), "respondent.contact", 50) or False,
        "area": _str(respondent.get("area"), "respondent.area", 200) or False,
        "profession": _str(respondent.get("profession"), "respondent.profession", 200) or False,
        "org": _str(respondent.get("org"), "respondent.org", 200) or False,
        "primary_dna": _str(body.get("primaryDna"), "primaryDna", 50, required=True),
        "secondary_dna": _str(body.get("secondaryDna"), "secondaryDna", 50, required=True),
        "fit_score": _int(body.get("fitScore"), "fitScore", 0, 100, required=False),
        "scores": {
            _str(dna, "scores key", 50, required=True): _int(pct, f"scores.{dna}", 0, 100)
            for dna, pct in scores.items()
        },
        "answers": [_validate_answer(a) for a in answers],
    }


def cors_headers():
    """CORS headers for a landing-page POST; also used by imen_recruitment_assessment."""
    origin = request.httprequest.headers.get("Origin")
    allowed = request.env["ir.config_parameter"].sudo().get_param(ALLOWED_ORIGINS_PARAM, "")
    allowed = {o.strip() for o in allowed.split(",") if o.strip()}
    if origin and origin in allowed:
        return [
            ("Access-Control-Allow-Origin", origin),
            ("Access-Control-Allow-Methods", "POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
            ("Access-Control-Max-Age", "86400"),
            ("Vary", "Origin"),
        ]
    return [("Vary", "Origin")]


class ImenAssessmentController(http.Controller):

    @http.route(
        "/imen/assessment/submissions",
        type="http",
        auth="public",
        methods=["POST", "OPTIONS"],
        csrf=False,
        save_session=False,
    )
    def submit(self, **kwargs):
        headers = cors_headers()
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=headers, status=204)

        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "null")
            vals = _validate(body)
        except (ValueError, ValidationError) as e:
            return request.make_json_response({"error": str(e)}, headers=headers, status=400)

        answers = vals.pop("answers")
        vals["answer_ids"] = [
            (0, 0, dict(answer, sequence=i)) for i, answer in enumerate(answers, start=1)
        ]
        vals["score_ids"] = [(0, 0, {"dna": dna, "percent": pct}) for dna, pct in vals["scores"].items()]
        vals["user_agent"] = (request.httprequest.headers.get("User-Agent") or "")[:500] or False

        submission = request.env["imen.assessment.submission"].sudo().create(vals)
        _logger.info("imen_assessment: stored %s submission %s", submission.assessment, submission.id)
        return request.make_json_response(
            {"id": submission.id, "submittedAt": submission.submitted_at.isoformat()},
            headers=headers,
            status=201,
        )
