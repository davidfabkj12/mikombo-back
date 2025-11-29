import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import uuid
import bcrypt

load_dotenv()

async def seed_database():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    
    print("Clearing existing data...")
    await db.users.delete_many({})
    await db.produits.delete_many({})
    await db.animaux.delete_many({})
    await db.cultures.delete_many({})
    
    print("Creating admin user...")
    admin_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    await db.users.insert_one({
        "id": str(uuid.uuid4()),
        "email": "admin@mikombopark.com",
        "nom": "Admin",
        "prenom": "Mikombo",
        "telephone": "+243123456789",
        "role": "admin",
        "password_hash": admin_password,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    print("Creating sample products...")
    produits = [
        {"nom": "Tomates Bio", "categorie": "Légumes", "description": "Tomates fraîches cultivées sans pesticides", "prix": 2.5, "unite": "kg", "stock": 50, "saison": True},
        {"nom": "Carottes", "categorie": "Légumes", "description": "Carottes croquantes et sucrées", "prix": 1.8, "unite": "kg", "stock": 40},
        {"nom": "Laitue", "categorie": "Légumes", "description": "Salade fraîche du jour", "prix": 1.2, "unite": "pièce", "stock": 30, "saison": True},
        {"nom": "Mangues", "categorie": "Fruits", "description": "Mangues juteuses et parfumées", "prix": 3.5, "unite": "kg", "stock": 25, "saison": True},
        {"nom": "Bananes", "categorie": "Fruits", "description": "Bananes mûres à point", "prix": 2.0, "unite": "kg", "stock": 60},
        {"nom": "Poulet Fermier", "categorie": "Viande", "description": "Poulet élevé en liberté", "prix": 8.5, "unite": "kg", "stock": 15},
    ]
    
    for p in produits:
        await db.produits.insert_one({
            "id": str(uuid.uuid4()),
            **p,
            "photos": [],
            "visible": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    print("Creating sample animals...")
    animaux = [
        {"espece": "Lion", "nom": "Simba", "enclos": "Savane A", "etat_sante": "Excellent", "description": "Mâle adulte majestueux"},
        {"espece": "Girafe", "nom": "Sophie", "enclos": "Savane B", "etat_sante": "Bonne santé", "description": "Femelle gracieuse"},
        {"espece": "Zèbre", "nom": "Rayure", "enclos": "Savane A", "etat_sante": "Bonne santé", "description": "Jeune zèbre joueur"},
        {"espece": "Éléphant", "nom": "Dumbo", "enclos": "Enclos C", "etat_sante": "Excellent", "description": "Éléphant d'Afrique imposant"},
    ]
    
    for a in animaux:
        await db.animaux.insert_one({
            "id": str(uuid.uuid4()),
            **a,
            "photo": "",
            "visible": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    print("Creating sample cultures...")
    cultures = [
        {"type_culture": "Tomates", "surface": 2.5, "periode_production": "Mars - Juillet", "statut": "en_production"},
        {"type_culture": "Carottes", "surface": 1.8, "periode_production": "Avril - Août", "statut": "en_production"},
        {"type_culture": "Mangues", "surface": 5.0, "periode_production": "Octobre - Février", "statut": "hors_saison"},
    ]
    
    for c in cultures:
        await db.cultures.insert_one({
            "id": str(uuid.uuid4()),
            **c,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    print("✅ Database seeded successfully!")
    print("\n📝 Admin credentials:")
    print("   Email: admin@mikombopark.com")
    print("   Password: admin123")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_database())
