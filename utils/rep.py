from enum import StrEnum
from thefuzz import process
from typing import overload, Literal, Union

# jesus christ its insane how many times a name is written differently on these sheets,
# anyway this script basically only has 1 useful thing, get_rep, which attempts to get


class RepName(StrEnum):
	TEARMOON = "TEARMOON"
	SHIELD_HERO = "SHIELD HERO"
	IRUMA = "IRUMA-KUN"
	FRIEREN = "FRIEREN"
	EMINENCE = "EMINENCE IN SHADOW"
	GO_TOUBOUN = "5TOUBOUN"
	VANITAS = "VANITAS NO CARTE"
	KAGUYA = "KAGUYA-SAMA"
	TONIKAWA = "TONIKAWA"
	MADOKA = "MADOKA"
	EIGHTY_SIX = "86"
	FT_EZ = "FTxEZ"
	SPY_FAMILY = "SPY X FAMILY"
	MAKEINE = "MAKEINE"
	WORLD_TRIGGER = "WORLD TRIGGER"
	KAORU_HANA = "KAORU HANA"
	KANOKARI = "KANOKARI"
	AES = "ANICORD"
	BEASTARS = "BEASTARS"
	CODE_GEASS = "CODE GEASS"
	SAO = "SWORD ART ONLINE"
	LYCORIS_RECOIL = "LYCORIS RECOIL"
	WHA = "WITCH HAT ATELIER"
	MDUD = "MY DRESS-UP DARLING"
	COTE = "CLASSROOM OF THE ELITE"
	SAKAMOTO_DAYS = "SAKAMOTO DAYS"
	ONIMAI = "ONIMAI"
	BLEACH = "BLEACH"
	OTONARI = "OTONARI"
	GOKURAKUGAI = "GOKURAKUGAI"
	HOUSEKI_NO_KUNI = "HOUSEKI NO KUNI"
	JELLYFISH = "JELLYFISH"
	KUMO = "KUMO"
	ROSHIDERE = "ROSHIDERE"
	BOCCHI = "BOCCHI"
	UNDEAD_UNLUCK = "UNDEAD UNLUCK"
	KON = "K-ON"
	OVERLORD = "OVERLORD"
	FATE = "FATE"
	KOMI = "KOMI"
	MUSHOKU = "MUSHOKU"
	NOKOTAN = "NOKOTAN"
	OSHI_NO_KO = "OSHI NO KO"
	PRECURE = "PRECURE"
	REZERO = "REZERO"
	SBY = "SBY"  # aint typing the entire romaji thats so long
	TENSURA = "TENSURA"
	GBC = "GIRLS BAND CRY"
	VIVY = "VIVY"
	MADE_IN_ABYSS = "MADE IN ABYSS"  # unused
	NGNL = "NO GAME NO LIFE"
	KING_PROPOSAL = "KING'S PROPOSAL"  # unused
	MADOME = "AN ARCHDEMON'S DILEMMA"
	TOKYO_REVENGERS = "TOKYO REVENGERS"
	MANHWA = "MANHWA"  # unused
	VISUAL_NOVEL = "VISUAL NOVEL"


ALTERNATIVE_NAMES: dict[RepName, list[str]] = {
	RepName.BOCCHI: ["bocchi the rock"],
	RepName.MUSHOKU: ["mushoku tensei"],
	RepName.PRECURE: ["precord"],
	RepName.FT_EZ: ["fairy tail x eden zero (ft x ez)"],
	RepName.MDUD: ["bisque"],
	RepName.TEARMOON: ["tearmoon empire"],
	RepName.SBY: ["bunny girl senpai", "aobuta"],
	RepName.KOMI: ["komi can't communicate"],
	RepName.FATE: ["fate/type-moon"],
	RepName.AES: ["anicord event server"],
	RepName.KAGUYA: ["kaguya-sama love is war"],
	RepName.IRUMA: ["welcome to demon school! iruma-kun"],
	RepName.KUMO: ["kumo desu ga, nani ka?", "so i'm a spider, so what?"],
	RepName.HOUSEKI_NO_KUNI: ["land of the lustrous"],
	RepName.TENSURA: ["slime", "that time i got reincarnated as a slime"],
	RepName.OTONARI: ["otonari no tenshi sama", "the angel next door spoils me rotten"],
	RepName.GO_TOUBOUN: ["the quintessential quintuplets", "5tbn"],
	RepName.LYCORIS_RECOIL: ["lycoreco"],
	RepName.VANITAS: ["vnc"],
	RepName.KING_PROPOSAL: ["kp"],
	RepName.VISUAL_NOVEL: ["vn"],
}

rep_fuzzy_choices: dict[str, RepName] = {}
for rep in RepName:
	rep_fuzzy_choices[rep.value.lower()] = rep
	rep_fuzzy_choices[rep.name.lower()] = rep

	for alt in ALTERNATIVE_NAMES.get(rep, []):
		rep_fuzzy_choices[alt.lower()] = rep


# python typing sucks what the hell is all of this it makes my head hurt when i look at it
@overload
def get_rep(
	name, min_confidence: int = ..., *, only_include_reps: list[RepName | None] = ..., include_confidence: Literal[False] = ...
) -> RepName | None: ...
@overload
def get_rep(
	name, min_confidence: int = ..., *, only_include_reps: list[RepName | None] = ..., include_confidence: Literal[True]
) -> tuple[RepName | None, int | None]: ...
def get_rep(
	name: str, min_confidence: int = 80, *, only_include_reps: list[RepName] | None = None, include_confidence: bool = False
) -> Union[RepName | None, tuple[RepName | None, int | None]]:
	if name is None:
		return (None, None) if include_confidence else None

	choices = rep_fuzzy_choices
	if only_include_reps is not None:  # incase you only want to match the name from a specific list of reps instead of all
		new_choices: dict[str, RepName] = {}
		for rep in only_include_reps:
			if isinstance(rep, str):
				rep = RepName(rep)
			new_choices[rep.value.lower()] = rep
			new_choices[rep.name.lower()] = rep
			for alt in ALTERNATIVE_NAMES.get(rep, []):
				new_choices[alt.lower()] = rep
		choices = new_choices

	fuzzy_results: list[tuple[str, int]] = process.extract(name.lower(), [k for k in choices.keys()], limit=1)
	if fuzzy_results:
		rep_name, confidence = fuzzy_results[0]
		if confidence >= min_confidence:
			found_rep = rep_fuzzy_choices[rep_name]
			return (found_rep, confidence) if include_confidence else found_rep

	return (None, None) if include_confidence else None


if __name__ == "__main__":
	try:
		while True:
			query = input("NAME > ")
			rep, confidence = get_rep(query, include_confidence=True)

			if rep is not None:
				print(f"{rep.value} ({confidence}%)")
			else:
				print("Could not find anything.")
	except KeyboardInterrupt:
		pass
