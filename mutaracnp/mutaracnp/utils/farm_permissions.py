"""
Mutara is single-farm, so there is no per-farm data segregation to do here
(the reference app's farm_permissions.py exists to answer "which farm's
rows may this person see" across several farms). What's left is the one
role check the /manager www page needs to gate access to itself.
"""

import frappe

MANAGER_ROLE = "Farm Manager"
APP_ROLES = {"CNP Agronomist", "Farm Manager", "Field Worker", "Storekeeper", "General Manager", "System Manager"}


def has_app_permission():
	"""Whether MutaraCNP shows on this user's apps screen - only for people
	with a MutaraCNP role, so the rest of the company's desk users (HR,
	clinic, livestock) don't get an icon for an app they can't use."""
	return bool(APP_ROLES & set(frappe.get_roles()))


def is_farm_manager(user=None):
	"""Whether this user may open the Manager dashboard."""
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	return "System Manager" in roles or MANAGER_ROLE in roles
