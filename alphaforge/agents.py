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

PROMPT_AVOCAT = """Tu es l'Avocat du diable d'AlphaForge AI : un conseiller bienveillant mais ferme.
Contexte : SIMULATION pédagogique, personas fictifs ; ce n'est pas un conseil financier personnalisé.
On te donne le profil, l'évaluation déjà faite par les règles du contrat (tu ne la changes jamais),
les alternatives et la liste des chiffres autorisés. Écris 4 à 6 phrases en français correct, avec
tous les accents, au vouvoiement :
1. Commence par ce que la personne AURAIT vécu, au conditionnel (c'est une relecture du passé) :
   la valeur de son placement au pire moment, sa date, et la perte maximale subie.
2. Explique pourquoi c'est important pour ELLE, en partant des règles marquées « bloquante »,
   puis des points de vigilance. Relie-les à son horizon, à son objectif et à ses préférences.
   Ne confonds jamais la perte SUBIE par le placement et la perte TOLÉRÉE par la personne.
3. Présente les 2 alternatives et ce qu'elles auraient donné au pire moment.
4. Termine par une question qui fait réfléchir (ex. « Si vous aviez pris votre retraite en
   janvier 2023, auriez-vous pu attendre ? »).
Si l'évaluation est « Coherent », confirme simplement et rappelle le risque qui reste.
Si elle est « A surveiller », nuance : ce qui va, ce qui demande de la vigilance.
Ne prête jamais à la personne un trait qui n'est pas dans son profil.
Les chiffres de la description du profil (âge, fourchette d'horizon comme « 8 à 12 ans ») ne sont PAS
autorisés : pour l'horizon, utilise uniquement l'horizon déclaré, avec son numéro. Pour une absence,
écris-la en mots (« aucune part en obligations ») plutôt que « 0 % ».
Interdits : « Monsieur » ou « Madame » (appelle la personne par son prénom) ; les mots internes
« verdict », « reçu », « règles codées », « conteste la demande » ; « achetez » ou « vendez ».
Règle absolue : chaque chiffre (%, $) vient de la liste des chiffres autorisés et est suivi de son
numéro entre crochets, ex. « 20 500 $ [#R-009] ». Aucun autre chiffre. Si une information manque
(ex. aucune source ESG documentée), dis que tu ne peux pas conclure sur ce point au lieu d'inventer."""

