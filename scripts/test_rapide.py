"""Test de bout en bout SANS IA : Robert + Tesla, puis Amira + Tesla.
Lancer depuis la racine du repo :
    Windows :  set ALPHAFORGE_HORS_LIGNE=1 && python scripts/test_rapide.py
    Mac/Linux: ALPHAFORGE_HORS_LIGNE=1 python scripts/test_rapide.py
Sans la variable, le script appelle Amazon Bedrock (BEDROCK_MODEL_ID requis).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alphaforge.agents import analyser  # noqa: E402

for persona, demande in [
    ("Robert", "Je veux mettre 60 000 $ dans Tesla, tout le monde en parle."),
    ("Robert", "Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 4 ans."),
    ("Amira", "Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 15 ans."),
    ("Mateo", "Je veux mettre 30 000 $ dans Exxon, j'en aurai besoin dans 10 ans."),
]:
    print("=" * 80, f"\n{persona} : {demande}")
    s = analyser(persona, demande)
    if "question" in s:
        print("QUESTION DE L'INTERVIEWEUR :", s["question"])
        continue
    ev = s["calc"]["evaluation"]
    print("VERDICT :", ev["verdict"])
    for c in ev["controles"]:
        print(f"  [{c['statut']:>14}] {c['regle']} : {c['valeur']} (limite {c['limite']}) {c['recus']}")
    for a in s["calc"]["alternatives"]:
        print("  ->", a["nom"], ":", a["eval"]["verdict"])
    print("RECUS :", len(s["calc"]["registre"].recus))
    for r in s["calc"]["registre"].recus[6:12]:
        print("  ", r.id, r.libelle, "=", r.affichage)
    print("AVOCAT :", s["avocat"][:400])
    print("FIDELITE :", s["verification"]["score"], "% | sans recu :", s["verification"]["chiffres_sans_recu"])
