"""AWS Lambda : execute la Machine a remonter le temps + les regles du contrat.

Evenement attendu : {"persona": "Robert", "ticker": "TSLA", "montant": 60000, "besoin": 4}
Les CSV sont lus depuis s3://$ALPHAFORGE_BUCKET/data/ (copies dans /tmp au premier appel).
Couche requise : AWS SDK for pandas (fournit pandas et numpy).
"""
import json
import os
from pathlib import Path

FICHIERS = ["prices_daily.csv", "fx_usdcad_daily.csv", "assets_universe.csv"]


def _preparer_donnees():
    bucket = os.environ.get("ALPHAFORGE_BUCKET")
    local = Path("/tmp/data")
    if bucket and not (local / FICHIERS[0]).exists():
        import boto3
        local.mkdir(parents=True, exist_ok=True)
        s3 = boto3.client("s3")
        for f in FICHIERS:
            s3.download_file(bucket, f"data/{f}", str(local / f))
    if bucket:
        os.environ["ALPHAFORGE_DATA"] = str(local)


def lambda_handler(event, context):
    _preparer_donnees()
    from alphaforge.agents import calculer
    from alphaforge.serialisation import vers_json
    if isinstance(event.get("body"), str):
        event = json.loads(event["body"])
    calc = calculer(event["persona"], event["ticker"], float(event["montant"]), float(event["besoin"]))
    print(json.dumps({"persona": event["persona"], "ticker": event["ticker"],
                      "verdict": calc["evaluation"]["verdict"], "recus": len(calc["registre"].recus)}))
    return vers_json(calc)