PROMPT_EXPLICATEUR = """Tu es l'Explicateur d'AlphaForge AI. SIMULATION pédagogique, pas un conseil financier.
Rédige la carte de vérité en français correct, avec tous les accents, au vouvoiement, en 5 sections
courtes avec ces titres exacts :
Faits / Pourquoi c'est important pour vous / Hypothèses / Limites / Ce qui changerait la réponse.
- Faits : uniquement ce que disent les données (pire moment, perte maximale, année 2022, fin de
  période), au conditionnel quand il s'agit du placement envisagé.
- Hypothèses : les limites du contrat sont des choix de l'équipe pour ce profil fictif.
- Limites : une seule période historique ; le passé ne prédit pas l'avenir ; biais du survivant
  (actifs choisis en 2026). Si une information manque (ex. ESG), écris
  « information manquante : impossible de conclure ».
Ne prête jamais à la personne un trait qui n'est pas dans son profil.
Les chiffres de la description du profil (âge, fourchette d'horizon comme « 8 à 12 ans ») ne sont PAS
autorisés : pour l'horizon, utilise uniquement l'horizon déclaré, avec son numéro. Pour une absence,
écris-la en mots (« aucune part en obligations ») plutôt que « 0 % ».
Règle absolue : chaque chiffre (%, $) vient de la liste des chiffres autorisés et est suivi de son
numéro entre crochets. Aucun autre chiffre. N'utilise pas les mots « verdict » ni « reçu »."""


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
    reg.ajouter("Montant envisagé", montant, "$", "demande de la personne", "declare dans la demande", "demande")
    r_poids = reg.ajouter("Poids de ce placement dans votre capital total", montant / c["capital_total"] * 100,
                          "%", f"contrat de {persona}", "montant / capital total fictif", "contrats.json")
    from .verdict import _composition
    comp = _composition(res["poids"])
    r_crypto = reg.ajouter("Part de cryptoactifs dans votre capital total",
                           comp["crypto"] * montant / c["capital_total"], "%", f"contrat de {persona}",
                           "part crypto du placement × montant / capital total", "assets_universe.csv ; contrats.json")
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
    c = calc["contrat"]

    def nature(x):
        if x["statut"] == "ok":
            return "respectee"
        if x["statut"] == "info_manquante":
            return "INFORMATION MANQUANTE (ne pas conclure)"
        if x["cle"] and not x.get("de_peu"):
            return "DEPASSEE - regle bloquante pour ce profil"
        if x.get("de_peu"):
            return "depassee de peu - vigilance"
        return "depassee - point de vigilance (non bloquant pour ce profil)"

    lignes = [f"Profil de la personne (ne lui prete AUCUN trait absent de ce texte) : "
              f"{c.get('description', c['profil'])}",
              f"Evaluation par les regles du contrat : {ev['verdict']}", "Detail des regles :"]
    lignes += [f"- {x['regle']} : {nature(x)} (valeur {x['valeur']}, limite {x['limite']}, numeros {x['recus']})"
               for x in ev["controles"]]
    lignes += ["Alternatives rejouees sur la meme periode :"] + [
        f"- {a['nom']} : {a['eval']['verdict']}, pire moment {a['res']['recus']['creux'].affichage} "
        f"{a['res']['recus']['creux'].id}" for a in calc["alternatives"]]
    lignes += ["Liste des chiffres autorises (les SEULS que tu peux ecrire) :", calc["registre"].pour_ia()]
    return "\n".join(lignes)


_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
         "septembre", "octobre", "novembre", "décembre"]
_VERDICT_FR = {"Coherent": "cohérent", "A surveiller": "à surveiller", "Incoherent": "incohérent"}


def _date_fr(d) -> str:
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {_MOIS[d.month - 1]} {d.year}"


def _phrase_controle(x) -> str:
    r = x["recus"]
    v = f"{x['valeur']} [{r[0]}]" if len(r) >= 2 else x["valeur"]
    lim = f"{x['limite']} [{r[-1]}]" if r else x["limite"]
    regle = x["regle"]
    if x["statut"] == "info_manquante":
        return ("information manquante : aucune source ESG publique n'est documentée pour ce secteur, "
                "il est donc impossible de conclure sur ce point")
    if regle.startswith("Perte maximale"):
        return f"la perte maximale aurait atteint {v}, alors que votre limite est de {lim}"
    if regle.startswith("Volatilite"):
        return f"la volatilité annuelle serait de {v}, au-delà de votre limite de {lim}"
    if regle.startswith("Part stable"):
        return f"la part placée en obligations serait de {v}, alors que votre profil en demande au moins {lim}"
    if regle.startswith("Poids maximal"):
        return f"ce placement représenterait {v} de votre capital, au-delà de la limite de {lim} pour un seul titre"
    if regle.startswith("Cryptoactifs"):
        return f"la part de cryptoactifs atteindrait {v} de votre capital, au-delà de votre plafond de {lim}"
    if regle.startswith("Temps de recuperation"):
        return f"il aurait fallu {v} pour revenir au montant investi, ce qui ne cadre pas avec votre horizon"
    return f"{regle.lower()} : {v} (limite {lim})"


