import os
import json
from datetime import datetime
from groq import Groq
from sqlalchemy.orm import Session, joinedload
from app.models import Utilisateur, Produit, Commande, Avis, ConversationBot

GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY = 20
 
# Groq auto-reads GROQ_API_KEY from the environment if api_key is not given
client = Groq()

# ── Tool definitions ──────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rechercher_produits",
            "description": (
                "Recherche en temps réel des produits disponibles sur la plateforme Agrinova. "
                "Utilise cet outil quand l'utilisateur demande des produits spécifiques, veut "
                "comparer des prix, cherche dans une région, ou pose une question sur la disponibilité. "
                "Tous les paramètres sont optionnels."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nom": {
                        "type": "string",
                        "description": "Mot-clé dans le nom du produit (ex: 'tomate', 'riz', 'mangue', 'oignon')",
                    },
                    "categorie": {
                        "type": "string",
                        "enum": ["Légumes", "Fruits", "Céréales", "Légumineuses"],
                        "description": "Filtrer par catégorie",
                    },
                    "prix_max": {
                        "type": "number",
                        "description": "Prix maximum en FCFA par unité",
                    },
                    "localisation": {
                        "type": "string",
                        "description": "Région ou ville à chercher (ex: 'Thiès', 'Dakar', 'Saint-Louis', 'Casamance')",
                    },
                },
                "required": [],
            },
        },
    }
]


# ── Tool executor ─────────────────────────────────────────────────────────────
def _executer_recherche_produits(
    db: Session,
    nom: str | None = None,
    categorie: str | None = None,
    prix_max: float | None = None,
    localisation: str | None = None,
) -> str:
    query = (
        db.query(Produit)
        .options(joinedload(Produit.agriculteur))
        .filter(Produit.est_disponible == True)
    )
    if nom:
        query = query.filter(Produit.nom.ilike(f"%{nom}%"))
    if categorie:
        query = query.filter(Produit.categorie == categorie)
    if prix_max is not None:
        query = query.filter(Produit.prix <= prix_max)
    if localisation:
        query = query.filter(Produit.localisation.ilike(f"%{localisation}%"))

    produits = query.order_by(Produit.prix.asc()).all()

    if not produits:
        return "Aucun produit trouvé pour ces critères sur la plateforme."

    lignes = [f"Résultats ({len(produits)} produit(s) trouvé(s)):"]
    for p in produits[:25]:
        vendeur = p.agriculteur.nom if p.agriculteur else "N/A"
        note = f" | ⭐{p.agriculteur.note_globale:.1f}" if p.agriculteur and p.agriculteur.note_globale else ""
        verifie = " ✓" if p.agriculteur and p.agriculteur.est_verifie else ""
        lignes.append(
            f"• {p.nom} | {p.prix:,.0f} FCFA/{p.unite}"
            f" | stock: {p.quantite_disponible} {p.unite}"
            f" | {p.localisation or 'localisation N/A'}"
            f" | vendeur: {vendeur}{verifie}{note}"
            + (f"\n  Description: {p.description[:100]}" if p.description else "")
        )
    if len(produits) > 25:
        lignes.append(f"... ({len(produits) - 25} autres résultats non affichés)")
    return "\n".join(lignes)


# ── Context builder ───────────────────────────────────────────────────────────
def _date_fr(dt) -> str:
    if not dt:
        return "N/A"
    try:
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(dt)


