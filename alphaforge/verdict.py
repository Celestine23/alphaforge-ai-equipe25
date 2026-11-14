"""Le verdict vient des regles codees du contrat, pas de l'IA."""
import itertools
import json
from pathlib import Path

from .machine import rejouer, univers
from .recus import Registre

CONTRATS = json.loads((Path(__file__).parent / "contrats.json").read_text(encoding="utf-8"))
STABLES = {"etf_bond"}


def contrat(persona: str, **modifs) -> dict:
    c = dict(CONTRATS[persona])
    c.update({k: v for k, v in modifs.items() if v is not None})
    return c


def recus_contrat(c: dict, persona: str, reg: Registre) -> dict:
    src = "contrats.json (hypothese de l'equipe)"
    p = f"contrat de {persona}"
    return {
        "horizon": reg.ajouter("Horizon du besoin d'argent", c["horizon_annees"], "ans", p, "declare", src),
        "perte": reg.ajouter("Perte toleree", c["perte_max_toleree_pct"], "%", p, "hypothese", src),
        "vol": reg.ajouter("Volatilite maximale", c["volatilite_max_pct"], "%", p, "hypothese", src),
        "poids": reg.ajouter("Poids maximal d'un seul titre", c["poids_max_titre_pct"], "%", p, "hypothese", src),
        "crypto": reg.ajouter("Cryptoactifs maximum", c["crypto_max_pct"], "%", p, "hypothese", src),
        "stable": reg.ajouter("Part stable minimale", c["part_stable_min_pct"], "%", p, "hypothese", src),
    }


def _composition(poids: dict) -> dict:
    u = univers()
    crypto = sum(w for t, w in poids.items() if u.loc[t, "asset_class"] == "crypto") * 100
    stable = sum(w for t, w in poids.items() if u.loc[t, "asset_class"] in STABLES) * 100
    titres = [w for t, w in poids.items() if u.loc[t, "asset_class"] in ("equity", "crypto")]
    return {"crypto": crypto, "stable": stable, "max_titre": max(titres, default=0) * 100,
            "secteurs": {u.loc[t, "sector"] for t in poids}}


def evaluer(c: dict, res: dict, poids_dans_capital: float, rc: dict) -> dict:
    """Retourne le verdict et la liste des controles (chacun relie a des recus)."""
    v, rec = res["valeurs"], res["recus"]
    comp = _composition(res["poids"])
    long_terme = c["horizon_annees"] >= 8
    ctl = []

    def ajout(regle, limite, valeur_txt, recus, ok, cle):
        ctl.append({"regle": regle, "limite": limite, "valeur": valeur_txt,
                    "recus": recus, "statut": "ok" if ok else "depasse", "cle": cle})

    ajout("Perte maximale toleree", rc["perte"].affichage, rec["perte_max"].affichage,
          [rec["perte_max"].id, rc["perte"].id], v["perte_max"] >= c["perte_max_toleree_pct"],
          cle=not long_terme)
    ajout("Volatilite maximale", rc["vol"].affichage, rec["vol"].affichage,
          [rec["vol"].id, rc["vol"].id], v["vol"] <= c["volatilite_max_pct"], cle=False)
    ajout("Cryptoactifs maximum", rc["crypto"].affichage, f"{comp['crypto']:.0f} %",
          [rc["crypto"].id], comp["crypto"] <= c["crypto_max_pct"], cle=True)
    ajout("Part stable minimale", rc["stable"].affichage, f"{comp['stable']:.0f} %",
          [rc["stable"].id], comp["stable"] >= c["part_stable_min_pct"], cle=False)
    poids_titre = comp["max_titre"] * poids_dans_capital
    ajout("Poids maximal d'un seul titre (dans le capital total)", rc["poids"].affichage,
          f"{poids_titre:.0f} %", [rc["poids"].id], poids_titre <= c["poids_max_titre_pct"], cle=False)
    if "recup" in rec or "besoin" in rec:
        mois = v.get("recup")
        ok = mois is not None and mois <= c["horizon_annees"] * 12
        ajout("Temps de recuperation compatible avec l'horizon", rc["horizon"].affichage,
              rec["recup"].affichage if "recup" in rec else "non recupere",
              [x.id for x in (rec.get("recup"), rc["horizon"]) if x], ok, cle=False)
    for secteur in comp["secteurs"] & set(c.get("exclusions_secteurs", [])):
        source = c.get("exclusions_sources", {}).get(secteur)
        ctl.append({"regle": f"Exclusion ESG : {secteur}", "limite": "exclu si une source publique le justifie",
                    "valeur": source or "aucune source ESG documentee", "recus": [],
                    "statut": "depasse" if source else "info_manquante", "cle": bool(source)})

    if any(x["statut"] == "depasse" and x["cle"] for x in ctl):
        verdict = "Incoherent"
    elif any(x["statut"] in ("depasse", "info_manquante") for x in ctl):
        verdict = "A surveiller"
    else:
        verdict = "Coherent"
    return {"verdict": verdict, "controles": ctl}


def alternatives(c: dict, ticker_demande: str, montant: float, besoin: float, rc: dict,
                 reg_brouillon_factory) -> list:
    """Cherche 2 combinaisons conformes au contrat (grille simple, deterministe)."""
    candidats = []
    stab_min = c["part_stable_min_pct"] / 100
    for coeur, stable in itertools.product(c["blocs_coeur"], c["blocs_stables"] or [None]):
        for ws in sorted({max(stab_min, 0.1), stab_min + 0.1, stab_min + 0.2, 0.6, 0.7}):
            if ws > 0.9 or stable is None:
                continue
            poids = {coeur: round(1 - ws, 2), stable: round(ws, 2)}
            candidats.append(poids)
    # Variante : une petite part plafonnee du titre demande
    w_max = min(c["poids_max_titre_pct"] / 100 * c["capital_total"] / montant, 0.5)
    if univers().loc[ticker_demande, "asset_class"] != "crypto" or c["crypto_max_pct"] > 0:
        for base in list(candidats):
            for w in (w_max, w_max / 2):
                if w > 0.01:
                    p = {k: round(v * (1 - w), 4) for k, v in base.items()}
                    p[ticker_demande] = round(w, 4)
                    candidats.append(p)
    conformes = []
    for poids in candidats:
        reg = reg_brouillon_factory()
        res = rejouer(poids, montant, besoin, reg, "test")
        ev = evaluer(c, res, montant / c["capital_total"], recus_contrat(c, "x", reg))
        if ev["verdict"] == "Coherent":
            part_stable = sum(w for t, w in poids.items() if t in c["blocs_stables"])
            conformes.append((poids, part_stable, res["valeurs"].get("besoin", res["valeurs"]["fin"])))
    # Priorite : utiliser le budget de risque du contrat (part stable la plus basse permise),
    # puis la valeur a la date du besoin. On ne cherche pas le meilleur rendement passe.
    conformes.sort(key=lambda x: (x[1], -x[2]))
    avec_titre = [p for p, _, _ in conformes if ticker_demande in p]
    sans_titre = [p for p, _, _ in conformes if ticker_demande not in p]
    choix = avec_titre[:1] + sans_titre[:2]
    return choix[:2]
