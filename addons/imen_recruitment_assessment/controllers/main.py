import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.imen_assessment.controllers.main import ValidationError, _int, _str, cors_headers

from ..models.submission import ARCHETYPES, DIMENSIONS, LEVELS

_logger = logging.getLogger(__name__)

DIMENSION_CODES = {code for code, _label in DIMENSIONS}
ARCHETYPE_CODES = {code for code, _label in ARCHETYPES}
LEVEL_CODES = {code for code, _label in LEVELS}
COMPOSITES = {
    # payload key -> field
    "character": "character_score",
    "mental": "mental_score",
    "skill": "skill_score",
    "capacity": "capacity_score",
    "agility": "adaptability_score",
    "sales": "commercial_score",
}


def _score(value, field, lo=1, hi=5):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValidationError(f"{field} must be a number between {lo} and {hi}")
    return round(float(value), 2)


def _choice(value, field, allowed):
    if value not in allowed:
        raise ValidationError(f"{field} must be one of {', '.join(sorted(allowed))}")
    return value


def _dict(value, field):
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object")
    return value


def _validate_answer(a):
    if not isinstance(a, dict):
        raise ValidationError("answers items must be objects")
    reverse = a.get("reverse", False)
    if not isinstance(reverse, bool):
        raise ValidationError("answers.reverse must be a boolean")
    return {
        "question_id": _str(a.get("questionId"), "answers.questionId", 20, required=True),
        "dimension": _choice(a.get("dimension"), "answers.dimension", DIMENSION_CODES),
        "question_text": _str(a.get("text"), "answers.text", 500, required=True),
        "reverse": reverse,
        "value": _int(a.get("value"), "answers.value", 1, 5),
        "score": _int(a.get("score"), "answers.score", 1, 5),
    }


def _validate(body):
    if not isinstance(body, dict):
        raise ValidationError("body must be an object")

    respondent = _dict(body.get("respondent"), "respondent")

    answers = body.get("answers")
    if not isinstance(answers, list) or not 1 <= len(answers) <= 200:
        raise ValidationError("answers must be a list of 1-200 items")

    dimensions = _dict(body.get("dimensions"), "dimensions")
    composites = _dict(body.get("composites"), "composites")
    archetypes = _dict(body.get("archetypes"), "archetypes")

    risks = body.get("risks") or []
    if not isinstance(risks, list) or len(risks) > 20:
        raise ValidationError("risks must be a list of at most 20 items")

    vals = {
        "name": _str(respondent.get("name"), "respondent.name", 200, required=True),
        "position": _str(respondent.get("position"), "respondent.position", 200) or False,
        "primary_archetype": _choice(body.get("primaryArchetype"), "primaryArchetype", ARCHETYPE_CODES),
        "secondary_archetype": _choice(body.get("secondaryArchetype"), "secondaryArchetype", ARCHETYPE_CODES),
        "readiness": _score(body.get("readiness"), "readiness"),
        "level": _choice(body.get("level"), "level", LEVEL_CODES),
        "archetype_scores": {
            _choice(k, "archetypes key", ARCHETYPE_CODES): _score(v, f"archetypes.{k}")
            for k, v in archetypes.items()
        },
        "risk_notes": "\n".join(_str(r, "risks item", 500, required=True) for r in risks) or False,
        "dimensions": {
            _choice(k, "dimensions key", DIMENSION_CODES): _score(v, f"dimensions.{k}")
            for k, v in dimensions.items()
        },
        "answers": [_validate_answer(a) for a in answers],
    }
    for key, field in COMPOSITES.items():
        vals[field] = _score(composites.get(key), f"composites.{key}")
    return vals


class ImenRecruitmentController(http.Controller):

    @http.route(
        "/imen/recruitment/submissions",
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
        vals["dimension_ids"] = [
            (0, 0, {"dimension": code, "score": score}) for code, score in vals.pop("dimensions").items()
        ]
        vals["user_agent"] = (request.httprequest.headers.get("User-Agent") or "")[:500] or False

        submission = request.env["imen.recruitment.submission"].sudo().create(vals)
        _logger.info("imen_recruitment_assessment: stored submission %s", submission.id)
        return request.make_json_response(
            {"id": submission.id, "submittedAt": submission.submitted_at.isoformat()},
            headers=headers,
            status=201,
        )
