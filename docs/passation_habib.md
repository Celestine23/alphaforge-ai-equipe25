# Note de passation — Habib (Lead Data Scientist)

*Rédigée le samedi 14 novembre, à jour avec les changements de Celestine de 18 h. Je pars dimanche à 13 h. Pour toute question avant mon départ : Habib.*

## Ce qui marche

| Livrable | Fichier | Comment le vérifier |
|---|---|---|
| Validation des chiffres (18/18 identiques aux reçus) | `notebooks/validation_habib.ipynb`, `docs/validation_tableau.csv` | Ouvrir le notebook, *Run All* : section 2 affiche « 18 / 18 chiffres validés » |
| Vérificateur : contrôle du sens des chiffres, ajouté à la version de Celestine (citation obligatoire conservée) | `alphaforge/verificateur.py` | `python3 scripts/test_verificateur.py` → `20/20 tests reussis` |
| Test des 7 scénarios de `docs/scenarios.md` | `scripts/test_scenarios.py` | `python3 scripts/test_scenarios.py` → `7/7 scenarios conformes` |
| Section « Données, méthodes et validations » (premier jet) | `docs/validation_habib.md` | À intégrer telle quelle dans la documentation technique |
| Constats pour le pitch | Document « Pour le pitch » envoyé à Celestine | Chiffres issus du notebook, section 6 |

Les deux tests fonctionnent **sans IA et sans AWS** (mode hors ligne activé automatiquement).

## Comment relancer depuis zéro

```bash
cd alphaforge-ai-equipe25
python3 -m pip install -r requirements.txt
python3 scripts/test_verificateur.py
python3 scripts/test_scenarios.py
ALPHAFORGE_HORS_LIGNE=1 python3 scripts/test_rapide.py
```
Sous Windows : `python` au lieu de `python3`, et `$env:ALPHAFORGE_HORS_LIGNE="1"; python scripts/test_rapide.py`.

## Ce qui reste (décisions d'équipe)

1. ~~Règle crypto calculée sur le placement~~ : **corrigé par Celestine** (18 h), vérifié par les scénarios 5 et 6.
2. **Volatilité des portefeuilles mixtes crypto + actions** sous-estimée (√252 au lieu de √365). Correctif d'une ligne dans `machine.py`, détaillé dans `docs/validation_habib.md`, point 6.2. Aucun scénario de démo touché. Décision : [à remplir].
3. **Arrondi trompeur près des limites** (XBB : « −15 % » face à une limite de « −15 % » ; le verdict « À surveiller » est juste depuis la règle « de peu » de Celestine, mais l'affichage peut surprendre). Proposition : une décimale près de la limite. Décision : [à remplir].
4. **ESGV a plus baissé que SPY en 2022** : l'hypothèse « les fonds ESG excluent l'énergie » est à vérifier sur la page méthodologique de Vanguard avant de la dire au jury.

## Si un chiffre change

- Les chiffres changent seulement si `data/` ou `alphaforge/machine.py` change. Dans ce cas, relancer le notebook (*Run All*) : le tableau `docs/validation_tableau.csv` est réécrit automatiquement.
- Si `docs/scenarios.md` change un verdict attendu, modifier la liste `SCENARIOS` en haut de `scripts/test_scenarios.py`.
- Si un test échoue après une modification : la ligne `ECHEC` dit quel cas et pourquoi. Ne pas « corriger » le test pour qu'il passe sans comprendre l'écart.
