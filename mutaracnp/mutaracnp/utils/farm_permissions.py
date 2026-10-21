"""
Mutara is single-farm, so there is no per-farm data segregation to do here
(the reference app's farm_permissions.py exists to answer "which farm's
rows may this person see" across several farms). What's left is the one
role check the /manager www page needs to gate access to itself.
"""

import frappe

MANAGER_ROLE = "Farm Manager"


def is_farm_manager(user=None):
	"""Whether this user may open the Manager dashboard."""
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	return "System Manager" in roles or MANAGER_ROLE in roles
