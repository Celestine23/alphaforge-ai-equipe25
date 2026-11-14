"""Interface AlphaForge AI — lancer :  streamlit run app.py"""
import os

import altair as alt
import pandas as pd
import streamlit as st

from alphaforge.agents import HORS_LIGNE, analyser, calculer
from alphaforge.verdict import CONTRATS

st.set_page_config(page_title="AlphaForge AI", page_icon="⏳", layout="wide")
COULEURS = {"Coherent": "green", "A surveiller": "orange", "Incoherent": "red"}

st.warning("**Simulation — données historiques (12 nov. 2021 → 12 nov. 2026).** "
           "Personas fictifs. Ceci n'est pas un conseil financier et le passé ne prédit pas l'avenir.")
st.title("⏳ AlphaForge AI — Vivez votre placement avant de le faire")
if HORS_LIGNE:
    st.caption("Mode hors ligne : textes gabarits, sans appel à Amazon Bedrock.")

# ---------------- Persona et contrat ----------------
with st.sidebar:
    persona = st.radio("Investisseur", list(CONTRATS.keys())[1:] if "_note" in CONTRATS else list(CONTRATS))
    c = CONTRATS[persona]
    st.subheader(f"Contrat de {persona}")
    st.caption(c["profil"] + " — seuils = hypothèses de l'équipe")
    st.table(pd.DataFrame({
        "Règle": ["Horizon", "Perte tolérée", "Volatilité max", "Poids max d'un titre",
                  "Crypto max", "Part stable min", "Capital fictif"],
        "Valeur": [f"{c['horizon_annees']} ans", f"{c['perte_max_toleree_pct']} %", f"{c['volatilite_max_pct']} %",
                   f"{c['poids_max_titre_pct']} %", f"{c['crypto_max_pct']} %", f"{c['part_stable_min_pct']} %",
                   f"{c['capital_total']:,} $".replace(",", " ")]}).set_index("Règle"))
    if st.button("Nouvelle conversation"):
        st.session_state.clear()
        st.rerun()

etat = st.session_state
etat.setdefault("messages", [])
etat.setdefault("demande", "")
if etat.get("persona") != persona:
    etat.update(messages=[], demande="", resultat=None, persona=persona)

# ---------------- Conversation ----------------
for m in etat["messages"]:
    st.chat_message(m["role"]).write(m["texte"])

saisie = st.chat_input(f"Ex. : Je veux mettre 60 000 $ dans Tesla (en tant que {persona})")
if saisie:
    etat["messages"].append({"role": "user", "texte": saisie})
    etat["demande"] = (etat["demande"] + " " + saisie).strip()
    with st.spinner("Les agents analysent la demande…"):
        res = analyser(persona, etat["demande"])
    if "question" in res:
        etat["messages"].append({"role": "assistant", "texte": res["question"]})
    else:
        etat["resultat"] = res
        etat["messages"].append({"role": "assistant", "texte": res["avocat"]})
    st.rerun()

res = etat.get("resultat")
if not res:
    st.info("Choisissez un investisseur à gauche, puis écrivez sa demande ci-dessous.")
    st.stop()

# ---------------- « Et si… » ----------------
calc = res["calc"]
p = calc["principal"]
ticker = list(p["poids"])[0]
with st.expander("🔁 Et si… (changer une hypothèse)", expanded=False):
    c1, c2 = st.columns(2)
    besoin = c1.slider("Besoin de l'argent dans (années)", 1, 15, int(calc["contrat"]["horizon_annees"]))
    montant = c2.number_input("Montant (CAD)", 1000, 1_000_000, int(p["montant"]), step=5000)
    if (besoin, montant) != (int(calc["contrat"]["horizon_annees"]), int(p["montant"])):
        calc = calculer(persona, ticker, float(montant), float(besoin))
        p = calc["principal"]
        st.caption("Recalcul par la Machine (code) ; les textes des agents correspondent à la demande initiale.")

