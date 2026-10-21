"""Round-half-up helper.

Python's builtin round() does round-half-to-even (banker's rounding). The
calculation engine (a later phase) needs round-half-up for its worked
examples, so every intermediate rounding step should use this instead of
round() once that engine exists.
"""

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value, ndigits=0):
	q = Decimal(10) ** -ndigits
	return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))
