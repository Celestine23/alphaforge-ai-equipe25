"""Orchestration : 3 agents IA (Strands + Amazon Bedrock) et 2 outils de calcul.

Le code calcule et decide (Machine, regles du contrat, Verificateur) ;
l'IA questionne (Intervieweur), conteste (Avocat du diable) et explique (Explicateur).

Variables d'environnement :
  BEDROCK_MODEL_ID       identifiant du modele (copie depuis la console Bedrock)
  AWS_REGION             region des organisateurs (ex. ca-central-1)
  ALPHAFORGE_HORS_LIGNE  =1 pour tester sans IA (textes gabarits)
  ALPHAFORGE_BUCKET      compartiment S3 ou ecrire les traces (facultatif)
"""
import datetime as dt
import json
import os
import re
import time
import uuid

from .machine import rejouer, univers
from .recus import Registre
from .verdict import alternatives, contrat, evaluer, recus_contrat
from .verificateur import verifier

HORS_LIGNE = os.environ.get("ALPHAFORGE_HORS_LIGNE") == "1"
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "")
REGION = os.environ.get("AWS_REGION", "ca-central-1")

PROMPT_INTERVIEWEUR = """Tu es l'Intervieweur d'AlphaForge AI, un assistant de SIMULATION (pas un conseil financier).
On te donne le profil d'un investisseur fictif et sa demande. Reponds UNIQUEMENT par un objet JSON :
{"ticker": "<symbole exact de la liste ou null>", "montant": <nombre en CAD ou null>,
 "besoin_annees": <nombre ou null>, "question": "<une seule question si une information cle manque, sinon null>"}
Le besoin_annees est le delai avant que la personne ait besoin de cet argent. Ne l'invente jamais :
s'il n'est pas dit, pose la question. Utilise seulement les symboles de la liste fournie."""

PROMPT_AVOCAT = """Tu es l'Avocat du diable d'AlphaForge AI (SIMULATION, pas un conseil financier).
Le verdict est DEJA rendu par les regles du contrat : tu ne le changes jamais.
Ecris 3 a 5 phrases en francais, au vouvoiement, pour la personne : conteste la demande si le verdict
n'est pas « Coherent », explique pourquoi avec ses propres limites, puis presente les alternatives.
Regle absolue : chaque chiffre que tu ecris doit venir de la liste des recus et etre suivi de son numero
entre crochets, ex. « −71 % [#R-002] ». N'ecris aucun autre chiffre. Ne dis jamais « achetez ».
Si une information manque (ex. aucune source ESG documentee), dis clairement que tu ne peux pas conclure
sur ce point au lieu d'inventer une justification."""

PROMPT_EXPLICATEUR = """Tu es l'Explicateur d'AlphaForge AI (SIMULATION, pas un conseil financier).
Redige la carte de verite en francais, en 5 sections courtes avec ces titres exacts :
Faits / Pourquoi c'est important pour vous / Hypotheses / Limites / Ce qui changerait la reponse.
Regle absolue : chaque chiffre doit venir de la liste des recus, suivi de son numero entre crochets.
Aucun autre chiffre. Distingue clairement faits (donnees) et hypotheses (contrat de l'equipe).
Dans Limites, mentionne : une seule periode historique, le passe ne predit pas l'avenir,
biais du survivant (actifs choisis en 2026). Si une information manque (ex. ESG), ecris
« information manquante : impossible de conclure » plutot que d'inventer."""


def _agent(prompt_systeme: str):
    from strands import Agent
    from strands.models import BedrockModel
    modele = BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.2)
    return Agent(model=modele, system_prompt=prompt_systeme, callback_handler=None)


def _appel_ia(prompt_systeme: str, message: str) -> str:
    return str(_agent(prompt_systeme)(message)).strip()