ev = calc["evaluation"]
reg = calc["registre"]
rc = p["recus"]

# ---------------- Le relevé ----------------
col_g, col_d = st.columns([3, 2])
with col_g:
    st.subheader("Le relevé : ce que votre placement aurait traversé")
    series = [p] + [a["res"] for a in calc["alternatives"]]
    df = pd.concat([pd.DataFrame({"date": s["serie"].index, "valeur": s["serie"].values, "placement": s["nom"]})
                    for s in series])
    ligne = alt.Chart(df).mark_line().encode(
        x=alt.X("date:T", title=None), y=alt.Y("valeur:Q", title="Valeur (CAD)"),
        color=alt.Color("placement:N", legend=alt.Legend(orient="bottom", title=None)))
    marques = pd.DataFrame([
        {"date": p["date_creux"], "valeur": p["serie"].min(), "etiquette": f"Pire moment {rc['creux'].id}"},
    ] + ([{"date": p["date_besoin"], "valeur": rc["besoin"].valeur, "etiquette": f"Besoin d'argent {rc['besoin'].id}"}]
         if "besoin" in rc else []))
    points = alt.Chart(marques).mark_point(size=120, filled=True, color="black").encode(x="date:T", y="valeur:Q")
    textes = alt.Chart(marques).mark_text(dy=-14, fontSize=12).encode(x="date:T", y="valeur:Q", text="etiquette:N")
    regle = alt.Chart(pd.DataFrame({"y": [p["montant"]]})).mark_rule(strokeDash=[4, 4], color="gray").encode(y="y:Q")
    st.altair_chart((ligne + regle + points + textes).properties(height=380), use_container_width=True)

with col_d:
    couleur = COULEURS[ev["verdict"]]
    st.subheader("Verdict (règles du contrat)")
    st.markdown(f"### :{couleur}[{ev['verdict']}]")
    m1, m2, m3 = st.columns(3)
    m1.metric("Pire moment", rc["creux"].affichage, help=rc["creux"].id)
    m2.metric("Perte max", rc["perte_max"].affichage, help=rc["perte_max"].id)
    m3.metric("En 2022", rc["an2022"].affichage, help=rc["an2022"].id)
    icone = {"ok": "✅", "depasse": "⚠️", "info_manquante": "❓"}
    for x in ev["controles"]:
        st.write(f"{icone[x['statut']]} **{x['regle']}** : {x['valeur']} (limite {x['limite']}) "
                 f"{' '.join(x['recus'])}")
    for a in calc["alternatives"]:
        st.write(f"➡️ {a['nom']} — **{a['eval']['verdict']}**, pire moment {a['res']['recus']['creux'].affichage} "
                 f"{a['res']['recus']['creux'].id}")

# ---------------- Carte de vérité ----------------
st.divider()
v = res["verification"]
c1, c2 = st.columns([3, 1])
with c1:
    st.subheader("🧾 Carte de vérité")
    st.markdown(res["carte"])
with c2:
    st.metric("Fidélité aux reçus", f"{v['score']:.0f} %")
    st.caption(f"{len(v['chiffres_verifies'])} chiffres vérifiés")
    relances = sum(1 for e in res["trace"] if "essai" in e["action"] and not e["action"].endswith("essai 1"))
    st.caption(f"Relances de correction par le Vérificateur : {relances}")
    if v["chiffres_sans_recu"] or v["recus_inconnus"] or v.get("chiffres_mal_cites"):
        st.error("À corriger : " + ", ".join(v["chiffres_sans_recu"] + v["recus_inconnus"] + v.get("chiffres_mal_cites", [])))

with st.expander(f"📑 Les {len(reg.recus)} reçus (calcul, source, période, devise)"):
    st.dataframe(pd.DataFrame(reg.en_dicts())[["id", "libelle", "affichage", "periode", "calcul", "sources", "devise"]],
                 hide_index=True, use_container_width=True)
with st.expander("🔍 Trace d'exécution des agents"):
    st.json(res["trace"])
