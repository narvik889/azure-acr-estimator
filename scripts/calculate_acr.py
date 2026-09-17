#!/usr/bin/env python3
"""
Model projected Azure Consumed Revenue (ACR) for a set of already-priced workloads.

This script does PURE MATH ONLY -- it makes no network calls. Pricing must be
resolved beforehand (by the assistant, via the azure_price_search MCP tool or
equivalent) and passed in on each item as `unit_price`. This split exists
because a subprocess launched from this script inside Claude's sandboxed VM
cannot reach external APIs -- only the assistant itself can, through its own
tool calls. See SKILL.md step 2 for the fetch-then-compute workflow.

This script also does NOT know current Microsoft partner ACR incentive tier
thresholds -- those change periodically and must be confirmed separately (see
references/partner_tiers.md). It only computes projected Azure consumption
($ACR), which is the input to that lookup.

Example input JSON (workloads.json) -- every item must already carry a
resolved unit_price:
{
  "months": 12,
  "items": [
    {
      "name": "Prod app servers",
      "service_name": "Virtual Machines",
      "region": "eastus",
      "matched_sku": "Standard_D4s_v5",
      "unit_price": 0.192,
      "unit_of_measure": "1 Hour",
      "currency": "USD",
      "quantity": 4,
      "hours_per_month": 730,
      "monthly_growth_rate": 0.02
    },
    {
      "name": "App Service Plan",
      "service_name": "Azure App Service",
      "region": "eastus",
      "matched_sku": "P1 v3",
      "unit_price": 0.219,
      "unit_of_measure": "1 Hour",
      "currency": "USD",
      "quantity": 2,
      "hours_per_month": 730,
      "monthly_growth_rate": 0.0
    }
  ]
}

If a line item couldn't be priced (lookup failed, ambiguous match, etc.), pass
it through with an "error" field instead of unit_price -- this script will
flag it in the output and exclude it from totals rather than silently
treating it as zero cost. Never invent or guess a unit_price to fill the gap.

Usage:
    python calculate_acr.py --input workloads.json --output acr_projection.json
"""
import argparse
import json


REQUIRED_FIELDS = ["name", "service_name", "region", "quantity", "hours_per_month"]


def compute_projection(config: dict) -> dict:
    months = config.get("months", 12)
    items = config["items"]

    priced_items = []
    for item in items:
        # Pass through any item that already carries an explicit error --
        # never fabricate a price to fill the gap.
        if "error" in item or "unit_price" not in item:
            priced_items.append({
                **item,
                "error": item.get("error", "No unit_price provided -- price must be resolved before calling this script"),
            })
            continue

        missing = [f for f in REQUIRED_FIELDS if f not in item]
        if missing:
            priced_items.append({
                **item,
                "error": f"Missing required field(s): {', '.join(missing)}",
            })
            continue

        unit_price = item["unit_price"]
        qty = item.get("quantity", 1)
        hours = item.get("hours_per_month", 730)
        monthly_baseline = unit_price * qty * hours

        priced_items.append({
            "name": item["name"],
            "service_name": item["service_name"],
            "region": item["region"],
            "matched_sku": item.get("matched_sku"),
            "unit_price": unit_price,
            "unit_of_measure": item.get("unit_of_measure"),
            "quantity": qty,
            "hours_per_month": hours,
            "monthly_baseline_cost": round(monthly_baseline, 2),
            "monthly_growth_rate": item.get("monthly_growth_rate", 0.0),
            "currency": item.get("currency", "USD"),
        })

    # Build month-by-month projection per item and totals
    monthly_totals = [0.0] * months
    for pitem in priced_items:
        if "error" in pitem:
            continue
        base = pitem["monthly_baseline_cost"]
        growth = pitem["monthly_growth_rate"]
        series = []
        for m in range(months):
            val = base * ((1 + growth) ** m)
            series.append(round(val, 2))
            monthly_totals[m] += val
        pitem["monthly_projection"] = series
        pitem["cumulative_acr"] = round(sum(series), 2)

    errored = [p for p in priced_items if "error" in p]

    result = {
        "months": months,
        "items": priced_items,
        "monthly_totals": [round(v, 2) for v in monthly_totals],
        "total_acr": round(sum(monthly_totals), 2),
        "acr_12mo": round(sum(monthly_totals[:12]), 2) if months >= 12 else None,
        "acr_36mo": round(sum(monthly_totals[:36]), 2) if months >= 36 else None,
        "unresolved_item_count": len(errored),
    }
    return result


def main():
    ap = argparse.ArgumentParser(description="Project Azure Consumed Revenue (ACR) for a set of already-priced workloads")
    ap.add_argument("--input", required=True, help="Path to workload config JSON (each item must already carry unit_price)")
    ap.add_argument("--output", default=None, help="Path to write result JSON (defaults to stdout)")
    args = ap.parse_args()

    with open(args.input) as f:
        config = json.load(f)

    result = compute_projection(config)

    output_str = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_str)
        print(f"Wrote projection to {args.output}")
        if result["unresolved_item_count"]:
            print(f"WARNING: {result['unresolved_item_count']} item(s) had no resolved price and were excluded from totals -- see 'error' fields.")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
