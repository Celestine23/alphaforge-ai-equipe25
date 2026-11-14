"""Aller-retour JSON du resultat de calcul (pour l'appel via AWS Lambda)."""
import pandas as pd

from .recus import Recu, Registre


def vers_json(calc: dict) -> dict:
    def res_json(res):
        s = res["serie"]
        return {"nom": res["nom"], "poids": res["poids"], "montant": res["montant"],
                "dates": [d.strftime("%Y-%m-%d") for d in s.index], "valeurs": [round(x, 2) for x in s.values],
                "date_creux": str(res["date_creux"].date()), "date_besoin": str(res["date_besoin"].date()),
                "recus": {k: r.id for k, r in res["recus"].items()}}
    return {"contrat": calc["contrat"],
            "recus": [r.__dict__ for r in calc["registre"].recus],
            "principal": res_json(calc["principal"]), "evaluation": calc["evaluation"],
            "alternatives": [{"nom": a["nom"], "res": res_json(a["res"]), "eval": a["eval"]}
                             for a in calc["alternatives"]]}


def depuis_json(d: dict) -> dict:
    reg = Registre("R")
    reg.recus = [Recu(**r) for r in d["recus"]]
    par_id = reg.par_id()

    def res_obj(r):
        recus = {k: par_id[i] for k, i in r["recus"].items()}
        return {"nom": r["nom"], "poids": r["poids"], "montant": r["montant"],
                "serie": pd.Series(r["valeurs"], index=pd.to_datetime(r["dates"])),
                "date_creux": pd.Timestamp(r["date_creux"]), "date_besoin": pd.Timestamp(r["date_besoin"]),
                "recus": recus, "valeurs": {k: v.valeur for k, v in recus.items()}}
    return {"contrat": d["contrat"], "registre": reg, "principal": res_obj(d["principal"]),
            "evaluation": d["evaluation"],
            "alternatives": [{"nom": a["nom"], "res": res_obj(a["res"]), "eval": a["eval"]}
                             for a in d["alternatives"]]}
