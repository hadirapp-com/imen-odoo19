{
    "name": "IBP DNA Assessment",
    "summary": "Collect and review IBP / IMP Business DNA Assessment submissions from the IMEN landing page",
    "description": """
Replaces the standalone assessment-collector service. The landing page
(landing/static/ibp and landing/static/imp-assessment) POSTs each finished
assessment to /imen/assessment/submissions; results are browsable, filterable
and pivotable under the IBP DNA Assessment menu.
""",
    "author": "HadirApp",
    "license": "LGPL-3",
    "category": "Human Resources",
    "version": "19.0.1.1.0",
    "application": True,
    "installable": True,
    "depends": ["base", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/config_data.xml",
        "views/assessment_views.xml",
        "views/menus.xml",
    ],
}
