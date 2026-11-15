# Données, méthodes et validations

*Responsable : Habib (Lead Data Scientist). Version du 14 novembre 2026, à jour avec les changements de Celestine de 18 h. Ce texte est le premier jet de la section du même nom dans la documentation technique.*

## 1. Données utilisées

| Fichier | Contenu | Source | Usage dans AlphaForge |
|---|---|---|---|
| `prices_daily.csv` | Prix quotidiens de 31 actifs, 2021-11-12 au 2026-11-12 | Yahoo Finance (bibliothèque `yfinance`), extrait le 2026-11-13 | Rendements calculés sur `adj_close` (ajusté pour dividendes et fractionnements) |
| `fx_usdcad_daily.csv` | Taux USD/CAD | Banque du Canada (API Valet) | Conversion en CAD des actifs américains et de la crypto |
| `assets_universe.csv` | Classe d'actif et secteur de chaque titre | Organisateurs | Règles du contrat (crypto, part stable, exclusions ESG) |
| `contrats.json` | Seuils des 3 personas | Hypothèses de l'équipe | Verdicts |

Aucune donnée ESG n'est fournie. Quand une exclusion ESG ne peut pas être justifiée par une source publique, l'outil affiche « information manquante » au lieu d'inventer une conclusion (cas de Mateo et Exxon).

## 2. Méthodes de calcul (`alphaforge/machine.py`)

- **Montants en CAD.** Prix américains × taux USD/CAD du même jour ; les jours sans taux publié (fériés canadiens, fins de semaine pour la crypto), on reprend le dernier taux connu.
- **Dividendes réinvestis.** Tous les rendements utilisent `adj_close`.
- **Volatilité annuelle** : écart-type des rendements journaliers en logarithme × √252 (actions, FNB) ou × √365 (crypto, qui cote 7 jours sur 7).
- **Perte maximale** : pire chute entre un plus haut et le creux qui suit (`valeur / plus haut précédent − 1`).
- **Valeur au pire moment** : montant investi × prix au plus bas / prix de départ. Ce n'est pas la même chose que la perte maximale : la perte maximale part du **sommet**, la valeur au pire moment part du **montant investi**. Exemple Tesla : perte maximale −71 %, mais 60 000 $ investis ne sont jamais descendus sous 20 500 $, parce que Tesla avait d'abord monté.
- **Résultat 2022** : valeur au 31 décembre 2022 / valeur au 31 décembre 2021 − 1.

## 3. Validation : recalcul indépendant

J'ai recalculé 18 chiffres **sans le code de l'équipe** (méthode écrite séparément : `merge_asof` pour le change, boucle simple pour la perte maximale), puis je les ai comparés aux reçus. Notebook : `notebooks/validation_habib.ipynb`. Tableau complet : `docs/validation_tableau.csv`.

| Actif | Volatilité | Perte maximale | Résultat 2022 | Verdict |
|---|---|---|---|---|
| TSLA | 58,79 % | −70,88 % | −62,64 % | 3/3 validés |
| SPY | 16,65 % | −22,25 % | −12,59 % | 3/3 validés |
| XIU.TO | 13,07 % | −16,36 % | −6,35 % | 3/3 validés |
| ZST.TO | 0,56 % | −0,43 % | +1,22 % | 3/3 validés |
| BTC-USD | 50,28 % | −74,18 % | −61,82 % | 3/3 validés |
| XOM | 26,02 % | −19,08 % | +100,21 % | 3/3 validés |

**Résultat : 18 chiffres sur 18 identiques (écart inférieur à 0,01 point).**

**Le cas Exxon.** « 30 000 $ deviennent 106 500 $ » paraît trop beau, mais il se décompose en trois effets réels : prix de l'action ×2,66, dividendes réinvestis ×1,18, baisse du dollar canadien ×1,13. Total ×3,55. Le chiffre est juste.

## 4. Pièges des données traités

