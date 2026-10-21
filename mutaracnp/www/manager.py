import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/manager"
        raise frappe.Redirect

    from mutaracnp.mutaracnp.utils.farm_permissions import is_farm_manager
    if not is_farm_manager():
        frappe.throw(
            "This dashboard is only available to Farm Managers.",
            frappe.PermissionError,
        )

    context.no_cache = 1
    context.show_sidebar = False
    return context
