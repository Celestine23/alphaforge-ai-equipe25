"""La Machine a remonter le temps : calculs deterministes (aucune IA).

Tout est converti en CAD avec le taux USD/CAD de la Banque du Canada
(dernier taux connu reporte les jours sans publication).
Rendements sur adj_close (ajuste pour dividendes et fractionnements).
"""
from functools import lru_cache
from pathlib import Path
import os

import numpy as np
import pandas as pd

from .recus import Registre, fmt_nombre

DATA = Path(os.environ.get("ALPHAFORGE_DATA", Path(__file__).resolve().parents[1] / "data"))
SRC_PRIX = "prices_daily.csv (adj_close, Yahoo Finance)"
SRC_FX = "fx_usdcad_daily.csv (Banque du Canada)"


@lru_cache(maxsize=1)
def univers() -> pd.DataFrame:
    return pd.read_csv(DATA / "assets_universe.csv").set_index("ticker")


@lru_cache(maxsize=1)
def _prix() -> pd.DataFrame:
    p = pd.read_csv(DATA / "prices_daily.csv", parse_dates=["date"])
    fx = pd.read_csv(DATA / "fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["usdcad"]
    jours = pd.DatetimeIndex(sorted(set(p["date"]) | set(fx.index)))
    fx = fx.reindex(jours).ffill().bfill()
    p["fx"] = np.where(p["currency"] == "USD", fx.reindex(p["date"]).to_numpy(), 1.0)
    p["prix_cad"] = p["adj_close"] * p["fx"]
    return p


@lru_cache(maxsize=64)
def serie_cad(ticker: str) -> pd.Series:
    p = _prix()
    s = p.loc[p["ticker"] == ticker].set_index("date")["prix_cad"].sort_index()
    if s.empty:
        raise ValueError(f"Actif inconnu : {ticker}")
    return s


def _jours_par_an(ticker: str) -> int:
    return 365 if ticker.endswith("-USD") else 252


def _sources(ticker: str) -> str:
    return SRC_PRIX + ("" if ticker.endswith(".TO") else f" ; {SRC_FX}")


def serie_portefeuille(poids: dict, montant: float, debut=None) -> pd.Series:
    """Valeur en CAD d'un portefeuille achete au debut et conserve (sans reequilibrage)."""
    series = {t: serie_cad(t) for t in poids}
    jours = sorted(set().union(*[s.index for s in series.values()]))
    df = pd.DataFrame({t: s.reindex(jours).ffill() for t, s in series.items()}).dropna()
    if debut is not None:
        df = df.loc[df.index >= pd.Timestamp(debut)]
    return sum(montant * w * df[t] / df[t].iloc[0] for t, w in poids.items())


def rejouer(poids: dict, montant: float, besoin_annees: float, reg: Registre,
            nom: str, debut=None) -> dict:
    """Rejoue `montant` investi selon `poids` et produit les recus."""
    v = serie_portefeuille(poids, montant, debut)
    d0, d1 = v.index[0], v.index[-1]
    periode = f"{d0.date()} → {d1.date()}"
    src = " ; ".join(sorted({_sources(t) for t in poids}))
    r = np.log(v).diff().dropna()
    n_an = 365 if all(t.endswith("-USD") for t in poids) else 252
    vol = r.std() * np.sqrt(n_an) * 100
    dd = (v / v.cummax() - 1)
    perte_max = dd.min() * 100
    creux_date = v.idxmin()
    creux = v.min()
    apres = v.loc[creux_date:]
    retour = apres[apres >= montant]
    mois_recup = None if retour.empty else round((retour.index[0] - creux_date).days / 30.44)
    fin_2021 = v.loc[:"2021-12-31"].iloc[-1]
    fin_2022 = v.loc[:"2022-12-31"].iloc[-1]
    an_2022 = (fin_2022 / fin_2021 - 1) * 100
    date_besoin = d0 + pd.DateOffset(years=int(besoin_annees), months=int(round((besoin_annees % 1) * 12)))
    val_besoin = v.loc[:date_besoin].iloc[-1] if date_besoin <= d1 else None

    res = {"nom": nom, "poids": poids, "montant": montant, "serie": v,
           "date_creux": creux_date, "date_besoin": date_besoin, "recus": {}}
    add = lambda cle, *a: res["recus"].__setitem__(cle, reg.ajouter(*a))
    add("vol", f"Volatilite annuelle — {nom}", vol, "%", periode,
        f"ecart-type des rendements journaliers (log) × √{n_an}", src)
    add("perte_max", f"Perte maximale (sommet → creux) — {nom}", perte_max, "%", periode,
        "minimum de (valeur / plus haut precedent − 1)", src)
    add("creux", f"Valeur au pire moment ({creux_date.date()}) — {nom}", creux, "$", periode,
        f"{fmt_nombre(montant)} $ × prix au creux / prix de depart", src)
    add("an2022", f"Resultat sur l'annee 2022 — {nom}", an_2022, "%", "2021-12-31 → 2022-12-31",
        "valeur fin 2022 / valeur fin 2021 − 1", src)
    add("fin", f"Valeur en fin de periode — {nom}", v.iloc[-1], "$", periode,
        "montant × prix final / prix de depart", src)
    if mois_recup is not None:
        add("recup", f"Temps pour revenir au montant investi apres le creux — {nom}", mois_recup,
            "mois", periode, "premiere date ou valeur ≥ montant investi, apres le creux", src)
    if val_besoin is not None:
        add("besoin", f"Valeur a la date du besoin ({date_besoin.date()}) — {nom}", val_besoin, "$",
            periode, f"valeur {besoin_annees:g} ans apres le depart", src)
    # Plusieurs dates d'entree : fenetres glissantes (horizon plafonne a 3 ans faute d'historique)
    h = min(besoin_annees, 3)
    pas = int(h * n_an)
    rend = (v.shift(-pas) / v - 1).dropna().iloc[::21] * 100
    if len(rend) > 5:
        add("fen_duree", f"Duree des periodes testees (plafonnee faute d'historique) — {nom}", h, "ans",
            periode, "min(horizon du besoin, 3 ans)", "choix de methode de l'equipe")
        add("fen_perte", f"Part des dates d'entree en perte apres {h:g} ans — {nom}",
            (rend < 0).mean() * 100, "%", periode, f"{len(rend)} dates d'entree mensuelles", src)
        add("fen_pire", f"Pire resultat apres {h:g} ans, toutes dates d'entree — {nom}",
            rend.min(), "%", periode, f"{len(rend)} dates d'entree mensuelles", src)
    res["valeurs"] = {k: r.valeur for k, r in res["recus"].items()}
    return res
