from odoo import api, fields, models

ASSESSMENT_TYPES = [
    ("ibp", "IBP"),
    ("imp", "IMP"),
]


class ImenAssessmentSubmission(models.Model):
    _name = "imen.assessment.submission"
    _description = "Business DNA Assessment Submission"
    _order = "submitted_at desc, id desc"

    # Respondent
    name = fields.Char(string="Respondent", required=True)
    contact = fields.Char()
    area = fields.Char()
    profession = fields.Char()
    org = fields.Char(string="Organization")

    # Result — computed client-side by the landing page, stored as-is
    assessment = fields.Selection(ASSESSMENT_TYPES, required=True, default="ibp", index=True)
    primary_dna = fields.Char(string="Primary DNA", required=True, index=True)
    secondary_dna = fields.Char(string="Secondary DNA", required=True)
    fit_score = fields.Integer(help="IMP only; IBP has no fit score.", aggregator="avg")
    scores = fields.Json(string="Raw Scores")

    answer_ids = fields.One2many("imen.assessment.answer", "submission_id", string="Answers")
    score_ids = fields.One2many("imen.assessment.score", "submission_id", string="DNA Scores")
    answer_count = fields.Integer(compute="_compute_answer_count")

    user_agent = fields.Char()
    submitted_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True, readonly=True)
    legacy_id = fields.Char(
        string="Collector ID", readonly=True, copy=False,
        help="UUID of the row in the old assessment-collector database, set by scripts/import_collector.py.",
    )

    _legacy_id_uniq = models.Constraint("unique(legacy_id)", "This collector submission was already imported.")

    @api.depends("answer_ids")
    def _compute_answer_count(self):
        for rec in self:
            rec.answer_count = len(rec.answer_ids)


class ImenAssessmentAnswer(models.Model):
    _name = "imen.assessment.answer"
    _description = "Business DNA Assessment Answer"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one("imen.assessment.submission", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer()
    question_id = fields.Char(string="Question", required=True)
    dna = fields.Char(string="DNA", required=True)
    choice_index = fields.Integer(string="Choice #")
    choice_text = fields.Char(string="Choice", required=True)
    score = fields.Integer()


class ImenAssessmentScore(models.Model):
    """One row per DNA per submission, so scores can be pivoted/graphed."""

    _name = "imen.assessment.score"
    _description = "Business DNA Assessment Score"
    _order = "submission_id, percent desc, id"

    submission_id = fields.Many2one("imen.assessment.submission", required=True, ondelete="cascade", index=True)
    dna = fields.Char(string="DNA", required=True, index=True)
    percent = fields.Integer(string="Score (%)", aggregator="avg")

    # Related for grouping in the analysis views
    assessment = fields.Selection(related="submission_id.assessment", store=True)
    area = fields.Char(related="submission_id.area", store=True)
    profession = fields.Char(related="submission_id.profession", store=True)
    submitted_at = fields.Datetime(related="submission_id.submitted_at", store=True)