# ---------------- Intervieweur ----------------
def _interview_hors_ligne(demande: str) -> dict:
    u = univers()
    t = None
    for tick, row in u.iterrows():
        nom = row["name"].split(" (")[0].split()[0].lower()
        if re.search(rf"\b{re.escape(tick.split('.')[0].split('-')[0].lower())}\b|\b{nom}\b", demande.lower()):
            t = tick
            break
    m = re.search(r"(\d{1,3}(?:[  ]?\d{3})+|\d+)\s*(k|000)?\s*\$", demande)
    montant = None
    if m:
        montant = float(m.group(1).replace(" ", "").replace(" ", ""))
        montant *= 1000 if m.group(2) == "k" else 1
    a = re.search(r"(\d+)\s*ans", demande)
    besoin = float(a.group(1)) if a else None
    question = None
    if t is None:
        question = "Quel placement envisagez-vous exactement ?"
    elif besoin is None:
        question = "Dans combien de temps pensez-vous avoir besoin de cet argent ?"
    return {"ticker": t, "montant": montant, "besoin_annees": besoin, "question": question}


def interviewer(persona: str, demande: str) -> dict:
    if HORS_LIGNE:
        return _interview_hors_ligne(demande)
    liste = ", ".join(f"{t} ({r['name']})" for t, r in univers().iterrows())
    txt = _appel_ia(PROMPT_INTERVIEWEUR,
                    f"Profil : {persona}, {contrat(persona)['profil']}\nActifs : {liste}\nDemande : {demande}")
    try:
        return json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
    except Exception:
        return _interview_hors_ligne(demande)


# ---------------- Calcul (local ou AWS Lambda) ----------------
def calculer(persona: str, ticker: str, montant: float, besoin: float, **modifs) -> dict:
    """Machine + regles du contrat + alternatives. Si ALPHAFORGE_LAMBDA (nom de la fonction)
    est defini, le calcul s'execute dans AWS Lambda (voir lambda_function.py)."""
    fonction = os.environ.get("ALPHAFORGE_LAMBDA")
    if fonction and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and not modifs:
        import boto3
        from .serialisation import depuis_json
        rep = boto3.client("lambda", region_name=REGION).invoke(
            FunctionName=fonction,
            Payload=json.dumps({"persona": persona, "ticker": ticker, "montant": montant, "besoin": besoin}))
        charge = json.loads(rep["Payload"].read())
        if "errorMessage" in charge:
            raise RuntimeError(f"Lambda : {charge['errorMessage']}")
        return depuis_json(charge)
    return _calculer_local(persona, ticker, montant, besoin, **modifs)


def _calculer_local(persona: str, ticker: str, montant: float, besoin: float, **modifs) -> dict:
    c = contrat(persona, horizon_annees=besoin, **modifs)
    reg = Registre("R")
    rc = recus_contrat(c, persona, reg)
    nom = f"{ticker} ({univers().loc[ticker, 'name']})"
    res = rejouer({ticker: 1.0}, montant, besoin, reg, nom)
    ev = evaluer(c, res, montant / c["capital_total"], rc)
    r_poids = reg.ajouter("Poids de ce placement dans votre capital total", montant / c["capital_total"] * 100,
                          "%", f"contrat de {persona}", "montant / capital total fictif", "contrats.json")
    from .verdict import _composition
    comp = _composition(res["poids"])
    r_crypto = reg.ajouter("Part de cryptoactifs de ce placement", comp["crypto"], "%", "composition",
                           "classe d'actif (assets_universe.csv)", "assets_universe.csv")
    r_stable = reg.ajouter("Part stable (obligations) de ce placement", comp["stable"], "%", "composition",
                           "classe d'actif (assets_universe.csv)", "assets_universe.csv")
    for ctl in ev["controles"]:
        if ctl["regle"].startswith("Poids maximal"):
            ctl["recus"].insert(0, r_poids.id)
        elif ctl["regle"].startswith("Cryptoactifs"):
            ctl["recus"].insert(0, r_crypto.id)
        elif ctl["regle"].startswith("Part stable"):
            ctl["recus"].insert(0, r_stable.id)
    alts = []
    for i, poids in enumerate(alternatives(c, ticker, montant, besoin, rc, lambda: Registre("X")), 1):
        nom_alt = "Alternative " + chr(64 + i) + " : " + " + ".join(f"{int(round(w * 100))} % {t}" for t, w in poids.items())
        for t, w in poids.items():
            reg.ajouter(f"Composition de l'alternative {chr(64 + i)} : {t}", round(w * 100), "%",
                        "allocation fictive", "grille de combinaisons conformes au contrat", "verdict.py")
        r_alt = rejouer(poids, montant, besoin, reg, nom_alt)
        alts.append({"nom": nom_alt, "res": r_alt,
                     "eval": evaluer(c, r_alt, montant / c["capital_total"], rc)})
    return {"contrat": c, "registre": reg, "principal": res, "evaluation": ev, "alternatives": alts}


