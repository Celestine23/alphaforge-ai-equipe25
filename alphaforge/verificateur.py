"""Le Verificateur de recus (aucune IA) : chaque chiffre du texte doit correspondre a un recu."""
import re

NB = re.compile(r"(?<![#\w-])([−-]?\d{1,3}(?:[   ]\d{3})+|[−-]?\d+(?:,\d+)?)\s*(%|\$|mois|ans?)?")
REF = re.compile(r"#[RC]-\d{3}")


def _num(txt: str) -> float:
    return float(txt.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "").replace(",", "."))


def verifier(texte: str, recus: list) -> dict:
    ids = {r.id for r in recus}
    par_id = {r.id: r for r in recus}
    # 1) Chiffre suivi d'un numero de recu : il doit correspondre a CE recu.
    mal_cites = []
    for m in re.finditer(r"([−-]?\d[\d \u00a0\u202f]*(?:,\d+)?)\s*(%|\$|mois|ans?)?\s*\[(#[RC]-\d{3})", texte):
        r = par_id.get(m.group(3))
        try:
            x = _num(m.group(1).strip())
        except ValueError:
            continue
        if r is not None and abs(x - r.valeur) > max(1.0, abs(r.valeur) * 0.02) and abs(abs(x) - abs(r.valeur)) > 1.0:
            mal_cites.append(f"{m.group(0)}] ≠ {r.affichage}")
    refs = REF.findall(texte)
    refs_inconnues = sorted({r for r in refs if r not in ids})
    propre = REF.sub(" ", texte)
    propre = re.sub(r"\b(19|20)\d{2}(-\d{2}-\d{2})?\b", " ", propre)  # annees et dates
    trouves, orphelins = [], []
    for m in NB.finditer(propre):
        brut, unite = m.group(1), m.group(2)
        try:
            x = _num(brut)
        except ValueError:
            continue
        if unite is None and abs(x) < 20:
            continue  # petits nombres sans unite (ex. « 2 alternatives ») ignores
        ok = any(
            (abs(x - r.valeur) <= max(1.0, abs(r.valeur) * 0.02))
            or (unite in ("%", None) and abs(abs(x) - abs(r.valeur)) <= 1.0)
            for r in recus
        )
        (trouves if ok else orphelins).append(m.group(0).strip())
    total = len(trouves) + len(orphelins)
    score = 100.0 if total == 0 else round(100 * len(trouves) / total, 1)
    if refs_inconnues or mal_cites:
        score = min(score, 50.0)
    return {"score": score, "chiffres_verifies": trouves, "chiffres_sans_recu": orphelins,
            "recus_cites": sorted(set(refs)), "recus_inconnus": refs_inconnues,
            "chiffres_mal_cites": mal_cites}
