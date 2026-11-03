from mutaracnp.mutaracnp.install import seed_core_data


def execute():
	"""Backfill for sites installed before Soil Buildup Factor existed - reuses
	the same idempotent seeding install.py runs on a fresh install, so a
	one-off site doesn't need its own copy of this logic."""
	seed_core_data()
