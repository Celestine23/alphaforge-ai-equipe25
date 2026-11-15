"""Interface AlphaForge AI — lancer :  streamlit run app.py

Deux niveaux de lecture :
  1. « Pour vous » : l'histoire du placement en dollars et en mois, sans jargon (pour l'investisseur).
  2. « Les preuves » : règles, reçus, carte de vérité, trace (pour le jury et les curieux).
Toutes les phrases de l'onglet « Pour vous » sont construites par le code à partir des reçus :
aucun chiffre n'y est inventé.
"""
import os
import re
from contextlib import contextmanager

import altair as alt
import pandas as pd
import streamlit as st

from alphaforge.agents import HORS_LIGNE, analyser, calculer
from alphaforge.recus import fmt_nombre
from alphaforge.verdict import CONTRATS

st.set_page_config(page_title="AlphaForge AI", page_icon="⏳", layout="wide")

# ======================================================================
# Textes affichés (le moteur garde ses clés sans accents)
# ======================================================================
VERDICTS = {
    "Coherent": {"humain": "Ce placement correspond à votre profil", "technique": "Cohérent",
                 "icone": "✅", "couleur": "green"},
    "A surveiller": {"humain": "Possible, mais à bien réfléchir", "technique": "À surveiller",
                     "icone": "⚠️", "couleur": "orange"},
    "Incoherent": {"humain": "Ce placement ne vous convient pas", "technique": "Incohérent",
                   "icone": "⛔", "couleur": "red"},
}
STATUTS = {"ok": "✅", "depasse": "⚠️", "info_manquante": "❓"}
PERSO = "➕ Mon profil"

# Profil personnalisé : 3 modèles, choisis selon la perte que la personne dit pouvoir supporter.
# Les seuils reprennent ceux des 3 personas (hypothèses de l'équipe, voir contrats.json).
MODELES = {
    "prudent": {"volatilite_max_pct": 12, "poids_max_titre_pct": 10, "poids_max_secteur_pct": 30,
                "crypto_max_pct": 0, "part_stable_min_pct": 40,
                "blocs_coeur": ["XIU.TO", "SPY"], "blocs_stables": ["ZST.TO", "XBB.TO"]},
    "équilibré": {"volatilite_max_pct": 18, "poids_max_titre_pct": 15, "poids_max_secteur_pct": 35,
                  "crypto_max_pct": 2, "part_stable_min_pct": 25,
                  "blocs_coeur": ["SPY", "XIU.TO"], "blocs_stables": ["XBB.TO", "ZST.TO"]},
    "audacieux": {"volatilite_max_pct": 30, "poids_max_titre_pct": 20, "poids_max_secteur_pct": 45,
                  "crypto_max_pct": 10, "part_stable_min_pct": 0,
                  "blocs_coeur": ["SPY", "XIU.TO"], "blocs_stables": ["XBB.TO", "GLD"]},
}


def profil_personnalise(prenom, age, horizon, perte, capital, esg, sans_crypto) -> dict:
    """Construit un contrat fictif à partir de réponses en langage simple."""
    modele = "prudent" if perte <= 15 else "équilibré" if perte <= 25 else "audacieux"
    c = {k: (list(v) if isinstance(v, list) else v) for k, v in MODELES[modele].items()}
    if esg:
        c["blocs_coeur"] = ["ESGV" if t == "SPY" else t for t in c["blocs_coeur"]]
    if sans_crypto:
        c["crypto_max_pct"] = 0
    c.update({
        "age": age, "capital_total": capital, "horizon_annees": horizon,
        "perte_max_toleree_pct": -perte, "exclusions_secteurs": ["Energy"] if esg else [],
        "modele": modele,
        "profil": f"Profil fictif {modele}, besoin de l'argent dans {horizon} ans",
        "description": (f"{prenom}, {age} ans (profil fictif saisi dans l'application). Aura besoin de "
                        f"son argent dans {horizon} ans. Peut supporter une baisse d'au plus {perte} %. "
                        f"Profil {modele}." + (" Souhaite éviter les entreprises liées à des controverses "
                                               "environnementales ou sociales." if esg else "")
                        + (" Ne veut pas de cryptoactifs." if sans_crypto else "")),
    })
    return c