def _construire_contexte(user: Utilisateur, db: Session) -> str:
    now = datetime.now()
    sections: list[str] = []

    sections.append(
        f"=== PROFIL UTILISATEUR ===\n"
        f"Nom: {user.nom}\n"
        f"Rôle: {user.role}\n"
        f"Email: {user.email}\n"
        f"Téléphone: {user.telephone or 'non renseigné'}\n"
        f"Localisation: {user.localisation or 'non renseignée'}\n"
        f"Note globale: {user.note_globale}/5 ({user.nombre_avis} avis reçus)\n"
        f"Compte vérifié: {'Oui' if user.est_verifie else 'Non'}\n"
        f"Membre depuis: {_date_fr(user.date_inscription)}"
    )

    if user.role == "producteur":
        produits = (
            db.query(Produit)
            .filter(Produit.agriculteur_id == user.id)
            .order_by(Produit.date_publication.desc())
            .all()
        )
        nb_dispo = sum(1 for p in produits if p.est_disponible)
        stock_total = sum((p.quantite_disponible or 0) for p in produits)

        if produits:
            by_cat: dict[str, list] = {}
            for p in produits:
                by_cat.setdefault(p.categorie or "Autre", []).append(p)

            prod_lines = [
                f"=== MES PRODUITS ({len(produits)} total | {nb_dispo} en vente | stock total: {stock_total} unités) ==="
            ]
            for cat, ps in by_cat.items():
                prod_lines.append(f"\n[{cat}]")
                for p in ps:
                    statut = "✅ en vente" if p.est_disponible else "⏸ masqué"
                    prod_lines.append(
                        f"  • ID#{p.id} | {p.nom} | {p.prix} FCFA/{p.unite}"
                        f" | stock: {p.quantite_disponible} {p.unite} | {statut}"
                        f" | publié le {_date_fr(p.date_publication)}"
                    )

            low_stock = [p for p in produits if p.est_disponible and (p.quantite_disponible or 0) <= 5]
            if low_stock:
                prod_lines.append(
                    "\n⚠️ ALERTE STOCK BAS (≤5 unités): "
                    + ", ".join(f"{p.nom} ({p.quantite_disponible} {p.unite})" for p in low_stock)
                )
            sections.append("\n".join(prod_lines))
        else:
            sections.append("=== MES PRODUITS ===\nAucun produit publié.")

        commandes = (
            db.query(Commande)
            .options(joinedload(Commande.produit), joinedload(Commande.acheteur))
            .filter(Commande.agriculteur_id == user.id)
            .order_by(Commande.date_commande.desc())
            .all()
        )
        if commandes:
            total_revenus = sum((c.montant_total or 0) for c in commandes)
            by_statut: dict[str, int] = {}
            for c in commandes:
                by_statut[c.statut] = by_statut.get(c.statut, 0) + 1

            prod_revenus: dict[str, float] = {}
            prod_qte: dict[str, int] = {}
            for c in commandes:
                nom = c.produit.nom if c.produit else f"Produit #{c.produit_id}"
                prod_revenus[nom] = prod_revenus.get(nom, 0) + c.montant_total
                prod_qte[nom] = prod_qte.get(nom, 0) + c.quantite
            top_rev = sorted(prod_revenus.items(), key=lambda x: x[1], reverse=True)[:5]

            debut_mois = now.replace(day=1, hour=0, minute=0, second=0)
            rev_mois = sum((c.montant_total or 0) for c in commandes if c.date_commande and c.date_commande >= debut_mois)
            cmd_mois = sum(1 for c in commandes if c.date_commande and c.date_commande >= debut_mois)

            cmd_lines = [
                f"=== COMMANDES REÇUES ({len(commandes)}) ===",
                f"Revenus totaux: {total_revenus:,.0f} FCFA",
                f"Ce mois-ci: {rev_mois:,.0f} FCFA | {cmd_mois} commandes",
                "Statuts: " + " | ".join(f"{k}: {v}" for k, v in by_statut.items()),
                "\nTop produits par revenu:",
            ]
            for nom, rev in top_rev:
                cmd_lines.append(f"  • {nom}: {rev:,.0f} FCFA (qté: {prod_qte.get(nom, 0)})")
            cmd_lines.append("\nDernières commandes (30):")
            for c in commandes[:30]:
                prod_nom = c.produit.nom if c.produit else f"Produit #{c.produit_id}"
                acheteur_nom = c.acheteur.nom if c.acheteur else f"Acheteur #{c.acheteur_id}"
                cmd_lines.append(
                    f"  • Cmd#{c.id} | {prod_nom} | qté:{c.quantite} | {c.montant_total:,.0f} FCFA"
                    f" | {c.statut} | {acheteur_nom} | {_date_fr(c.date_commande)}"
                )
            sections.append("\n".join(cmd_lines))

        avis_list = (
            db.query(Avis)
            .filter(Avis.agriculteur_id == user.id)
            .order_by(Avis.date_avis.desc())
            .all()
        )
        if avis_list:
            notes = [a.note for a in avis_list if a.note is not None]
            moy = round(sum(notes) / len(notes), 1) if notes else 0
            distrib = {i: notes.count(i) for i in range(1, 6)}
            avis_lines = [
                f"=== AVIS CLIENTS ({len(avis_list)}) ===",
                f"Note moyenne: {moy}/5",
                "Distribution: " + " | ".join(f"{k}★:{v}" for k, v in distrib.items()),
            ]
            for a in avis_list[:5]:
                avis_lines.append(f"  • {a.note}/5 – \"{a.commentaire or '—'}\" ({_date_fr(a.date_avis)})")
            sections.append("\n".join(avis_lines))

    else:  # ACHETEUR
        commandes = (
            db.query(Commande)
            .options(joinedload(Commande.produit), joinedload(Commande.agriculteur))
            .filter(Commande.acheteur_id == user.id)
            .order_by(Commande.date_commande.desc())
            .all()
        )
        if commandes:
            total_depenses = sum((c.montant_total or 0) for c in commandes)
            by_statut: dict[str, int] = {}
            for c in commandes:
                by_statut[c.statut] = by_statut.get(c.statut, 0) + 1
            debut_mois = now.replace(day=1, hour=0, minute=0, second=0)
            dep_mois = sum((c.montant_total or 0) for c in commandes if c.date_commande and c.date_commande >= debut_mois)

            cmd_lines = [
                f"=== MES COMMANDES ({len(commandes)}) ===",
                f"Total dépensé: {total_depenses:,.0f} FCFA | Ce mois-ci: {dep_mois:,.0f} FCFA",
                "Statuts: " + " | ".join(f"{k}: {v}" for k, v in by_statut.items()),
                "\nHistorique:",
            ]
            for c in commandes[:20]:
                prod_nom = c.produit.nom if c.produit else f"Produit #{c.produit_id}"
                vendeur = c.agriculteur.nom if c.agriculteur else "N/A"
                unite = c.produit.unite if c.produit else ""
                cmd_lines.append(
                    f"  • Cmd#{c.id} | {prod_nom} | qté:{c.quantite}{unite}"
                    f" | {c.montant_total:,.0f} FCFA | {c.statut} | {vendeur} | {_date_fr(c.date_commande)}"
                )
            sections.append("\n".join(cmd_lines))

    sections.append(f"=== DATE/HEURE: {now.strftime('%d/%m/%Y %H:%M')} ===")
    return "\n\n".join(sections)


