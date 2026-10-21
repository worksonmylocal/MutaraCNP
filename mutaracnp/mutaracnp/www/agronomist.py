import os

import frappe


def get_context(context):
    """The agronomist's central desk.

    Gated on the module role rather than left open: this page carries the
    actions that build a programme, not just a view of one. Mutara is a
    single-farm site, so there is no farm scoping to reapply here - the API
    always operates on the one farm.
    """
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/agronomist"
        raise frappe.Redirect

    roles = frappe.get_roles(frappe.session.user)
    if not ({"CNP Agronomist", "System Manager"} & set(roles)):
        frappe.throw(
            "This desk is for CNP agronomists. Ask for the CNP Agronomist role "
            "if you should have access.",
            frappe.PermissionError,
        )

    context.no_cache = 1
    context.show_sidebar = False
    # Frappe serves /assets with Cache-Control: max-age=43200 - twelve hours.
    # Without a changing query string a browser keeps the previous script and
    # stylesheet across every update, which looks exactly like "I still don't
    # see the change" however many times the page is reloaded. Keyed on the
    # files' own modification time so it moves when they do, with no manual
    # version number to forget to bump.
    context.asset_version = _asset_version()
    # Supplied here rather than assumed. csrf_token is not in a web page's
    # context by default, and a missing one renders as DebugUndefined, which
    # tojson then refuses - taking the whole page down with a traceback rather
    # than degrading. The site sets ignore_csrf today, but a page should not
    # depend on that, and it should certainly not die if the token cannot be
    # minted (there is no session object outside a real request).
    try:
        context.csrf_token = frappe.sessions.get_csrf_token()
    except Exception:
        context.csrf_token = ""
    return context


def _asset_version():
    base = frappe.get_app_path("mutaracnp", "public")
    newest = 0
    for rel in ("js/agronomist.js", "css/dashboard.css"):
        try:
            newest = max(newest, int(os.path.getmtime(os.path.join(base, rel))))
        except OSError:
            pass
    return newest
