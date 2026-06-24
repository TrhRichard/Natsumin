from typing import overload, Literal, Union
from thefuzz import process
from enum import StrEnum

import discord


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
	ANICORD = "ANICORD"
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
	ONE_PIECE = "ONE PIECE"
	CALL_OF_THE_NIGHT = "CALL OF THE NIGHT"
	GACHIAKUTA = "GACHIAKUTA"
	ORV = "OMNISCIENT READERS VIEWPOINT"
	ICHI_THE_WITCH = "ICHI THE WITCH"
	BIAS_LAST_TRAIN = "MY BIAS GETS ON THE LAST TRAIN"
	AIKATSU = "AIKATSU"
	ATLA = "AVATAR THE LAST AIRBENDER"

	REFUGEE = "REFUGEE"  # technically not a rep but it appears, should only be used for global rep
	UNKNOWN = "UNKNOWN"  # appears if a user's rep is unable to be found


ROLE_TO_REP: dict[int, RepName] = {
	1141090560652890182: RepName.WORLD_TRIGGER,
	1079109100627046411: RepName.WHA,
	1170743167490994176: RepName.VIVY,
	1411397292119949344: RepName.VISUAL_NOVEL,
	1003046221432238101: RepName.VANITAS,
	1136378527055368212: RepName.UNDEAD_UNLUCK,
	1265542379075539047: RepName.TOKYO_REVENGERS,
	1139644313245069342: RepName.EMINENCE,
	995908657357267025: RepName.TONIKAWA,
	1063283590449868921: RepName.TENSURA,
	1171240063296868384: RepName.TEARMOON,
	1072217622227206244: RepName.SPY_FAMILY,
	994073177258987530: RepName.SHIELD_HERO,
	1074542618064724119: RepName.SBY,
	1215507836432416778: RepName.SAKAMOTO_DAYS,
	994073548853362720: RepName.SAO,
	994073600845946951: RepName.REZERO,
	1272396379695616060: RepName.ROSHIDERE,
	1176675192655847474: RepName.PRECURE,
	994073438857728150: RepName.OVERLORD,
	1412570348683268166: RepName.ORV,
	1062801563002884228: RepName.OTONARI,
	1002783698690768926: RepName.OSHI_NO_KO,
	1161335513383456888: RepName.ONIMAI,
	1418407360845844567: RepName.ONE_PIECE,
	1262861522544234526: RepName.NOKOTAN,
	1399074382923432088: RepName.NGNL,
	994359618421661746: RepName.MDUD,
	1493726531355283466: RepName.BIAS_LAST_TRAIN,
	994073680881664020: RepName.MUSHOKU,
	1273056949864370277: RepName.MAKEINE,
	1220460953213210635: RepName.MADOKA,
	1016796186176405635: RepName.LYCORIS_RECOIL,
	1172694314195894342: RepName.KUMO,
	1001305175501312100: RepName.KOMI,
	1254999446152937493: RepName.KAORU_HANA,
	994217793606127696: RepName.KANOKARI,
	1003134927014998076: RepName.KAGUYA,
	1066739728403144864: RepName.KON,
	1255261647723823224: RepName.JELLYFISH,
	1013563562175762532: RepName.IRUMA,
	1118954170435768361: RepName.HOUSEKI_NO_KUNI,
	1271232743694536766: RepName.GOKURAKUGAI,
	1333614913679134860: RepName.GBC,
	1465945118702833746: RepName.GACHIAKUTA,
	1134633351643414621: RepName.FT_EZ,
	1069834029567848468: RepName.FRIEREN,
	1070617803574480947: RepName.FATE,
	994359447705112636: RepName.CODE_GEASS,
	1096195804294811779: RepName.COTE,
	1412201464608063649: RepName.CALL_OF_THE_NIGHT,
	1046235473615536249: RepName.BOCCHI,
	1085981209978478592: RepName.BLEACH,
	1137147016133226506: RepName.BEASTARS,
	1262875464368787476: RepName.AIKATSU,
	999348392662663198: RepName.EIGHTY_SIX,
	994359307648909342: RepName.GO_TOUBOUN,
	1517618120359936021: RepName.ATLA,
}
ANICORD_REP_ID = 1110782878503157760