| Piège | Ce que j'ai vérifié | Conclusion |
|---|---|---|
| CNQ.TO, « fractionnement » de 1,021 le 2022-08-22 | Le saut de `adj_close` ce jour-là (+2,2 points) correspond au dividende de 0,75 $ (2,1 % du prix) | Pas de double comptage. CNQ n'est dans aucun scénario de démo |
| Crypto 7 jours sur 7 | BTC et ETH ont 1 827 lignes, contre 1 255 pour les actions | Correct pour un actif seul (× √365). **Écart pour un portefeuille mixte** : voir point 6 |
| Conversion USD/CAD | 582 jours de cotation sans taux publié ; contrôle ponctuel SPY le 2022-12-30 identique au centime | Correct |
| ZST.TO, volume nul le 2022-07-06 | Prix cohérent avec les jours voisins | Aucun effet |

## 5. Validation du Vérificateur et du garde-fou

Test automatique : `scripts/test_verificateur.py` (20 cas). Il couvre les cas de la roadmap (chiffre inventé, bon chiffre avec le mauvais reçu, reçu inexistant, montant faux), la règle « citation obligatoire » ajoutée par Celestine (un chiffre juste mais sans numéro de reçu plafonne la fidélité à 90 %) et le garde-fou bloquant (texte refusé, défaut nommé, relance, texte de secours affiché et signalé).

**Faille trouvée et corrigée : le sens du chiffre.** Le Vérificateur acceptait à 100 % « Tesla a **gagné** 71 % [#R-008] », alors que le reçu #R-008 vaut **−71 %** (une perte). Il ignorait le signe pour accepter « a perdu 71 % ». C'est l'erreur la plus grave possible pour Robert : une perte présentée comme un gain. 4 cas de ce type passaient avant le correctif. Le Vérificateur compare maintenant le sens annoncé par le texte (signe moins, ou mots comme « perdu », « baisse », « gagné », « hausse ») au signe du reçu. Le correctif a été intégré dans la version du Vérificateur de Celestine, sans rien retirer de sa règle. Résultat : 20/20 tests réussis. Sur sa version sans le correctif, les 4 cas de sens inversé passent encore (13/18).

Test des 7 scénarios de `docs/scenarios.md` : `scripts/test_scenarios.py`, 7/7 conformes, fidélité 100 %.

## 6. Écarts trouvés et suite donnée

1. **Règle crypto calculée sur le placement, pas sur le capital** (`verdict.py`). Amira qui plaçait 5 000 $ en Bitcoin (5 % de son capital, sous sa limite de 10 %) obtenait « Incohérent ». **Corrigé par Celestine** (version de 18 h) : la règle et son reçu sont maintenant calculés sur le capital total. Vérifié par les scénarios 5 et 6 de `docs/scenarios.md` (15 000 $ : Incohérent ; 10 000 $ : À surveiller).
2. **Volatilité d'un portefeuille qui mélange crypto et actions** (`machine.py`). **Toujours ouvert, à décider en équipe.** La série a environ 365 points par an mais elle est annualisée avec √252 : pour 85 % SPY + 15 % BTC, la volatilité affichée est de 14,6 % au lieu de 17,6 %. Aucun scénario de démo n'est touché. Correctif proposé : `n_an = 365 if any(t.endswith("-USD") for t in poids) else 252`.
3. **Arrondi trompeur à l'affichage.** Robert + XBB.TO : perte maximale −15,48 %, affichée « −15 % » face à une limite de « −15 % ». Depuis la règle « de peu » de Celestine, le verdict est « À surveiller » (scénario 3), ce qui est cohérent. Mais l'affichage « −15 % contre −15 % » peut encore surprendre un juge. Proposition : afficher une décimale quand la valeur est à moins d'un point de la limite. **À décider.**

## 7. Limites

- Une seule période historique (2021-2026). Le passé ne prédit pas l'avenir.
- Biais du survivant : les 31 actifs ont été choisis en 2026 parmi des titres aujourd'hui importants.
- `adj_close` est recalculé par Yahoo à chaque téléchargement : les valeurs anciennes peuvent changer si les données sont téléchargées de nouveau.
- Les seuils des contrats sont des hypothèses de l'équipe pour des personas fictifs.