# ---------------- Avocat du diable et Explicateur ----------------
def _contexte(persona, calc) -> str:
    ev = calc["evaluation"]
    lignes = [f"Persona : {persona} — {calc['contrat']['profil']}",
              f"Verdict (regles codees) : {ev['verdict']}", "Controles :"]
    lignes += [f"- {x['regle']} : {x['statut']} (valeur {x['valeur']}, limite {x['limite']}, recus {x['recus']})"
               for x in ev["controles"]]
    lignes += ["Alternatives (verdict) :"] + [f"- {a['nom']} : {a['eval']['verdict']}" for a in calc["alternatives"]]
    lignes += ["Recus disponibles (les SEULS chiffres autorises) :", calc["registre"].pour_ia()]
    return "\n".join(lignes)


def _avocat_hors_ligne(persona, calc) -> str:
    rc = calc["principal"]["recus"]
    ev = calc["evaluation"]
    dep = [x for x in ev["controles"] if x["statut"] != "ok"]
    txt = f"Verdict : {ev['verdict']}. "
    if dep:
        def phrase(x):
            r = x["recus"]
            if len(r) >= 2:
                return f"{x['regle'].lower()} : {x['valeur']} [{r[0]}] pour une limite de {x['limite']} [{r[-1]}]"
            return f"{x['regle'].lower()} : {x['valeur']} ({x['limite']})"
        txt += "Ce placement ne respecte pas votre contrat sur ces points : " + "; ".join(phrase(x) for x in dep) + ". "
    txt += f"Au pire moment, votre placement aurait valu {rc['creux'].affichage} [{rc['creux'].id}]. "
    if calc["alternatives"]:
        txt += "Deux alternatives conformes ont ete rejouees sur la meme periode : " + "; ".join(
            f"{a['nom']} (pire moment {a['res']['recus']['creux'].affichage} [{a['res']['recus']['creux'].id}])"
            for a in calc["alternatives"]) + "."
    return txt


def _explicateur_hors_ligne(persona, calc) -> str:
    rc = calc["principal"]["recus"]
    lignes = ["**Faits.** " + " ".join(f"{r.libelle} : {r.affichage} [{r.id}]." for r in rc.values())]
    lignes.append(f"**Pourquoi c'est important pour vous.** Verdict : {calc['evaluation']['verdict']}.")
    lignes.append("**Hypotheses.** Les limites du contrat sont des hypotheses de l'equipe pour ce profil fictif.")
    lignes.append("**Limites.** Une seule periode historique ; le passe ne predit pas l'avenir ; "
                  "biais du survivant (actifs choisis en 2026).")
    lignes.append("**Ce qui changerait la reponse.** Un horizon plus long ou une part plus petite de ce placement.")
    return "\n\n".join(lignes)


MAX_RELANCES = 2


def _defauts(v: dict) -> list:
    return ([f"le chiffre « {x} » n'a aucun recu" for x in v["chiffres_sans_recu"]]
            + [f"le recu {x} n'existe pas" for x in v["recus_inconnus"]]
            + [f"chiffre mal cite : {x}" for x in v.get("chiffres_mal_cites", [])])