def _system_prompt(contexte: str) -> str:
    return f"""Tu es AgrinovaBot, l'assistant intelligent de la plateforme Agrinova — un marketplace agricole au Sénégal.

Tu as accès en temps réel aux données de l'utilisateur connecté ET tu peux effectuer des recherches en direct sur tous les produits de la plateforme via l'outil `rechercher_produits`.

**Quand utiliser `rechercher_produits` :**
- L'utilisateur demande des produits spécifiques ("tomates", "riz", "mangues"…)
- Il veut comparer des prix ("le moins cher", "pas plus de 500 FCFA")
- Il cherche dans une région ("à Thiès", "autour de Dakar")
- Il demande ce qui est disponible dans une catégorie
- Il veut savoir si un produit existe sur la plateforme
→ Appelle toujours cet outil pour avoir les données fraîches, même si des produits sont déjà dans le contexte.

Tu réponds toujours en français, de façon claire, concise et bienveillante.
Pour les analyses chiffrées sur l'utilisateur, utilise les données du contexte.
Pour toute question sur les produits de la plateforme, utilise l'outil de recherche.

--- DONNÉES DE L'UTILISATEUR ---
{contexte}
--- FIN ---"""


# ── Main chat function ────────────────────────────────────────────────────────
def chat_avec_groq(message: str, user: Utilisateur, db: Session) -> str:
    try:
        contexte = _construire_contexte(user, db)
    except Exception:
        contexte = (
            f"=== PROFIL UTILISATEUR ===\n"
            f"Nom: {user.nom}\nRôle: {user.role}\nEmail: {user.email}"
        )
    system = _system_prompt(contexte)

    historique_db = (
        db.query(ConversationBot)
        .filter(ConversationBot.user_id == user.id)
        .order_by(ConversationBot.date_envoi.desc())
        .limit(MAX_HISTORY)
        .all()
    )
    historique_db.reverse()

    messages: list[dict] = [{"role": "system", "content": system}]
    for h in historique_db:
        messages.append({"role": h.role, "content": h.contenu})
    messages.append({"role": "user", "content": message})

    # ── Premier appel avec les outils disponibles ──────────────────────────
    reponse = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.5,
        max_tokens=1500,
    )

    msg = reponse.choices[0].message

    # ── Si l'IA appelle un outil, on l'exécute et on relance ──────────────
    if msg.tool_calls:
        # Ajouter la réponse de l'assistant avec ses tool_calls
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Exécuter chaque outil appelé
        for tc in msg.tool_calls:
            if tc.function.name == "rechercher_produits":
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                resultat = _executer_recherche_produits(db, **args)
            else:
                resultat = f"Outil '{tc.function.name}' inconnu."

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": resultat,
            })

        # Deuxième appel avec les résultats de l'outil
        reponse2 = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=1500,
        )
        contenu_reponse = reponse2.choices[0].message.content

    else:
        contenu_reponse = msg.content or ""

    # Fallback si le modèle ne renvoie rien
    if not contenu_reponse.strip():
        contenu_reponse = "Je suis désolé, je n'ai pas pu générer une réponse. Veuillez reformuler votre question."

    # ── Sauvegarder en base ────────────────────────────────────────────────
    db.add(ConversationBot(user_id=user.id, role="user", contenu=message))
    db.add(ConversationBot(user_id=user.id, role="assistant", contenu=contenu_reponse))
    db.commit()

    return contenu_reponse
