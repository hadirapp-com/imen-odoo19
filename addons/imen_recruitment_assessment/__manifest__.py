{
    "name": "IMEN Recruitment Assessment",
    "summary": "Collect and review IMEN ILDA internal recruitment assessments from the landing page",
    "description": """
The landing page (landing/static/internal-recruitment) POSTs each finished
Talent, Character & Work Readiness Assessment to
/imen/recruitment/submissions; results are reviewable by HR under the
Recruitment Assessment menu. Candidate results are restricted to the
Recruitment Assessment groups.

Reuses the CORS allow-list (imen_assessment.allowed_origins) and request
validation helpers from imen_assessment.
""",
    "author": "HadirApp",
    "license": "LGPL-3",
    "category": "Human Resources",
    "version": "19.0.1.0.0",
    "application": True,
    "installable": True,
    "depends": ["base", "web", "imen_assessment"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/submission_views.xml",
        "views/menus.xml",
    ],
}