ALTERNATIVE_NAMES: dict[RepName, list[str]] = {
	RepName.BOCCHI: ["bocchi the rock"],
	RepName.MUSHOKU: ["mushoku tensei", "jobless reincarnation"],
	RepName.PRECURE: ["precord"],
	RepName.FT_EZ: ["fairy tail x eden zero (ft x ez)", "fairy tail", "eden zero"],
	RepName.MDUD: ["bisque"],
	RepName.TEARMOON: ["tearmoon empire"],
	RepName.SBY: ["bunny girl senpai", "aobuta"],
	RepName.KOMI: ["komi can't communicate"],
	RepName.FATE: ["fate/type-moon"],
	RepName.ANICORD: ["anicord event server"],
	RepName.KAGUYA: ["kaguya-sama love is war"],
	RepName.IRUMA: ["welcome to demon school! iruma-kun"],
	RepName.KUMO: ["kumo desu ga, nani ka?", "so i'm a spider, so what?"],
	RepName.HOUSEKI_NO_KUNI: ["land of the lustrous"],
	RepName.TENSURA: ["slime", "that time i got reincarnated as a slime", "tensei slime"],
	RepName.OTONARI: ["otonari no tenshi sama", "the angel next door spoils me rotten"],
	RepName.GO_TOUBOUN: ["the quintessential quintuplets", "5tbn"],
	RepName.LYCORIS_RECOIL: ["lycoreco", "fish's favorite show"],
	RepName.VANITAS: ["vnc"],
	RepName.KING_PROPOSAL: ["kp"],
	RepName.VISUAL_NOVEL: ["vn", "visual novel fandom"],
	RepName.CALL_OF_THE_NIGHT: ["yofukashi no uta"],
	RepName.ORV: ["omniscient reader"],
	RepName.KANOKARI: ["rent a girlfriend"],
	RepName.OSHI_NO_KO: ["onk"],
	RepName.SHIELD_HERO: ["the rising of the shield hero"],
	RepName.TONIKAWA: ["tonikaku kawaii", "fly me to the moon"],
	RepName.ROSHIDERE: ["alya sometimes hides her feelings in russian"],
	RepName.KAORU_HANA: ["the fragrant flower blooms with dignity"],
	RepName.NOKOTAN: ["my deer friend nokotan", "shikanoko nokonoko koshitantan"],
	RepName.BIAS_LAST_TRAIN: ["nae choeaeneun makchareul tanda"],
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
	name, min_confidence: int = ..., *, only_include_reps: list[RepName] | None = ..., include_confidence: Literal[False] = ...
) -> RepName | None: ...
@overload
def get_rep(
	name, min_confidence: int = ..., *, only_include_reps: list[RepName] | None = ..., include_confidence: Literal[True]
) -> tuple[RepName | None, int | None]: ...
def get_rep(
	name: str, min_confidence: int = 80, *, only_include_reps: list[RepName] | None = None, include_confidence: bool = False
) -> Union[RepName | None, tuple[RepName | None, int | None]]:
	if name is None:
		return (None, None) if include_confidence else None
	elif name.strip() == "":
		return (None, None) if include_confidence else None

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
	else:
		choices = rep_fuzzy_choices

	fuzzy_results: list[tuple[str, int]] = process.extract(name.lower(), [k for k in choices.keys()], limit=1)
	if fuzzy_results:
		rep_name, confidence = fuzzy_results[0]
		if confidence >= min_confidence:
			found_rep = choices[rep_name]
			return (found_rep, confidence) if include_confidence else found_rep

	return (None, None) if include_confidence else None


def search_reps(query: str, min_confidence: int = 80, *, limit: int = 25) -> list[tuple[RepName, int | None]]:
	if query is None or query.strip() == "":
		return [(rep, None) for rep in RepName.__members__.values()]

	reps_found: dict[RepName, int] = {}
	fuzzy_results: list[tuple[str, int]] = process.extract(query.lower(), [k for k in rep_fuzzy_choices.keys()], limit=limit)
	for rep_name, confidence in fuzzy_results:
		if confidence >= min_confidence:
			found_rep = rep_fuzzy_choices[rep_name]
			reps_found[found_rep] = confidence

	return [(rep, confidence) for rep, confidence in reps_found.items()]


def get_rep_from_member(member: discord.Member, default: RepName = RepName.UNKNOWN) -> RepName:
	has_anicord_rep = False
	for role in member.roles:
		if rep := ROLE_TO_REP.get(role.id):
			return rep
		if role.id == ANICORD_REP_ID:
			has_anicord_rep = True

	if has_anicord_rep:
		return RepName.ANICORD

	return default


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
