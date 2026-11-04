app_name = "mutaracnp"
app_title = "MutaraCNP"
app_publisher = "Upande"
app_description = "Mutara Fertilizer Planning Module"
app_email = "steve@upande.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Frappe v16 only lists apps on the desk's apps screen if they register here.
add_to_apps_screen = [
    {
        "name": "mutaracnp",
        "logo": "/assets/mutaracnp/images/mutaracnp-logo.svg",
        "title": "MutaraCNP",
        "route": "/app/mutaracnp",
        "has_permission": "mutaracnp.mutaracnp.utils.farm_permissions.has_app_permission",
    }
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/mutaracnp/css/mutaracnp.css"
# app_include_js = "/assets/mutaracnp/js/mutaracnp.js"

# Installation
# ------------

after_install = "mutaracnp.mutaracnp.install.after_install"

# Uninstallation
# ------------

before_uninstall = "mutaracnp.uninstall.before_uninstall"

# Permissions
# -----------
# Single farm - nothing to scope between farms, so (unlike the reference
# UpandeCNP app this was built from) there are deliberately no
# permission_query_conditions or has_permission hooks here. Role-based access
# (CNP Agronomist / Farm Manager / Field Worker / Storekeeper / General
# Manager) is handled entirely through each DocType's own permissions and the
# www page controllers' role gates.

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Purchase Receipt": {
        "on_submit": "mutaracnp.mutaracnp.utils.integration.update_budget_on_receipt"
    },
    "Stock Entry": {
        "on_submit": "mutaracnp.mutaracnp.utils.integration.mark_plan_issued_from_stock_entry"
    },
    "Fertilizer Store Request": {
        "validate": [
            "mutaracnp.mutaracnp.utils.farm_scope.set_farm_from_block",
            "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm",
        ],
        # The "Issue" workflow transition submits the request (doc_status 1 at
        # the Issued state) - catch that here to flip the linked Block
        # Fertilizer Plan to Issued too.
        "on_submit": "mutaracnp.mutaracnp.utils.farm_scope.mark_plan_issued_from_request",
    },
    "Fertilizer Application": {
        "validate": [
            "mutaracnp.mutaracnp.utils.farm_scope.set_farm_from_block",
            "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Block Fertilizer Plan": {
        "validate": [
            "mutaracnp.mutaracnp.utils.farm_scope.set_farm_from_block",
            "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Fertilizer Budget": {
        "validate": [
            "mutaracnp.mutaracnp.utils.farm_scope.set_farm_from_programme",
            "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Farm Block": {
        "validate": [
            "mutaracnp.mutaracnp.utils.farm_scope.set_farm_from_section",
            "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm",
        ]
    },
    "Fertilizer Programme": {
        "validate": "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm"
    },
    "Leaf Analysis": {
        "validate": "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm"
    },
    "Soil Analysis": {
        "validate": "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm"
    },
    "Production Calendar": {
        "validate": "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm"
    },
    "Section": {
        "validate": "mutaracnp.mutaracnp.utils.farm_scope.set_company_from_farm"
    },
}

# Runs on every `bench migrate`, not just once - a Workspace record isn't
# resynced from its source JSON by the normal DocType migrate step, so an
# edit to it would otherwise sit unused until someone noticed and force-
# reloaded it by hand.
after_migrate = ["mutaracnp.mutaracnp.install.after_migrate"]

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "mutaracnp.mutaracnp.utils.alerts.check_upcoming_applications",
        "mutaracnp.mutaracnp.utils.alerts.check_low_stock",
        "mutaracnp.mutaracnp.utils.alerts.check_missed_applications",
    ]
}

# Request Events
# ----------------
# Records who is using the field app. after_request, not before_request: token
# authentication happens after before_request runs, so there the user is still
# Guest for every call the mobile app makes.
after_request = ["mutaracnp.mutaracnp.utils.presence.record_presence"]

fixtures = [
    # The workspace is a single Custom HTML Block; ship the block with it, or a
    # fresh site syncs a workspace pointing at something that isn't there.
    {"dt": "Custom HTML Block", "filters": [["name", "=", "MutaraCNP Navigation"]]},
    {"dt": "Workflow", "filters": [["name", "=", "Fertilizer Store Request Workflow"]]},
    {"dt": "Workflow State", "filters": [["name", "in", ["Requested", "Approved", "Issued", "Rejected"]]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", ["Approve", "Reject", "Issue"]]]},
]
