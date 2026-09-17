#!/usr/bin/env python3
"""
Standalone CLI for querying Microsoft's public Azure Retail Prices API.
No auth required. Docs: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices

NOT used by calculate_acr.py or the automated skill workflow -- a subprocess
launched inside Claude's sandboxed VM cannot reach external APIs, so live
pricing in the actual skill flow is fetched by the assistant itself via the
azure_price_search MCP tool (see SKILL.md). This script is kept only as a
manual reference/testing tool for use outside the sandbox -- e.g. on your own
machine, to sanity-check a SKU or meter name before wiring it into a request.

Usage (CLI):
    python fetch_azure_prices.py --service "Virtual Machines" --sku "Standard_D4s_v5" --region "eastus"
    python fetch_azure_prices.py --service "Azure App Service" --region "eastus" --meter-contains "P1 v3"

Usage (import, outside the sandbox only):
    from fetch_azure_prices import get_price
    price = get_price(service_name="Virtual Machines", arm_sku_name="Standard_D4s_v5", region="eastus")
"""
import argparse
import json
import urllib.parse
import urllib.request
import sys

API_BASE = "https://prices.azure.com/api/retail/prices"


def query_prices(filters: dict, top: int = 50) -> list:
    """
    filters: dict of OData filter clauses, e.g. {"serviceName": "Virtual Machines", "armRegionName": "eastus"}
    Returns list of price items (raw API rows).
    """
    clauses = []
    for key, val in filters.items():
        clauses.append(f"{key} eq '{val}'")
    odata_filter = " and ".join(clauses)

    params = {"$filter": odata_filter, "$top": str(top)}
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"

    items = []
    # Follow pagination via NextPageLink, capped to avoid runaway loops
    for _ in range(5):
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items.extend(data.get("Items", []))
        next_link = data.get("NextPageLink")
        if not next_link or len(items) >= top:
            break
        url = next_link
    return items


def get_price(service_name: str, region: str, arm_sku_name: str = None,
              meter_name_contains: str = None, price_type: str = "Consumption") -> dict:
    """
    Convenience wrapper: fetch the best-matching consumption (pay-as-you-go) price.
    Returns dict with unitPrice, unitOfMeasure, meterName, skuName, retailPrice, or None if not found.

    Selection rules (learned the hard way -- see the blog post this skill came from):
    - App Service tier names need a space before the version letter in meterName/
      meter_name_contains -- "P1 v3", not "P1v3". The no-space form returns zero
      results even though it looks like a reasonable SKU string.
    - Windows vs. Linux for App Service does NOT follow the same pattern as VMs.
      Two Consumption rows can share an identical meterName/skuName (e.g. both
      "P1 v3") and only the Linux row self-identifies, via productName ending in
      "- Linux". The Windows row is the plain, unlabeled productName -- it does
      NOT contain the word "Windows" anywhere. So for App Service this function
      selects by presence of "Linux" in productName, not absence of "Windows".
      Confirmed live: both rows returned for "P1 v3" in eastus were priced
      0.315 (unlabeled = Windows) and 0.155 (labeled "- Linux").
    - VM SKUs are the opposite: Windows DOES self-identify in productName (e.g.
      "Virtual Machines Dsv5 Series Windows"), so excluding "windows" from
      productName is a reliable Linux/non-Windows filter there.
    - VM SKUs also return Spot and Low Priority variants as separate skuName
      rows -- this function excludes those by default unless requested.
    """
    filters = {
        "serviceName": service_name,
        "armRegionName": region,
        "priceType": price_type,
    }
    if arm_sku_name:
        filters["armSkuName"] = arm_sku_name

    items = query_prices(filters, top=100)

    if meter_name_contains:
        items = [i for i in items if meter_name_contains.lower() in i.get("meterName", "").lower()]

    is_app_service = "app service" in service_name.lower()

    if is_app_service:
        # Windows doesn't self-identify here -- select by presence of "Linux"
        # in productName instead of absence of "Windows".
        preferred = [i for i in items if "linux" in i.get("productName", "").lower()]
    else:
        # VMs: Windows DOES self-identify in productName, so exclude it directly,
        # along with Spot/Low Priority variants.
        preferred = [i for i in items if "windows" not in i.get("productName", "").lower()
                     and "spot" not in i.get("meterName", "").lower()
                     and "low priority" not in i.get("meterName", "").lower()]
    candidates = preferred or items

    if not candidates:
        return None

    best = candidates[0]
    return {
        "serviceName": best.get("serviceName"),
        "productName": best.get("productName"),
        "skuName": best.get("skuName"),
        "meterName": best.get("meterName"),
        "unitPrice": best.get("unitPrice"),
        "unitOfMeasure": best.get("unitOfMeasure"),
        "armRegionName": best.get("armRegionName"),
        "currencyCode": best.get("currencyCode"),
    }


def main():
    ap = argparse.ArgumentParser(description="Query Azure Retail Prices API (standalone reference tool, not used by the skill's automated flow)")
    ap.add_argument("--service", required=True, help="e.g. 'Virtual Machines', 'Azure App Service'")
    ap.add_argument("--sku", default=None, help="ARM SKU name, e.g. 'Standard_D4s_v5'")
    ap.add_argument("--region", required=True, help="e.g. 'eastus', 'westeurope'")
    ap.add_argument("--meter-contains", default=None, help="Substring filter on meterName, e.g. 'P1 v3' (note the space)")
    args = ap.parse_args()

    result = get_price(args.service, args.region, args.sku, args.meter_contains)
    if result is None:
        print(json.dumps({"error": "No matching price found. Try a broader filter -- check spacing in tier names (e.g. 'P1 v3')."}, indent=2))
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
