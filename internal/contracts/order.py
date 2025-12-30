from typing import TypedDict, Literal

import re


class OrderType(TypedDict):
	type: Literal["regex"]
	pattern: str
	order_by: Literal["last_number"] | None


class OrderCategory(TypedDict):
	name: str
	order: list[str | OrderType]


class OrderContractData(TypedDict):
	name: str
	type: str
	kind: int
	status: int
	optional: int
	review_url: str | None


class SortedOrderCategory(TypedDict):  # im great at naming
	name: str
	types: list[str]


def sort_contract_types(contract_types: list[str], order_data: list[OrderCategory]) -> list[SortedOrderCategory]:
	result: list[SortedOrderCategory] = []
	used: set[str] = set()

	for category in order_data:
		matched: list[str] = []

		for rule in category["order"]:
			if isinstance(rule, str):
				for ct in contract_types:
					if ct.lower() == rule.lower() and ct not in used:
						matched.append(ct)
						used.add(ct)
			else:
				if rule["type"] == "regex":
					regex_matches = [ct for ct in contract_types if ct not in used and re.fullmatch(rule["pattern"], ct, re.IGNORECASE)]

					if rule.get("order_by") == "last_number":
						regex_matches.sort(key=lambda s: int(re.search(r"\d+$", s).group()))

					for ct in regex_matches:
						matched.append(ct)
						used.add(ct)

		if matched:
			result.append({"name": category["name"], "types": matched})

	other = [ct for ct in contract_types if ct not in used]
	if other:
		result.append({"name": "Other", "types": other})

	return result