def _avocat_hors_ligne(persona, calc) -> str:
    p = calc["principal"]
    rc = p["recus"]
    ev = calc["evaluation"]
    montant = next((r for r in calc["registre"].recus if r.libelle == "Montant envisagé"), None)
    depart = f"{montant.affichage} [{montant.id}]" if montant else "votre montant"
    txt = (f"{persona}, si vous aviez placé {depart} au départ, votre placement aurait valu "
           f"{rc['creux'].affichage} [{rc['creux'].id}] au pire moment, le {_date_fr(p['date_creux'])}. ")
    dep = [x for x in ev["controles"] if x["statut"] != "ok"]
    if dep:
        txt += "Pour votre profil, ce placement est jugé " + _VERDICT_FR[ev["verdict"]] + " : " + " ; ".join(
            _phrase_controle(x) for x in dep) + ". "
    else:
        txt += "Ce placement respecte les limites de votre profil ; le risque de baisse reste réel. "
    if calc["alternatives"]:
        txt += "Deux répartitions conformes à votre profil, rejouées sur la même période : " + " ; ".join(
            f"{a['nom'].split(' : ', 1)[-1]}, qui aurait valu {a['res']['recus']['creux'].affichage} "
            f"[{a['res']['recus']['creux'].id}] au pire moment" for a in calc["alternatives"]) + "."
    return txt


def _explicateur_hors_ligne(persona, calc) -> str:
    rc = calc["principal"]["recus"]
    cles = [k for k in ("creux", "perte_max", "an2022", "fin", "recup", "besoin") if k in rc]
    lignes = ["**Faits.** " + " ".join(f"{rc[k].libelle.split(' — ')[0]} : {rc[k].affichage} [{rc[k].id}]."
                                         for k in cles)]
    lignes.append(f"**Pourquoi c'est important pour vous.** Pour votre profil, ce placement est jugé "
                  f"{_VERDICT_FR[calc['evaluation']['verdict']]}, d'après les limites de votre contrat.")
    lignes.append("**Hypothèses.** Les limites du contrat sont des hypothèses de l'équipe pour ce profil fictif.")
    lignes.append("**Limites.** Une seule période historique ; le passé ne prédit pas l'avenir ; "
                  "biais du survivant (actifs choisis en 2026).")
    lignes.append("**Ce qui changerait la réponse.** Un horizon plus long, ou une part plus petite de ce placement.")
    return "\n\n".join(lignes)


MAX_RELANCES = 2
_NOMBRES = r"(\d+([.,]\d+)?|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|quinze|vingt|trente)"
HORIZON_DIT = re.compile(rf"\b{_NOMBRES}\s*(ans?|ann[ée]es?|mois)\b", re.I)


def _defauts(v: dict) -> list:
    return ([f"le chiffre « {x} » n'a aucun recu" for x in v["chiffres_sans_recu"]]
            + [f"le recu {x} n'existe pas" for x in v["recus_inconnus"]]
            + [f"chiffre mal cite : {x}" for x in v.get("chiffres_mal_cites", [])]
            + [f"le chiffre « {x} » n'est pas suivi de son numero de recu" for x in v.get("chiffres_non_cites", [])])


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
    return "*Texte de secours généré par le code : le texte de l'IA a été bloqué par le Vérificateur.*\n\n" + txt


def analyser(persona: str, demande: str, ticker=None, montant=None, besoin=None, **modifs) -> dict:
    """Parcours complet. Retourne tout ce que l'interface affiche, plus la trace."""
    trace, t0 = [], time.time()
    etape = lambda qui, quoi, sortie: trace.append(
        {"t": round(time.time() - t0, 2), "composant": qui, "action": quoi, "sortie": sortie})

    info = interviewer(persona, demande)
    etape("Intervieweur (IA)" if not HORS_LIGNE else "Intervieweur (hors ligne)", "analyse de la demande", info)
    ticker = ticker or info.get("ticker")
    montant = float(montant or info.get("montant") or 10000)
    if besoin is None and info.get("besoin_annees") is not None and not HORIZON_DIT.search(demande):
        # Garde-fou qui EMPECHE : l'IA a fourni un horizon que la personne n'a jamais donne.
        etape("Garde-fou (code)", "horizon invente par l'IA rejete", {"horizon_propose": info.get("besoin_annees")})
        info["besoin_annees"] = None
        info["question"] = "Dans combien de temps pensez-vous avoir besoin de cet argent ?"
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
