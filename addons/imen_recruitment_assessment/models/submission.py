from odoo import api, fields, models

# Codes used by landing/static/internal-recruitment/index.html
DIMENSIONS = [
    ("C1", "Integrity"),
    ("A1", "Attitude"),
    ("M1", "Mental Kerja"),
    ("S1", "Skill Readiness"),
    ("K1", "Thinking Capacity"),
    ("E1", "Commercial / Hunter"),
    ("L1", "Leadership"),
    ("R1", "Adaptability"),
    ("X1", "Response Consistency"),
]

ARCHETYPES = [
    ("elang", "Elang"),
    ("harimau", "Harimau"),
    ("hiu", "Hiu"),
    ("gajah", "Gajah"),
]

LEVELS = [
    ("high_potential", "High Potential"),
    ("ready_with_supervision", "Ready with Supervision"),
    ("developing", "Developing"),
    ("high_support_needed", "High Support Needed"),
]

SCORE_DIGITS = (3, 2)


class ImenRecruitmentSubmission(models.Model):
    _name = "imen.recruitment.submission"
    _description = "Recruitment Assessment Submission"
    _order = "submitted_at desc, id desc"

    # Candidate
    name = fields.Char(string="Candidate", required=True)
    position = fields.Char(string="Position Applied", index=True)

    # Result — computed client-side by the landing page, stored as-is
    primary_archetype = fields.Selection(ARCHETYPES, required=True, index=True)
    secondary_archetype = fields.Selection(ARCHETYPES, required=True)
    readiness = fields.Float(string="Readiness Index", digits=SCORE_DIGITS, aggregator="avg")
    level = fields.Selection(LEVELS, string="Work Readiness", required=True, index=True)

    # Composite scores (1-5)
    character_score = fields.Float(string="Character & Integrity", digits=SCORE_DIGITS, aggregator="avg")
    mental_score = fields.Float(string="Mental Kerja", digits=SCORE_DIGITS, aggregator="avg")
    skill_score = fields.Float(string="Skill Readiness", digits=SCORE_DIGITS, aggregator="avg")
    capacity_score = fields.Float(string="Capacity", digits=SCORE_DIGITS, aggregator="avg")
    adaptability_score = fields.Float(string="Adaptability", digits=SCORE_DIGITS, aggregator="avg")
    commercial_score = fields.Float(string="Commercial / Hunter", digits=SCORE_DIGITS, aggregator="avg")
    archetype_scores = fields.Json()

    risk_notes = fields.Text(string="Red Flags", help="One line per flag raised by the assessment.")
    risk_count = fields.Integer(string="# Red Flags", compute="_compute_risk_count", store=True)

    answer_ids = fields.One2many("imen.recruitment.answer", "submission_id", string="Answers")
    dimension_ids = fields.One2many("imen.recruitment.dimension", "submission_id", string="Dimension Scores")

    # HR follow-up
    state = fields.Selection(
        [("new", "New"), ("interview", "Interview"), ("hired", "Hired"), ("rejected", "Rejected")],
        string="Status", required=True, default="new", index=True,
    )
    hr_notes = fields.Html(string="HR Notes")

    user_agent = fields.Char()
    submitted_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True, readonly=True)

    @api.depends("risk_notes")
    def _compute_risk_count(self):
        for rec in self:
            rec.risk_count = len([line for line in (rec.risk_notes or "").splitlines() if line.strip()])


class ImenRecruitmentAnswer(models.Model):
    _name = "imen.recruitment.answer"
    _description = "Recruitment Assessment Answer"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one("imen.recruitment.submission", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(help="Order the question was shown in (questions are shuffled per session).")
    question_id = fields.Char(string="Question", required=True)
    dimension = fields.Selection(DIMENSIONS, required=True)
    question_text = fields.Char(string="Statement", required=True)
    reverse = fields.Boolean(help="Reverse-scored statement: score = 6 - answer.")
    value = fields.Integer(string="Answer (1-5)")
    score = fields.Integer(help="Answer after reverse scoring.")


class ImenRecruitmentDimension(models.Model):
    """One row per dimension per submission, so scores can be pivoted/graphed."""

    _name = "imen.recruitment.dimension"
    _description = "Recruitment Assessment Dimension Score"
    _order = "submission_id, dimension, id"

    submission_id = fields.Many2one("imen.recruitment.submission", required=True, ondelete="cascade", index=True)
    dimension = fields.Selection(DIMENSIONS, required=True, index=True)
    score = fields.Float(string="Score (1-5)", digits=SCORE_DIGITS, aggregator="avg")

    # Related for grouping in the analysis views
    position = fields.Char(related="submission_id.position", store=True)
    primary_archetype = fields.Selection(related="submission_id.primary_archetype", store=True)
    level = fields.Selection(related="submission_id.level", store=True)
    submitted_at = fields.Datetime(related="submission_id.submitted_at", store=True)
