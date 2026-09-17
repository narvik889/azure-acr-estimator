# Microsoft Partner ACR Incentive Tiers

Microsoft's partner program (Solutions Partner designations, co-sell eligibility,
MDF/incentive thresholds) is tied to ACR, but the specific dollar thresholds and
designation requirements change periodically and are not reliable to hardcode here.

**When the user wants ACR mapped to a partner tier or designation:**

1. Do NOT state specific threshold dollar amounts from memory/training data.
2. Web search for the current thresholds, e.g.:
   - "Microsoft Solutions Partner designation ACR threshold [current year]"
   - "Microsoft Partner incentives ACR requirements [current year]"
3. Prefer official Microsoft Partner Center / Microsoft Learn documentation over
   third-party blogs.
4. Present the projected ACR figures from calculate_acr.py alongside the
   current threshold figures found via search, and let the user see both --
   note the search date so they know how fresh the threshold data is.
5. If search is unavailable, present the ACR projection only, and clearly flag
   that tier/threshold mapping needs to be confirmed against current Microsoft
   documentation before being used in any client-facing material.

This keeps the skill's core value (accurate, live Azure pricing math) decoupled
from a partner-program detail that can go stale independent of this skill.
