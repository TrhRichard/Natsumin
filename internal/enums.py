from enum import StrEnum, IntEnum


class BadgeType(StrEnum):
	CONTRACTS = "contracts"
	ARIA = "aria"


class UserStatus(IntEnum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3
	INCOMPLETE = 4


class ContractStatus(IntEnum):
	PENDING = 0
	PASSED = 1
	FAILED = 2
	LATE_PASS = 3
	UNVERIFIED = 4


class ContractKind(IntEnum):
	NORMAL = 0
	AID = 1


class UserKind(IntEnum):
	NORMAL = 0
	AID = 1
