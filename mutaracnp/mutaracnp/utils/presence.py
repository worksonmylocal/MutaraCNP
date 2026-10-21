"""Who is using the field app, and when they last did.

The mobile app signs in with API tokens, not a Frappe session, so Frappe's
own "who is online" signals (the Sessions table, User.last_active) never
fire for it. Presence is recorded from the requests themselves: after each
call to this app's API by a signed-in user, the user's last-seen time, the
call made and whether it came from the app or the web are written to a
small hash in Redis - ephemeral by design, rebuilds within minutes if the
cache is flushed.
"""

import time

import frappe

CACHE_KEY = "mutaracnp_presence"
API_PREFIX = "/api/method/mutaracnp.mutaracnp.api."


def record_presence(response=None, request=None, **_):
	"""after_request hook. Runs for every request on the site, so the first
	thing it does is leave unless the call is ours, and it must never raise."""
	try:
		if request is None or not request.path.startswith(API_PREFIX):
			return
		user = frappe.session.user
		if not user or user == "Guest":
			return

		frappe.cache.hset(CACHE_KEY, user, {
			"ts": time.time(),
			"method": request.path[len(API_PREFIX):].split("?")[0],
			"via": "app" if request.headers.get("Authorization") else "web",
		})
	except Exception:
		pass


def read_presence():
	"""{user: {ts, method, via}}. Empty when the cache holds nothing."""
	try:
		raw = frappe.cache.hgetall(CACHE_KEY) or {}
	except Exception:
		return {}
	return {
		(k.decode() if isinstance(k, bytes) else k): v
		for k, v in raw.items() if isinstance(v, dict)
	}
