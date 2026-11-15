"""Tests automatiques du Verificateur et du garde-fou bloquant (aucune IA, aucun AWS).

Lancer depuis la racine du repo :
    Mac/Linux : ALPHAFORGE_HORS_LIGNE=1 python3 scripts/test_verificateur.py
    Windows   : $env:ALPHAFORGE_HORS_LIGNE="1"; python scripts/test_verificateur.py

Chaque cas donne un texte et ce que le Verificateur doit en penser :
  "accepte" = score de 100 %, "refuse" = score de 50 % ou moins,
  "partiel" = entre les deux (chiffre juste mais sans numero de recu : 90 %).
Responsable : Habib (validation des chiffres).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ALPHAFORGE_HORS_LIGNE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alphaforge.agents as A  # noqa: E402
from alphaforge.agents import calculer  # noqa: E402
from alphaforge.verificateur import verifier  # noqa: E402

# Robert + Tesla : #R-007 volatilite 59 %, #R-008 perte max −71 %, #R-009 pire moment 20 500 $,
# #R-010 resultat 2022 −63 %
robert = calculer("Robert", "TSLA", 60000, 4)["registre"].recus
# Mateo + Exxon : #R-010 resultat 2022 +100 %
mateo = calculer("Mateo", "XOM", 30000, 10)["registre"].recus

CAS = [
    # (recus, texte, attendu, ce que le cas prouve)
    (robert, "Tesla a perdu −71 % [#R-008].", "accepte", "chiffre exact, recu exact"),
    (robert, "Tesla a perdu 71 % [#R-008].", "accepte", "« perdu » sans signe moins : accepte"),
    (robert, "Sa volatilite annuelle est de 59 % [#R-007].", "accepte", "volatilite exacte"),
    (robert, "Au pire moment, le placement valait 20 500 $ [#R-009].", "accepte", "montant arrondi"),
    (robert, "En 2022, Tesla a recule de 63 % [#R-010].", "accepte", "baisse annoncee en mots"),
    (robert, "Tesla a perdu −63 % [#R-008].", "refuse", "bon chiffre, MAUVAIS recu"),
    (robert, "Tesla a perdu −80 % [#R-008].", "refuse", "chiffre invente"),
    (robert, "Tesla a perdu −80 %.", "refuse", "chiffre invente, sans recu"),
    (robert, "Tesla a perdu −71 %.", "partiel", "chiffre exact mais NON CITE (regle de Celestine : 90 %)"),
    (robert, "Tesla a perdu −71 % [#R-999].", "refuse", "recu qui n'existe pas"),
    (robert, "Au pire moment, le placement valait 25 000 $ [#R-009].", "refuse", "montant faux"),
    (robert, "Tesla a gagne 71 % [#R-008].", "refuse", "SENS INVERSE : une perte presentee comme un gain"),
    (robert, "Tesla a progresse de 71 %.", "refuse", "SENS INVERSE, sans recu"),
    (robert, "En 2022, Tesla a bondi de 63 % [#R-010].", "refuse", "SENS INVERSE sur 2022"),
    (robert, "Au pire moment, le 3 janvier 2023, le placement valait 20 500 $ [#R-009].", "accepte",
     "date ecrite en mots : « 3 janvier » n'est pas un chiffre a sourcer"),
    (robert, "Le 20 octobre, Tesla a perdu 80 %.", "refuse", "date en mots ignoree, mais −80 % reste invente"),
    (mateo, "En 2022, Exxon a progresse de 100 % [#R-010].", "accepte", "hausse exacte"),
    (mateo, "En 2022, Exxon a perdu 100 % [#R-010].", "refuse", "SENS INVERSE : un gain presente comme une perte"),
]


def main() -> int:
    echecs = 0
    print(f"{'resultat':9} {'score':>6}  {'attendu':8} cas")
    for recus, texte, attendu, quoi in CAS:
        v = verifier(texte, recus)
        obtenu = "accepte" if v["score"] == 100.0 else "refuse" if v["score"] <= 50.0 else "partiel"
        ok = obtenu == attendu
        echecs += not ok
        print(f"{'OK' if ok else 'ECHEC':9} {v['score']:6.1f}  {attendu:8} {quoi} : {texte}")

    # Garde-fou bloquant : une IA simulee se trompe, puis se corrige (exemple de la roadmap)
    A.HORS_LIGNE = False
    journal = []
    rep = iter(["Tesla a perdu −80 % [#R-008].", "Tesla a perdu −71 % [#R-008]."])
    txt = A._rediger_sous_garde("Explicateur", "p", "ctx", robert, lambda: "SECOURS",
                                lambda *a: journal.append(a), appel_ia=lambda p, m: next(rep))
    ok1 = txt == "Tesla a perdu −71 % [#R-008]." and len(journal) == 2
    print(f"{'OK' if ok1 else 'ECHEC':9} garde-fou : essai 1 refuse (defaut nomme), essai 2 accepte")

    # Garde-fou : l'IA s'entete, le texte de secours du code est affiche et signale
    journal = []
    rep = iter(["Tesla a gagne 71 % [#R-008]."] * 3)
    txt = A._rediger_sous_garde("Explicateur", "p", "ctx", robert, lambda: "SECOURS",
                                lambda *a: journal.append(a), appel_ia=lambda p, m: next(rep))
    ok2 = txt.endswith("SECOURS") and "bloqu" in txt and len(journal) == 4  # « bloque » ou « bloqué » (V5)
    print(f"{'OK' if ok2 else 'ECHEC':9} garde-fou : 3 essais refuses, texte de secours affiche et signale")
    A.HORS_LIGNE = True

    echecs += (not ok1) + (not ok2)
    total = len(CAS) + 2
    print(f"\n{total - echecs}/{total} tests reussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
