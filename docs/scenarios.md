# Scénarios de validation — AlphaForge AI

Ces scénarios servent de **tests d'acceptation**. Pour chaque demande, l'équipe a fixé à l'avance le verdict attendu, puis vérifié que l'application le produit.

Données : relecture du 12 novembre 2021 au 12 novembre 2026, en CAD. Seuils des contrats : hypothèses de l'équipe (`alphaforge/contrats.json`).

| # | Persona | Demande | Verdict attendu | Pourquoi (logique de conseil) | Obtenu | Fidélité |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Robert | « Je veux mettre 60 000 $ dans Tesla, j'en aurai besoin dans 4 ans » | Incohérent | Perte maximale de −71 % contre −15 % tolérés, alors que l'argent sera nécessaire à la retraite ; volatilité, part stable et poids par titre également dépassés | Incohérent | 100 % |
| 2 | Robert | « 60 000 $ dans ZST, dans 4 ans » | Cohérent | Cas témoin : obligations ultra-courtes, perte maximale quasi nulle, conforme à un profil prudent | Cohérent | 100 % |
| 3 | Robert | « 60 000 $ dans XBB, dans 4 ans » | À surveiller | Piège pédagogique : une obligation n'est pas sans risque. XBB a perdu −15 % en 2022, soit juste au-delà de la limite (dépassement « de peu ») | À surveiller | 100 % |
| 4 | Amira | « 60 000 $ dans Tesla, dans 15 ans » | À surveiller | Son horizon long permet d'absorber la baisse, mais 60 % du capital dans un seul titre contredit son souhait de diversification | À surveiller | 100 % |
| 5 | Amira | « 15 000 $ en Bitcoin, dans 15 ans » | Incohérent | La crypto représenterait 15 % de son capital, au-delà de son plafond de 10 % (règle clé) | Incohérent | 100 % |
| 6 | Amira | « 10 000 $ en Bitcoin, dans 15 ans » | À surveiller | Même actif, mais 10 % du capital : le plafond est respecté ; la volatilité reste signalée | À surveiller | 100 % |
| 7 | Mateo | « 30 000 $ dans Exxon, dans 10 ans » | À surveiller | Secteur de l'énergie : aucune source ESG documentée, donc le système dit « information manquante » au lieu d'inventer une controverse | À surveiller | 100 % |

Les colonnes **Obtenu** et **Fidélité** viennent du mode sans IA (`scripts/test_scenarios.py`, 7/7 conformes). Le verdict est calculé par le code (`verdict.py`), sans IA : il est le même avec Bedrock. La fidélité, elle, porte sur le texte rédigé par les agents ; avec Bedrock, chaque texte est contrôlé à chaque analyse par le Vérificateur et son score est affiché dans l'onglet « Les preuves ».

## Ce que les scénarios démontrent

- **Le système conteste** une demande incohérente avec le profil (scénario 1 : le test de Robert).
- **« Risque élevé » ne veut pas dire « tout est permis »** : la diversification et le plafond crypto s'appliquent (scénarios 4 et 5).
- **Le même actif peut être acceptable ou non selon le montant** (scénarios 5 et 6).
- **Le système s'abstient au lieu d'inventer** quand une information manque (scénario 7).
- **Aucun actif n'est « sûr » par nature** : même une obligation peut dépasser une limite (scénario 3).