@contextmanager
def calcul_local(actif: bool):
    """La Lambda déployée ne connaît que les 3 personas : un profil personnalisé est calculé
    localement (même code, même Machine, mêmes règles)."""
    sauve = os.environ.pop("ALPHAFORGE_LAMBDA", None) if actif else None
    try:
        yield
    finally:
        if sauve is not None:
            os.environ["ALPHAFORGE_LAMBDA"] = sauve

# Noms compréhensibles pour quelqu'un qui ne connaît pas les symboles boursiers.
NOMS_SIMPLES = {
    "SPY": "un fonds des 500 plus grandes entreprises américaines (SPY)",
    "XIU.TO": "un fonds des 60 plus grandes entreprises canadiennes (XIU)",
    "QQQ": "un fonds des grandes entreprises technologiques américaines (QQQ)",
    "ESGV": "un fonds américain qui exclut les entreprises controversées (ESGV)",
    "ZST.TO": "des obligations à très court terme, très stables (ZST)",
    "XBB.TO": "des obligations canadiennes (XBB)",
    "AGG": "des obligations américaines (AGG)",
    "TLT": "des obligations américaines à très long terme (TLT)",
    "GLD": "de l'or (GLD)",
    "BTC-USD": "du Bitcoin",
    "ETH-USD": "de l'Ether (cryptomonnaie)",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

# Les gabarits hors ligne et les libellés du moteur sont écrits sans accents.
ACCENTS = {
    "Incoherent": "Incohérent", "Coherent": "Cohérent", "A surveiller": "À surveiller",
    "toleree": "tolérée", "Volatilite": "Volatilité", "volatilite": "volatilité",
    "recuperation": "récupération", "documentee": "documentée", "envisage": "envisagé",
    "Resultat": "Résultat", "resultat": "résultat", "periode": "période", "modere": "modéré",
    "preferences": "préférences", "faible a": "faible à", "declare": "déclaré",
    "hypothese": "hypothèse", "Hypothese": "Hypothèse", "esg": "ESG",
    "regles": "règles", "Regles": "Règles", "verite": "vérité", "Verite": "Vérité",
    "Recus": "Reçus", "recus": "reçus", "recu": "reçu", "Recu": "Reçu", "eleve": "élevé",
    "Energy": "Énergie", "energie": "énergie", "Hypotheses": "Hypothèses", "hypotheses": "hypothèses",
    "equipe": "équipe", "le passe": "le passé", "predit": "prédit", "entree": "entrée",
    "entrees": "entrées", "reponse": "réponse", "precedent": "précédent", "apres": "après",
    "Apres": "Après", "depasse": "dépassé", "depassee": "dépassée", "depassees": "dépassées",
    "ete": "été", "regle": "règle", "controle": "contrôle", "controles": "contrôles",
    "evaluation": "évaluation", "Evaluation": "Évaluation", "periodes": "périodes",
    "fenetre": "fenêtre", "fenetres": "fenêtres", "detenu": "détenu", "precisez": "précisez",
    "preciser": "préciser", "cle": "clé", "cles": "clés", "systeme": "système", "genere": "généré",
    "rejouees": "rejouées", "meme": "même", "Duree": "Durée", "testees": "testées",
    "plafonnee": "plafonnée", "annee": "année", "a la date": "à la date", "3 a 5": "3 à 5",
    "8 a 12": "8 à 12",
}
# Mots entiers seulement (ex. « releve » ne doit pas devenir « rélevé »).
_MOTIF = re.compile(r"(?<!\w)(?:" + "|".join(sorted(map(re.escape, ACCENTS), key=len, reverse=True)) + r")(?!\w)")
_REFS = re.compile(r"\s*\[#[RC]-\d{3}\]")


def fr(texte) -> str:
    """Rétablit les accents à l'affichage seulement (aucun chiffre n'est modifié)."""
    return _MOTIF.sub(lambda m: ACCENTS[m.group(0)], str(texte))


def sans_refs(texte: str) -> str:
    """Version lisible d'un texte d'agent : les numéros de reçus restent dans « Les preuves »."""
    return _REFS.sub("", texte)


def argent(x: float) -> str:
    return f"{fmt_nombre(round(x, -2))} $"


def mois_annee(ts) -> str:
    return f"{MOIS[ts.month - 1]} {ts.year}"


def sans_signe(txt: str) -> str:
    return str(txt).replace("−", "").replace("-", "").strip()


def nom_simple(poids: dict) -> str:
    """« 60 % dans un fonds … + 40 % dans des obligations … » ; un seul titre = son nom."""
    def nom(t):
        return NOMS_SIMPLES.get(t, UNIVERS.get(t, t))
    if len(poids) == 1:
        return nom(next(iter(poids)))
    morceaux = []
    for t, w in sorted(poids.items(), key=lambda kv: -kv[1]):
        pct = w * 100 if w <= 1 else w
        morceaux.append(f"{pct:.0f} % dans {nom(t)}")
    return " + ".join(morceaux)


try:
    UNIVERS = pd.read_csv("data/assets_universe.csv").set_index("ticker")["name"].to_dict()
except Exception:  # noqa: BLE001 — affichage seulement
    UNIVERS = {}


def phrase_regle(x: dict) -> str:
    """Traduit un contrôle du contrat en une phrase sans jargon (valeurs = celles du code)."""
    r, val, lim = x["regle"], fr(x["valeur"]), fr(x["limite"])
    if r.startswith("Perte maximale"):
        return (f"Vous avez dit pouvoir supporter une baisse d'au plus **{sans_signe(lim)}**. "
                f"Ce placement est tombé de **{sans_signe(val)}** pendant la période.")
    if r.startswith("Volatilite"):
        return (f"Sa valeur fait des montagnes russes : elle varie typiquement de **{val}** par an, "
                f"alors que votre limite est de **{lim}**.")
    if r.startswith("Cryptoactifs"):
        return f"Les cryptomonnaies représenteraient **{val}** de tout votre argent (votre limite : **{lim}**)."
    if r.startswith("Part stable"):
        return (f"Seulement **{val}** de ce placement est dans des placements stables, "
                f"alors que vous en voulez au moins **{lim}** pour amortir les chutes.")
    if r.startswith("Poids maximal"):
        return (f"Vous mettriez **{val}** de tout votre argent sur un seul placement "
                f"(votre limite : **{lim}**). Si ce placement chute, toute votre épargne en souffre.")
    if r.startswith("Temps de recuperation"):
        return (f"Après la chute, il aurait fallu **{val}** pour retrouver votre mise, "
                f"alors que vous aurez besoin de l'argent dans **{lim}**.")
    if r.startswith("Exclusion ESG"):
        if x["statut"] == "info_manquante":
            return ("Vous souhaitez éviter les entreprises liées à des controverses environnementales "
                    "ou sociales. Ce placement est dans un secteur sensible et **nous n'avons pas de "
                    "source fiable pour trancher** : nous préférons vous le dire plutôt que deviner.")
        return f"Ce secteur fait partie de ce que vous voulez éviter ({val})."
    return f"{fr(r)} : {val} (limite {lim})."


def fiche_recu(r):
    with st.container(border=True):
        st.markdown(f"**{r.id} · {fr(r.libelle)}**")
        st.markdown(f"### {r.affichage}")
        st.caption(f"Période : {fr(r.periode)}  \nCalcul : {fr(r.calcul)}  \n"
                   f"Sources : {r.sources}  \nDevise : {r.devise}")


def pastilles_recus(ids: list, par_id: dict, cle: str):
    """Reçus cliquables en pastilles ; un clic affiche la fiche du reçu juste en dessous."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return
    choix = st.pills("Reçus", ids, key=cle, label_visibility="collapsed",
                     format_func=lambda i: f"🧾 {i}" if i in par_id else f"❓ {i}")
    if choix:
        if choix in par_id:
            fiche_recu(par_id[choix])
        else:
            st.error(f"{choix} : reçu inconnu (le Vérificateur le signale).")


# ======================================================================
# En-tête et barre latérale
# ======================================================================
st.warning("**Simulation sur des données passées (nov. 2021 → nov. 2026).** Personnes fictives. "
           "Ce n'est pas un conseil financier : le passé ne prédit pas l'avenir.")
st.title("⏳ AlphaForge AI")
st.markdown("##### Vivez votre placement avant de le faire.")
if HORS_LIGNE:
    st.caption("Mode hors ligne : textes gabarits, sans appel à Amazon Bedrock.")

with st.sidebar:
    noms = [k for k in ("Robert", "Mateo", "Amira") if k in CONTRATS]
    choix = st.radio("Qui êtes-vous ?", noms + [PERSO], horizontal=True)
    perso = choix == PERSO
    if perso:
        st.caption("Répondez à quelques questions. Le profil reste **fictif** : rien n'est enregistré.")
        prenom = st.text_input("Votre prénom", "Myriam").strip() or "Moi"
        age = st.number_input("Votre âge", 18, 95, 30)
        horizon_p = st.slider("Dans combien d'années aurez-vous besoin de cet argent ?", 1, 30, 10)
        perte_p = st.select_slider("Si votre placement baissait, à partir de quelle perte "
                                   "seriez-vous vraiment inquiet(e) ?",
                                   [5, 10, 15, 20, 25, 30, 40, 50], value=20, format_func=lambda x: f"{x} %")
        capital_p = st.number_input("Votre épargne totale ($, fictive)", 5_000, 5_000_000, 100_000, step=5_000)
        esg_p = st.checkbox("Je veux éviter les entreprises controversées (environnement, social)")
        sans_crypto_p = st.checkbox("Pas de cryptomonnaies pour moi")
        persona = prenom if prenom not in noms else f"{prenom} (vous)"
        CONTRATS[persona] = profil_personnalise(prenom, int(age), int(horizon_p), int(perte_p),
                                                int(capital_p), esg_p, sans_crypto_p)
        cle_profil = f"{persona}|{age}|{horizon_p}|{perte_p}|{capital_p}|{esg_p}|{sans_crypto_p}"
    else:
        persona = choix
        cle_profil = persona
    c = CONTRATS[persona]
    with st.container(border=True):
        st.markdown(f"**{persona}, {c['age']} ans**")
        st.markdown(f"Aura besoin de son argent dans environ **{c['horizon_annees']} ans**.  \n"
                    f"Peut supporter une baisse d'au plus **{sans_signe(c['perte_max_toleree_pct'])} %**.  \n"
                    f"Épargne fictive : **{argent(c['capital_total'])}**.")
        if c.get("exclusions_secteurs"):
            st.markdown("Veut éviter les entreprises controversées (critères ESG).")
        if perso:
            st.caption(f"Profil déduit : **{c['modele']}** (selon la perte acceptée). Les autres limites "
                       "reprennent celles des personas de référence : ce sont des hypothèses.")
    if st.button("Nouvelle conversation", width="stretch"):
        for k in ("messages", "demande", "resultat"):
            st.session_state.pop(k, None)
        st.rerun()

    with st.expander("📖 Petit lexique"):
        st.markdown(
            "**Perte maximale** : la plus grosse chute entre un sommet et le creux qui suit.  \n"
            "**Volatilité** : à quel point la valeur monte et descend d'une année à l'autre.  \n"
            "**Obligation** : un prêt à un gouvernement ou à une entreprise ; en général plus stable "
            "qu'une action.  \n"
            "**Fonds (FNB)** : un panier de nombreux titres acheté d'un seul coup ; c'est une façon "
            "simple de se diversifier.  \n"
            "**Diversifier** : ne pas mettre tous ses œufs dans le même panier.  \n"
            "**Reçu (#R-…)** : la preuve d'un chiffre : son calcul, sa source et sa période.")

    with st.expander("🏗️ Comment ça marche"):
        st.graphviz_chart("""
digraph {
  rankdir=TB; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#f4f4f4", color="#999999", fontname="Helvetica", fontsize=11];
  edge [color="#888888", fontname="Helvetica", fontsize=9];
  app   [label="Application Streamlit"];
  int   [label="Intervieweur\\n(agent IA, Bedrock)"];
  mach  [label="Machine à remonter le temps\\n(code, AWS Lambda)"];
  verd  [label="Règles du contrat\\n(code)"];
  avo   [label="Avocat du diable\\n(agent IA, Bedrock)"];
  expl  [label="Explicateur\\n(agent IA, Bedrock)"];
  veri  [label="Vérificateur de reçus\\n(code)", fillcolor="#e6f0fb", color="#2f6fb3"];
  s3    [label="Amazon S3\\ndonnées, reçus, traces", shape=cylinder];
  app -> int [label=" demande"];
  int -> mach; s3 -> mach [style=dashed];
  mach -> verd [label=" reçus"];
  verd -> avo [label=" verdict"];
  avo -> expl -> veri;
  veri -> app [label=" carte de vérité"];
  veri -> expl [label=" défaut nommé", style=dashed, color="#c0392b", fontcolor="#c0392b"];
}
""", width="stretch")
        st.caption("Le code calcule et décide ; l'IA questionne, conteste et explique. "
                   "Le Vérificateur bloque tout texte dont un chiffre n'a pas de reçu.")

etat = st.session_state
etat.setdefault("messages", [])
etat.setdefault("demande", "")
if etat.get("persona") != cle_profil:
    etat.update(messages=[], demande="", resultat=None, persona=cle_profil)

# ======================================================================
# Conversation
# ======================================================================
for m in etat["messages"]:
    st.chat_message(m["role"]).markdown(fr(m["texte"]))

exemple = argent(min(60_000, c["capital_total"] * 0.3))
saisie = st.chat_input(f"Ex. : Je veux mettre {exemple} dans Tesla (en tant que {persona})")
if saisie:
    etat["messages"].append({"role": "user", "texte": saisie})
    etat["demande"] = (etat["demande"] + " " + saisie).strip()
    with st.spinner("Les agents analysent la demande…"):
        with calcul_local(perso):
            res = analyser(persona, etat["demande"])
    if "question" in res:
        etat["messages"].append({"role": "assistant", "texte": res["question"]})
    else:
        etat["resultat"] = res
        verdict = VERDICTS[res["calc"]["evaluation"]["verdict"]]
        etat["messages"].append({"role": "assistant",
                                 "texte": f"{verdict['icone']} **{verdict['humain']}.** "
                                          "Voici ce que ce placement vous aurait fait vivre."})
    st.rerun()

res = etat.get("resultat")
if not res:
    st.info(f"Vous êtes **{persona}**. Écrivez en bas ce que vous aimeriez faire de votre argent, "
            f"par exemple : *Je veux mettre {exemple} dans Tesla, j'en aurai besoin dans "
            f"{c['horizon_annees']} ans.*")
    st.stop()

onglet_vous, onglet_etsi, onglet_preuves = st.tabs(["💬 Pour vous", "🔁 Et si…", "🧾 Les preuves"])

# ======================================================================
# « Et si… » (calculé en premier : les autres onglets en dépendent)
# ======================================================================
calc = res["calc"]
p = calc["principal"]
ticker = list(p["poids"])[0]
recalcule = False
with onglet_etsi:
    st.markdown("Changez une hypothèse : la Machine à remonter le temps recalcule tout, "
                "puis les règles du contrat rendent un nouveau verdict.")
    c1, c2 = st.columns(2)
    besoin = c1.slider("J'aurai besoin de cet argent dans… (années)", 1, 15,
                       int(calc["contrat"]["horizon_annees"]))
    montant = c2.number_input("Montant placé ($ CA)", 1000, 1_000_000, int(p["montant"]), step=5000)
    if (besoin, montant) != (int(calc["contrat"]["horizon_annees"]), int(p["montant"])):
        with calcul_local(perso):
            calc = calculer(persona, ticker, float(montant), float(besoin))
        p = calc["principal"]
        recalcule = True
        nv = VERDICTS[calc["evaluation"]["verdict"]]
        st.success(f"Nouveau verdict : {nv['icone']} **{nv['humain']}** "
                   "(voir l'onglet « Pour vous »).")
        st.caption("Les textes rédigés par les agents correspondent à la demande initiale ; "
                   "les chiffres et le verdict, eux, sont recalculés par le code.")

ev = calc["evaluation"]
reg = calc["registre"]
par_id = reg.par_id()
rc = p["recus"]
v = res["verification"]
info = VERDICTS[ev["verdict"]]

# ======================================================================
# Onglet 1 : « Pour vous » (sans jargon)
# ======================================================================
with onglet_vous:
    if p["montant"] > c["capital_total"]:
        st.warning(f"Vous voulez placer **{argent(p['montant'])}**, soit plus que votre épargne totale "
                   f"(**{argent(c['capital_total'])}**). Vérifiez le montant : les pourcentages ci-dessous "
                   "dépassent 100 % de votre argent.")
    with st.container(border=True):
        st.markdown(f"## {info['icone']} :{info['couleur']}[{info['humain']}]")
        if recalcule:
            st.caption("Résultat recalculé avec vos hypothèses « Et si… ».")

        # L'histoire : uniquement des valeurs de reçus (ou une soustraction de deux reçus).
        mise, creux = p["montant"], rc["creux"].valeur
        histoire = (f"Si vous aviez placé **{argent(mise)}** dans **{nom_simple(p['poids'])}** "
                    f"en novembre 2021, ")
        if mise - creux < 0.02 * mise:
            histoire += (f"il aurait très peu bougé : au pire moment ({mois_annee(p['date_creux'])}), "
                         f"il valait encore **{rc['creux'].affichage}**.")
        elif creux < mise:
            histoire += (f"au pire moment ({mois_annee(p['date_creux'])}) il ne vous serait resté que "
                         f"**{rc['creux'].affichage}** : une perte de **{argent(mise - creux)}** sur le papier.")
            if "recup" in rc:
                histoire += f" Il aurait ensuite fallu **{rc['recup'].affichage}** pour retrouver votre mise."
            else:
                histoire += " Votre placement n'était **pas encore revenu** à votre mise à la fin de la période."
        else:
            histoire += "votre placement ne serait jamais descendu sous votre mise de départ."
        if "besoin" in rc:
            histoire += (f" Au moment où vous auriez eu besoin de l'argent ({mois_annee(p['date_besoin'])}), "
                         f"il aurait valu **{rc['besoin'].affichage}**.")
        st.markdown("**Ce que vous auriez vécu**")
        st.markdown(histoire)

        problemes = [x for x in ev["controles"] if x["statut"] != "ok"]
        # Honnêteté : une fin heureuse sur CETTE période ne rend pas le placement adapté.
        if ("besoin" in rc and rc["besoin"].valeur >= mise and creux < 0.85 * mise
                and ev["verdict"] != "Coherent"):
            st.info("Ici, tout se termine bien, mais **c'est une question de calendrier** : la chute est "
                    "arrivée assez tôt pour que le placement remonte avant votre besoin d'argent. Si elle "
                    "était arrivée juste avant, vous auriez dû vendre au plus bas.")
        elif (calc["alternatives"] and ev["verdict"] != "Coherent"
              and rc["fin"].valeur > max(a["res"]["recus"]["fin"].valeur for a in calc["alternatives"])):
            st.info("Sur cette période, ce placement a fini **plus haut** que les options proposées. "
                    "Le verdict ne juge pas le gain passé : il juge **la chute qu'il aurait fallu traverser** "
                    "avec vos limites. Rien ne garantit qu'une telle remontée se reproduise.")
        if problemes:
            st.markdown("**Pourquoi c'est important pour vous**")
            for x in problemes:
                st.markdown(f"- {phrase_regle(x)}")
        else:
            st.markdown("**Pourquoi ça vous convient** : toutes les limites que vous nous avez données "
                        "sont respectées.")

    # Le relevé : votre choix contre l'option plus adaptée, seulement 2 courbes.
    alts = calc["alternatives"]
    st.markdown("#### Votre placement, mois par mois")
    courbes = [("Votre choix", p)] + ([("Option plus adaptée", alts[0]["res"])] if alts else [])
    df = pd.concat([pd.DataFrame({"date": s["serie"].index, "valeur": s["serie"].values, "placement": nom})
                    for nom, s in courbes])
    couleurs = alt.Scale(domain=["Votre choix", "Option plus adaptée"], range=["#d64545", "#2e8b57"])
    ligne = alt.Chart(df).mark_line(strokeWidth=2).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y("valeur:Q", title="Valeur de votre placement ($ CA)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("placement:N", scale=couleurs, legend=alt.Legend(orient="top", title=None)),
        tooltip=[alt.Tooltip("placement:N", title=" "), alt.Tooltip("date:T", format="%B %Y", title="Date"),
                 alt.Tooltip("valeur:Q", format=",.0f", title="Valeur ($)")])
    marque = pd.DataFrame([{"date": p["date_creux"], "valeur": creux,
                            "etiquette": f"Pire moment : {rc['creux'].affichage}"}])
    point = alt.Chart(marque).mark_point(size=140, filled=True, color="#d64545").encode(x="date:T", y="valeur:Q")
    texte = alt.Chart(marque).mark_text(dy=18, fontSize=13, fontWeight="bold", color="#d64545").encode(
        x="date:T", y="valeur:Q", text="etiquette:N")
    mise_df = pd.DataFrame({"y": [mise], "date": [p["serie"].index[-1]],
                            "etiquette": [f"Votre mise : {argent(mise)}"]})
    regle = alt.Chart(mise_df).mark_rule(strokeDash=[5, 5], color="gray").encode(y="y:Q")
    regle_txt = alt.Chart(mise_df).mark_text(align="right", dy=14, color="gray", fontWeight="bold").encode(
        x="date:T", y="y:Q", text="etiquette:N")
    st.altair_chart((ligne + regle + regle_txt + point + texte).properties(height=340), width="stretch")

    if alts:
        st.markdown("#### Des options plus adaptées à votre profil")
        cols = st.columns(len(alts))
        for col, a in zip(cols, alts):
            va = VERDICTS[a["eval"]["verdict"]]
            ra = a["res"]["recus"]
            with col, st.container(border=True):
                st.markdown(f"{va['icone']} **{nom_simple(a['res']['poids'])}**")
                st.markdown(f"Au pire moment : **{ra['creux'].affichage}**  \n"
                            + (f"Quand vous auriez eu besoin de l'argent : **{ra['besoin'].affichage}**"
                               if "besoin" in ra else f"À la fin de la période : **{ra['fin'].affichage}**"))

    st.caption(f"🔍 Chaque chiffre de cette page vient d'un calcul vérifiable sur les données réelles "
               f"2021-2026 (onglet « Les preuves »). Fidélité aux reçus : {v['score']:.0f} %.")

# ======================================================================
# Onglet 3 : « Les preuves » (pour le jury et les curieux)
# ======================================================================
with onglet_preuves:
    with st.container(border=True):
        g, d = st.columns([3, 1])
        with g:
            st.markdown(f"### {info['icone']} Verdict des règles : :{info['couleur']}[{info['technique']}]")
            st.caption("Le verdict vient des règles codées du contrat, pas de l'IA.")
            if perso:
                st.caption("Profil personnalisé : calcul fait localement (la Lambda déployée "
                           "connaît seulement Robert, Mateo et Amira).")
        with d:
            st.metric("Fidélité aux reçus", f"{v['score']:.0f} %",
                      help="Part des chiffres du texte qui correspondent à un reçu calculé par le code.")

    col_g, col_d = st.columns([1, 1])
    with col_g:
        st.subheader("Le contrat (hypothèses de l'équipe)")
        st.dataframe(pd.DataFrame({
            "Règle": ["Horizon", "Perte tolérée", "Volatilité max", "Poids max d'un titre",
                      "Crypto max", "Part stable min", "Capital fictif"],
            "Valeur": [f"{c['horizon_annees']} ans", f"{c['perte_max_toleree_pct']} %",
                       f"{c['volatilite_max_pct']} %", f"{c['poids_max_titre_pct']} %",
                       f"{c['crypto_max_pct']} %", f"{c['part_stable_min_pct']} %", argent(c["capital_total"])]}),
            hide_index=True, width="stretch")
    with col_d:
        st.subheader("Les règles vérifiées")
        for i, x in enumerate(ev["controles"]):
            st.markdown(f"{STATUTS[x['statut']]} **{fr(x['regle'])}** : {fr(x['valeur'])} "
                        f"<span style='color:gray'>(limite {fr(x['limite'])})</span>", unsafe_allow_html=True)
            pastilles_recus(x["recus"], par_id, f"ctl{i}")

    st.divider()
    st.subheader("🧾 Carte de vérité (rédigée par l'Explicateur)")
    st.markdown(fr(res["carte"]))
    relances = sum(1 for e in res["trace"] if "essai" in e["action"] and not e["action"].endswith("essai 1"))
    st.caption(f"{len(v['chiffres_verifies'])} chiffres vérifiés · "
               f"relances de correction par le Vérificateur : {relances}")
    a_corriger = (v["chiffres_sans_recu"] + v["recus_inconnus"] + v.get("chiffres_mal_cites", [])
                  + [f"{x} (non cité)" for x in v.get("chiffres_non_cites", [])])
    if a_corriger:
        st.error("À corriger : " + ", ".join(a_corriger))
    if v.get("recus_cites"):
        st.markdown("**Reçus cités dans ce texte** (cliquez pour voir le calcul et la source)")
        pastilles_recus(v["recus_cites"], par_id, "carte")

    with st.expander("🗣️ Réponse de l'Avocat du diable"):
        st.markdown(fr(res["avocat"]))
    with st.expander(f"📑 Les {len(reg.recus)} reçus (calcul, source, période, devise)"):
        tableau = pd.DataFrame(reg.en_dicts())[["id", "libelle", "affichage", "periode", "calcul", "sources", "devise"]]
        for col in ("libelle", "periode", "calcul"):
            tableau[col] = tableau[col].map(fr)
        st.dataframe(tableau.rename(columns={"id": "Reçu", "libelle": "Libellé", "affichage": "Valeur",
                                             "periode": "Période", "calcul": "Calcul", "sources": "Sources",
                                             "devise": "Devise"}),
                     hide_index=True, width="stretch")
    with st.expander("🔍 Trace d'exécution des agents"):
        st.json(res["trace"])