def _rediger_sous_garde(nom, prompt, ctx, recus, secours, etape, appel_ia=None) -> str:
    """Garde-fou qui EMPECHE (pas qui rappelle) : un texte d'agent n'est affiche que si
    le Verificateur l'accepte a 100 %. Sinon, on relance l'agent en NOMMANT le defaut
    (boucle de correction, au plus MAX_RELANCES fois). Si l'echec persiste, on affiche
    le texte de secours genere par le code, et on le dit."""
    if HORS_LIGNE:
        txt = secours()
        etape(f"{nom} (hors ligne)", "texte gabarit", txt[:200])
        return txt
    appel_ia = appel_ia or _appel_ia
    message = ctx
    for essai in range(MAX_RELANCES + 1):
        txt = appel_ia(prompt, message)
        v = verifier(txt, recus)
        defauts = _defauts(v)
        etape(f"{nom} (IA)", f"redaction, essai {essai + 1}",
              {"texte": txt[:200], "fidelite": v["score"], "defauts": defauts})
        if not defauts:
            return txt
        message = (ctx + "\n\nTON TEXTE PRECEDENT A ETE REFUSE PAR LE VERIFICATEUR. Defauts nommes :\n- "
                   + "\n- ".join(defauts) + "\nNe les reproduis pas. Reecris le texte complet.")
    txt = secours()
    etape(f"{nom} (secours, code)", "texte refuse apres relances : texte genere par le code affiche", txt[:200])
    return "*Texte de secours genere par le code (le texte de l'IA a ete bloque par le Verificateur).*\n\n" + txt


def analyser(persona: str, demande: str, ticker=None, montant=None, besoin=None, **modifs) -> dict:
    """Parcours complet. Retourne tout ce que l'interface affiche, plus la trace."""
    trace, t0 = [], time.time()
    etape = lambda qui, quoi, sortie: trace.append(
        {"t": round(time.time() - t0, 2), "composant": qui, "action": quoi, "sortie": sortie})

    info = interviewer(persona, demande)
    etape("Intervieweur (IA)" if not HORS_LIGNE else "Intervieweur (hors ligne)", "analyse de la demande", info)
    ticker = ticker or info.get("ticker")
    montant = float(montant or info.get("montant") or 10000)
    besoin = besoin or info.get("besoin_annees")
    if ticker is None or besoin is None:
        return {"question": info.get("question") or "Pouvez-vous preciser votre demande ?", "trace": trace}

    calc = calculer(persona, ticker, montant, float(besoin), **modifs)
    etape("Machine a remonter le temps (code)", "relecture historique + regles du contrat",
          {"verdict": calc["evaluation"]["verdict"], "recus": len(calc["registre"].recus)})

    ctx = _contexte(persona, calc)
    recus = calc["registre"].recus
    avocat = _rediger_sous_garde("Avocat du diable", PROMPT_AVOCAT, ctx, recus,
                                 lambda: _avocat_hors_ligne(persona, calc), etape)
    carte = _rediger_sous_garde("Explicateur", PROMPT_EXPLICATEUR, ctx, recus,
                                lambda: _explicateur_hors_ligne(persona, calc), etape)
    verif = verifier(avocat + "\n" + carte, recus)
    etape("Verificateur de recus (code)", "controle final des chiffres affiches", verif)

    sortie = {"persona": persona, "demande": demande, "calc": calc, "avocat": avocat,
              "carte": carte, "verification": verif, "trace": trace}
    sauvegarder_trace(sortie)
    return sortie


def sauvegarder_trace(sortie: dict) -> str:
    """Trace JSON en local (dossier traces/) et, si configure, dans S3."""
    nom = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{sortie['persona']}-{uuid.uuid4().hex[:6]}.json"
    doc = {"persona": sortie["persona"], "demande": sortie["demande"],
           "verdict": sortie["calc"]["evaluation"]["verdict"],
           "controles": sortie["calc"]["evaluation"]["controles"],
           "recus": sortie["calc"]["registre"].en_dicts(), "avocat": sortie["avocat"],
           "carte": sortie["carte"], "verification": sortie["verification"], "trace": sortie["trace"]}
    texte = json.dumps(doc, ensure_ascii=False, indent=2, default=str)
    os.makedirs("traces", exist_ok=True)
    with open(os.path.join("traces", nom), "w", encoding="utf-8") as f:
        f.write(texte)
    bucket = os.environ.get("ALPHAFORGE_BUCKET")
    if bucket:
        import boto3
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=bucket, Key=f"traces/{nom}", Body=texte.encode("utf-8"), ContentType="application/json")
    return nom
