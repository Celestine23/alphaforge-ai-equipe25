"""Test d'acceptation des scenarios de docs/scenarios.md (aucune IA, aucun AWS).

Lancer depuis la racine du repo :
    Mac/Linux : python3 scripts/test_scenarios.py
    Windows   : python scripts/test_scenarios.py

Pour chaque scenario : le verdict attendu et une fidelite de 100 % sur les textes affiches.
La liste SCENARIOS reprend le tableau de docs/scenarios.md (Celestine) : si un verdict
attendu change dans ce document, le changer ici aussi.
Responsable : Habib (validation des chiffres).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ALPHAFORGE_HORS_LIGNE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alphaforge.agents import analyser  # noqa: E402

SCENARIOS = [
    # (numero dans docs/scenarios.md, persona, demande, verdict attendu, statut supplementaire attendu ou None)
    (1, "Robert", "Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 4 ans.", "Incoherent", None),
    (2, "Robert", "Je veux mettre 60 000 $ dans ZST, j'en aurai besoin dans 4 ans.", "Coherent", None),
    (3, "Robert", "Je veux mettre 60 000 $ dans XBB, j'en aurai besoin dans 4 ans.", "A surveiller", None),
    (4, "Amira", "Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 15 ans.", "A surveiller", None),
    (5, "Amira", "Je veux mettre 15 000 $ dans Bitcoin, j'en aurai besoin dans 15 ans.", "Incoherent", None),
    (6, "Amira", "Je veux mettre 10 000 $ dans Bitcoin, j'en aurai besoin dans 15 ans.", "A surveiller", None),
    (7, "Mateo", "Je veux mettre 30 000 $ dans Exxon, j'en aurai besoin dans 10 ans.", "A surveiller", "info_manquante"),
]


def main() -> int:
    echecs = 0
    for num, persona, demande, attendu, statut_attendu in SCENARIOS:
        s = analyser(persona, demande)
        if "question" in s:
            print(f"ECHEC  {num}. {persona} : l'Intervieweur pose une question ({s['question']})")
            echecs += 1
            continue
        ev = s["calc"]["evaluation"]
        fid = s["verification"]["score"]
        ok = ev["verdict"] == attendu and fid == 100.0
        if statut_attendu:
            ok = ok and any(c["statut"] == statut_attendu for c in ev["controles"])
        echecs += not ok
        print(f"{'OK' if ok else 'ECHEC':6} {num}. {persona:6} | attendu {attendu:12} | obtenu {ev['verdict']:12}"
              f" | fidelite {fid:5.1f} % | {demande}")
        if not ok:
            v = s["verification"]
            for cle in ("chiffres_sans_recu", "chiffres_mal_cites", "chiffres_non_cites"):
                if v.get(cle):
                    print(f"         {cle} : {v[cle]}")

    print(f"\n{len(SCENARIOS) - echecs}/{len(SCENARIOS)} scenarios conformes")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
