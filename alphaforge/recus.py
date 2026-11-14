"""Registre des recus : chaque chiffre affiche porte un numero (#R-001) qui renvoie
a son calcul, sa source, sa periode et sa devise."""
from dataclasses import dataclass, asdict, field


def fmt_nombre(x: float, decimales: int = 0) -> str:
    """Format francais : 17 400 ; -71 ; 3,4"""
    s = f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


@dataclass
class Recu:
    id: str
    libelle: str
    valeur: float
    unite: str  # "%", "$", "mois", "ans"
    periode: str
    calcul: str
    sources: str
    devise: str = "CAD"

    @property
    def affichage(self) -> str:
        if self.unite == "%":
            dec = 1 if abs(self.valeur) < 10 and self.valeur != int(self.valeur) else 0
            return f"{fmt_nombre(self.valeur, dec)} %"
        if self.unite == "$":
            return f"{fmt_nombre(round(self.valeur, -2))} $"
        return f"{fmt_nombre(self.valeur)} {self.unite}"


@dataclass
class Registre:
    prefixe: str = "R"
    recus: list = field(default_factory=list)

    def ajouter(self, libelle, valeur, unite, periode, calcul, sources, devise="CAD") -> Recu:
        r = Recu(f"#{self.prefixe}-{len(self.recus) + 1:03d}", libelle, float(valeur),
                 unite, periode, calcul, sources, devise)
        self.recus.append(r)
        return r

    def par_id(self) -> dict:
        return {r.id: r for r in self.recus}

    def en_dicts(self) -> list:
        return [asdict(r) | {"affichage": r.affichage} for r in self.recus]

    def pour_ia(self) -> str:
        """Liste compacte donnee aux agents : ils ne peuvent citer QUE ces chiffres."""
        return "\n".join(f"{r.id} | {r.libelle} | {r.affichage} | {r.periode}" for r in self.recus)
