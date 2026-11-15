"""Le Verificateur de recus (aucune IA) : chaque chiffre du texte doit correspondre a un recu.

Regles « citation obligatoire » et « 0 % sans recu » : Celestine (14 novembre, V5).
Correctifs du 14 novembre (validation des chiffres, Habib) : controle du SENS, et dates ecrites
en mots (« le 20 octobre 2022 ») ignorees comme les dates en chiffres.
Ancien defaut du sens :
Avant, « Tesla a gagne 71 % [#R-008] » etait accepte a 100 % alors que le recu
#R-008 vaut −71 % (une perte), parce que la comparaison ignorait le signe
(pour accepter « a perdu 71 % »). Desormais, le sens annonce par le texte
(signe moins, ou mot comme « perdu », « baisse », « gagne », « hausse »)
doit correspondre au signe du recu. Sans indice de sens, on garde l'ancienne
tolerance.
"""
import re

NB = re.compile(r"(?<![#\w-])([−-]?\d{1,3}(?:[   ]\d{3})+|[−-]?\d+(?:,\d+)?)\s*(%|\$|mois|ans?)?")
REF = re.compile(r"#[RC]-\d{3}")
DATE_EN_MOTS = re.compile(r"\b\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
                          r"septembre|octobre|novembre|d[ée]cembre)\b", re.I)

# Mots qui annoncent le sens d'une variation (debuts de mots, sans accents obligatoires)
MOTS_BAISSE = re.compile(r"\b(perd|perdu|perte|pertes|baiss|chut|recul|dimin|plong|effondr|fond|repli)\w*", re.I)
MOTS_HAUSSE = re.compile(r"\b(gagn|progress|hauss|augment|grimp|bondi|envol|rapport|croiss)\w*", re.I)
FENETRE = 40  # nombre de caracteres regardes avant le chiffre


def _num(txt: str) -> float:
    return float(txt.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "").replace(",", "."))


def _sens_annonce(texte: str, debut: int, brut: str, fin_precedente: int = 0):
    """-1 (baisse), +1 (hausse) ou None (inconnu) pour le chiffre qui commence a `debut`."""
    if brut.strip().startswith(("−", "-")):
        return -1
    avant = texte[max(fin_precedente, debut - FENETRE):debut]
    avant = re.split(r"[.;:!?\n]", avant)[-1]  # seulement la meme proposition
    if re.search(r"(\bà|\ba|jusqu.à|\bvers|\bniveau de)\s*$", avant, re.I):
        return None  # « baisse a 12 % » donne un niveau, pas une variation
    baisse, hausse = MOTS_BAISSE.findall(avant), MOTS_HAUSSE.findall(avant)
    if baisse and not hausse:
        return -1
    if hausse and not baisse:
        return 1
    return None


def _meme_valeur(x: float, unite, sens, valeur: float) -> bool:
    """x (lu dans le texte) correspond-il a `valeur` (le recu), sens compris ?"""
    if sens is not None and abs(valeur) >= 1.0 and (valeur < 0) != (sens < 0):
        return False  # le texte annonce une hausse pour une baisse (ou l'inverse)
    if abs(x - valeur) <= max(1.0, abs(valeur) * 0.02):
        return True
    # Tolerance « a perdu 71 % » pour un recu de −71 % (le sens a deja ete verifie).
    return unite in ("%", None) and abs(abs(x) - abs(valeur)) <= 1.0


def verifier(texte: str, recus: list) -> dict:
    ids = {r.id for r in recus}
    par_id = {r.id: r for r in recus}
    # 1) Chiffre suivi d'un numero de recu : il doit correspondre a CE recu (sens compris).
    mal_cites = []
    for m in re.finditer(r"([−-]?\d[\d \u00a0\u202f]*(?:,\d+)?)\s*(%|\$|mois|ans?)?\s*\[(#[RC]-\d{3})", texte):
        r = par_id.get(m.group(3))
        try:
            x = _num(m.group(1).strip())
        except ValueError:
            continue
        sens = _sens_annonce(texte, m.start(1), m.group(1)) if m.group(2) in ("%", None) else None
        if r is not None and not _meme_valeur(x, m.group(2), sens, r.valeur):
            mal_cites.append(f"{m.group(0)}] ≠ {r.affichage}")
    # 2) Chiffre en % ou $ sans numero de recu juste apres : « non cite ».
    non_cites = []
    for m in re.finditer(r"([−-]?\d{1,3}(?:[ \u00a0\u202f]\d{3})+|[−-]?\d+(?:,\d+)?)\s*(%|\$)(?!\s*\[#[RC]-\d{3})", texte):
        debut = texte[max(0, m.start() - 1):m.start()]
        if debut.isalnum():
            continue
        try:
            if _num(m.group(1)) == 0:
                continue  # « 0 % » : une absence, pas une donnee a sourcer
        except ValueError:
            pass
        if re.match(r"\s*[A-Z]{2,6}(\.TO|-USD)?\b", texte[m.end():]):
            continue  # composition d'une alternative (« 60 % SPY ») : chiffre produit par le code
        non_cites.append(m.group(0).strip())
    refs = REF.findall(texte)
    refs_inconnues = sorted({r for r in refs if r not in ids})
    propre = REF.sub(" ", texte)
    propre = re.sub(r"\b(19|20)\d{2}(-\d{2}-\d{2})?\b", " ", propre)  # annees et dates
    propre = DATE_EN_MOTS.sub(" ", propre)  # « le 20 octobre » : une date, pas un chiffre a sourcer
    trouves, orphelins = [], []
    fin_prec = 0
    for m in NB.finditer(propre):
        brut, unite = m.group(1), m.group(2)
        try:
            x = _num(brut)
        except ValueError:
            continue
        if unite is None and abs(x) < 20:
            continue  # petits nombres sans unite (ex. « 2 alternatives ») ignores
        sens = _sens_annonce(propre, m.start(1), brut, fin_prec) if unite in ("%", None) else None
        fin_prec = m.end()
        ok = any(_meme_valeur(x, unite, sens, r.valeur) for r in recus)
        (trouves if ok else orphelins).append(m.group(0).strip())
    total = len(trouves) + len(orphelins)
    score = 100.0 if total == 0 else round(100 * len(trouves) / total, 1)
    if refs_inconnues or mal_cites:
        score = min(score, 50.0)
    elif non_cites:
        score = min(score, 90.0)
    return {"score": score, "chiffres_verifies": trouves, "chiffres_sans_recu": orphelins,
            "recus_cites": sorted(set(refs)), "recus_inconnus": refs_inconnues,
            "chiffres_mal_cites": mal_cites, "chiffres_non_cites": non_cites}
